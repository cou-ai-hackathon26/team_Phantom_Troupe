"""Groq client access. The full JSON/retry wrapper is added in Phase 4."""

from functools import lru_cache

from groq import AsyncGroq

from app.core.config import settings


class LLMNotConfigured(RuntimeError):
    pass


@lru_cache
def get_raw_groq_client() -> AsyncGroq:
    if settings.groq_api_key is None:
        raise LLMNotConfigured("GROQ_API_KEY is not set in .env")
    return AsyncGroq(api_key=settings.groq_api_key.get_secret_value(), timeout=settings.llm_timeout_s, max_retries=0)
