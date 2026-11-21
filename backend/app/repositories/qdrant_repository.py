"""Qdrant Cloud access (collection management and search are added in Phase 2/3)."""

from functools import lru_cache

from qdrant_client import AsyncQdrantClient

from app.core.config import settings


class QdrantNotConfigured(RuntimeError):
    pass


@lru_cache
def get_qdrant_client() -> AsyncQdrantClient:
    if not settings.qdrant_url:
        raise QdrantNotConfigured("QDRANT_URL is not set in .env")
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    return AsyncQdrantClient(url=settings.qdrant_url, api_key=api_key, timeout=10)
