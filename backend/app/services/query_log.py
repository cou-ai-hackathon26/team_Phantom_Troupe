"""Log every question (structured log always; Postgres query_logs when configured). No personal data."""

import logging
import re
import uuid

from app.core.config import settings
from app.core.logging import log_event

logger = logging.getLogger("adhikarai.query")

# BD mobile numbers and NID-length digit runs (Bangla or ASCII digits)
_PII = re.compile(r"(?:\+?৮?৮?|\+?8?8?)[0০][1১][3-9৩-৯][0-9০-৯]{8}|[0-9০-৯]{10,17}")
MAX_STORED_MESSAGE = 300


def safe_message(message: str) -> str | None:
    """The raw message is stored only if short and free of phone/NID-like numbers."""
    if len(message) > MAX_STORED_MESSAGE or _PII.search(message):
        return None
    return message


async def record_query(
    *,
    message: str,
    normalized_question: str,
    area: str | None,
    status: str,
    retrieved_chunk_ids: list[str],
    best_dense_score: float | None,
    latency_ms: int,
    llm_calls: int,
    cached: bool,
    model: str | None,
    gate: str,
) -> str:
    request_id = str(uuid.uuid4())
    log_event(
        logger,
        "query",
        request_id=request_id,
        area=area,
        status=status,
        gate=gate,
        retrieved=retrieved_chunk_ids,
        best_dense_score=round(best_dense_score, 4) if best_dense_score is not None else None,
        latency_ms=latency_ms,
        llm_calls=llm_calls,
        cached=cached,
    )
    if settings.database_url is None:
        return request_id
    try:
        from app.db.models import QueryLog
        from app.db.session import get_sessionmaker

        async with get_sessionmaker()() as session:
            session.add(
                QueryLog(
                    id=uuid.UUID(request_id),
                    message=safe_message(message),
                    normalized_question=normalized_question,
                    area=area,
                    status=status,
                    retrieved_chunk_ids=retrieved_chunk_ids,
                    best_dense_score=best_dense_score,
                    latency_ms=latency_ms,
                    llm_calls=llm_calls,
                    cached=cached,
                    model=model,
                )
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 - logging must never fail a request
        logger.warning("query_logs write failed", extra={"data": {"error": type(exc).__name__}})
    return request_id
