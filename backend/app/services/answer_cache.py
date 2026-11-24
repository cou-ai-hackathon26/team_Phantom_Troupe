"""Answer cache keyed by a hash of the (normalized) question, area and model.

Postgres table `answer_cache` when DATABASE_URL is set; otherwise an in-process LRU. Cache misses and
storage errors never fail a request. Only answers the real pipeline produced are ever stored.
"""

import hashlib
import logging
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.ingestion.text_normalizer import normalize_for_search

logger = logging.getLogger(__name__)


# Bump when retrieval or validation changes what an answer would be. Prompt edits are picked up automatically.
PIPELINE_VERSION = "2026-11-23"
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


# Prompts used only for follow-up turns. Follow-up answers are never cached, so these files cannot make a
# cached answer stale and are left out of the fingerprint (editing them must not discard the warm demo cache).
UNCACHED_PROMPT_PREFIX = "followup_"


@lru_cache
def pipeline_fingerprint() -> str:
    """PIPELINE_VERSION + a hash of the prompt files, so answers cached before a fix are never served after it."""
    digest = hashlib.sha256(PIPELINE_VERSION.encode())
    for path in sorted(PROMPTS_DIR.glob("*.md")):
        if path.name.startswith(UNCACHED_PROMPT_PREFIX):
            continue
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()[:16]


def cache_key(question: str, area: str | None, model: str | None, kind: str) -> str:
    basis = "|".join([kind, normalize_for_search(question), area or "*", model or "-", pipeline_fingerprint()])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


class AnswerCache(Protocol):
    async def get(self, key: str) -> dict | None: ...
    async def set(self, key: str, value: dict) -> None: ...
    async def clear(self) -> None: ...


class MemoryCache:
    def __init__(self, max_items: int = 512) -> None:
        self.max_items = max_items
        self._data: OrderedDict[str, dict] = OrderedDict()

    async def get(self, key: str) -> dict | None:
        value = self._data.get(key)
        if value is not None:
            self._data.move_to_end(key)
        return value

    async def set(self, key: str, value: dict) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self.max_items:
            self._data.popitem(last=False)

    async def clear(self) -> None:
        self._data.clear()


class PostgresCache:
    def __init__(self) -> None:
        self._memory = MemoryCache()  # front cache; also covers DB outages

    async def get(self, key: str) -> dict | None:
        hit = await self._memory.get(key)
        if hit is not None:
            return hit
        try:
            from app.db.models import AnswerCache as Row
            from app.db.session import get_sessionmaker

            async with get_sessionmaker()() as session:
                row = await session.get(Row, key)
                if row is not None:
                    await self._memory.set(key, row.response_json)
                    return row.response_json
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache read failed", extra={"data": {"error": type(exc).__name__}})
        return None

    async def set(self, key: str, value: dict) -> None:
        await self._memory.set(key, value)
        try:
            from sqlalchemy.dialects.postgresql import insert

            from app.db.models import AnswerCache as Row
            from app.db.session import get_sessionmaker

            async with get_sessionmaker()() as session:
                stmt = insert(Row).values(key=key, response_json=value)
                await session.execute(
                    stmt.on_conflict_do_update(index_elements=[Row.key], set_={"response_json": value})
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache write failed", extra={"data": {"error": type(exc).__name__}})

    async def clear(self) -> None:
        """Knowledge changed: cached answers (and refusals) may be stale."""
        await self._memory.clear()
        try:
            from sqlalchemy import delete

            from app.db.models import AnswerCache as Row
            from app.db.session import get_sessionmaker

            async with get_sessionmaker()() as session:
                await session.execute(delete(Row))
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache clear failed", extra={"data": {"error": type(exc).__name__}})


_cache: AnswerCache | None = None


def get_answer_cache() -> AnswerCache:
    global _cache
    if _cache is None:
        _cache = PostgresCache() if settings.database_url is not None else MemoryCache()
    return _cache
