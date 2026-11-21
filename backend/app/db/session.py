"""Async SQLAlchemy engine/session for Supabase (or the local offline Postgres)."""

from collections.abc import AsyncIterator
from functools import lru_cache
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "postgres", "::1"}


class DatabaseNotConfigured(RuntimeError):
    pass


def _connect_args(url: str) -> dict[str, object]:
    # Supabase pooler (PgBouncer/Supavisor) breaks asyncpg's prepared-statement cache.
    args: dict[str, object] = {"statement_cache_size": 0}
    host = urlparse(url.replace("+asyncpg", "")).hostname or ""
    if host not in _LOCAL_HOSTS:
        args["ssl"] = "require"
    return args


@lru_cache
def get_engine() -> AsyncEngine:
    if settings.database_url is None:
        raise DatabaseNotConfigured("DATABASE_URL is not set in .env")
    url = settings.database_url.get_secret_value()
    return create_async_engine(url, connect_args=_connect_args(url), pool_pre_ping=True, pool_size=5, max_overflow=5)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
