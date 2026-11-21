"""Service health checks. Each check has a timeout and never returns secret values."""

import asyncio
from collections.abc import Awaitable, Callable

from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import Settings, settings


class ServiceStatus(BaseModel):
    ok: bool
    detail: str


class HealthReport(BaseModel):
    status: str  # ok | degraded
    services: dict[str, ServiceStatus]
    version: str


def _secrets(cfg: Settings) -> list[str]:
    values = [cfg.database_url, cfg.qdrant_api_key, cfg.groq_api_key]
    return [v.get_secret_value() for v in values if v is not None and v.get_secret_value()]


def redact(message: str, cfg: Settings = settings) -> str:
    for secret in _secrets(cfg):
        message = message.replace(secret, "***")
    return message[:200]


async def check_postgres() -> str:
    from app.db.session import get_engine

    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))
    return "SELECT 1 ok"


async def check_qdrant() -> str:
    from app.repositories.qdrant_repository import get_qdrant_client

    client = get_qdrant_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    has = settings.qdrant_collection in names
    return f"{len(names)} collection(s); '{settings.qdrant_collection}' {'present' if has else 'not created yet'}"


async def check_groq() -> str:
    from app.models.llm_client import get_raw_groq_client

    models = await get_raw_groq_client().models.list()
    configured = settings.llm_model or "LLM_MODEL not set"
    ids = {m.id for m in models.data}
    suffix = "" if settings.llm_model is None else (" (available)" if settings.llm_model in ids else " (NOT listed!)")
    return f"{len(ids)} models; {configured}{suffix}"


async def check_embedding() -> str:
    from app.models.embedding_client import get_embedding_client

    client = get_embedding_client()
    if client.loaded:
        return f"{client.model_name} loaded on {client.device}"
    return f"{client.model_name} (lazy, not loaded yet)"


CHECKS: dict[str, Callable[[], Awaitable[str]]] = {
    "postgres": check_postgres,
    "qdrant": check_qdrant,
    "groq": check_groq,
    "embedding": check_embedding,
}


async def _run(fn: Callable[[], Awaitable[str]], timeout: float) -> ServiceStatus:
    try:
        detail = await asyncio.wait_for(fn(), timeout=timeout)
        return ServiceStatus(ok=True, detail=detail)
    except TimeoutError:
        return ServiceStatus(ok=False, detail=f"timeout after {timeout:.0f}s")
    except Exception as exc:  # noqa: BLE001 - health must never raise
        return ServiceStatus(ok=False, detail=redact(f"{type(exc).__name__}: {exc}"))


async def run_health_checks(
    checks: dict[str, Callable[[], Awaitable[str]]] | None = None,
) -> HealthReport:
    checks = checks or CHECKS
    names = list(checks)
    results = await asyncio.gather(*(_run(checks[n], settings.health_check_timeout_s) for n in names))
    services = dict(zip(names, results, strict=True))
    status = "ok" if all(s.ok for s in services.values()) else "degraded"
    from app import __version__

    return HealthReport(status=status, services=services, version=__version__)
