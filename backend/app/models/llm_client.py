"""Groq chat wrapper: JSON mode, timeout, exponential backoff on 429/5xx, token-usage logging.

Every call returns a Pydantic-validated object. Model id comes from env LLM_MODEL (never hard-coded).
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, TypeVar

import groq
from groq import AsyncGroq
from pydantic import BaseModel, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLMNotConfigured(LLMError):
    pass


class LLMRateLimited(LLMError):
    pass


class LLMBadOutput(LLMError):
    pass


@lru_cache
def get_raw_groq_client() -> AsyncGroq:
    if settings.groq_api_key is None:
        raise LLMNotConfigured("GROQ_API_KEY is not set in .env")
    return AsyncGroq(api_key=settings.groq_api_key.get_secret_value(), timeout=settings.llm_timeout_s, max_retries=0)


# Reasoning models answer faster (and spend fewer free-tier tokens) with minimal reasoning.
_REASONING_DEFAULTS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("openai/gpt-oss", {"reasoning_effort": "low", "include_reasoning": False}),
    ("qwen/qwen3", {"reasoning_effort": "none"}),
)


def model_extra_params(model: str) -> dict[str, Any]:
    for prefix, params in _REASONING_DEFAULTS:
        if model.startswith(prefix):
            return dict(params)
    return {}


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json_object(content: str) -> dict[str, Any]:
    text = _FENCE.sub("", content.strip())
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMBadOutput("no JSON object in model output") from None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMBadOutput(f"invalid JSON: {exc}") from None
    if not isinstance(value, dict):
        raise LLMBadOutput("model output is not a JSON object")
    return value


@dataclass
class LLMResult[M: BaseModel]:
    data: M
    model: str
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    header = response.headers.get("retry-after") if response is not None else None
    try:
        return float(header) if header else None
    except ValueError:
        return None


RETRY_MAX_WAIT_S = 8.0  # outages and timeouts: short waits


def retry_delay(exc: Exception, attempt: int) -> float:
    """Seconds to wait before retry `attempt` (1-based). A 429 on the free tier is a per-minute token limit:
    Groq's retry-after says when enough tokens are free again, so it is honoured up to
    LLM_RATE_LIMIT_MAX_WAIT_S (a follow-up asked right after an answer otherwise gave up inside the same
    minute). Other errors keep short exponential backoff."""
    backoff = float(2 ** (attempt - 1))
    if isinstance(exc, groq.RateLimitError):
        cap = settings.llm_rate_limit_max_wait_s
        return min(_retry_after_seconds(exc) or backoff * 2, cap)
    return min(_retry_after_seconds(exc) or backoff, RETRY_MAX_WAIT_S)


class LLMClient:
    def __init__(self, client: AsyncGroq | None = None, model: str | None = None) -> None:
        self._client = client
        self.model = model or settings.llm_model
        self.max_retries = settings.llm_max_retries

    @property
    def client(self) -> AsyncGroq:
        if self._client is None:
            self._client = get_raw_groq_client()
        return self._client

    async def complete_json(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        purpose: str = "llm",
    ) -> LLMResult[T]:
        if not self.model:
            raise LLMNotConfigured("LLM_MODEL is not set in .env (choose one with scripts/test_llm_models.py)")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        start = time.perf_counter()
        attempt = 0
        while True:
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_completion_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    **model_extra_params(self.model),
                )
                break
            except (
                groq.RateLimitError,
                groq.InternalServerError,
                groq.APITimeoutError,
                groq.APIConnectionError,
            ) as exc:
                attempt += 1
                if attempt > self.max_retries:
                    logger.warning("llm gave up", extra={"data": {"purpose": purpose, "error": type(exc).__name__}})
                    if isinstance(exc, groq.RateLimitError):
                        raise LLMRateLimited("Groq rate limit reached") from exc
                    raise LLMError(f"Groq unavailable: {type(exc).__name__}") from exc
                delay = retry_delay(exc, attempt)
                logger.info("llm retry", extra={"data": {"purpose": purpose, "attempt": attempt, "delay_s": delay}})
                await asyncio.sleep(delay)
            except groq.APIStatusError as exc:  # 400 etc. — not retryable
                raise LLMError(f"Groq error {exc.status_code}") from exc

        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = response.usage
        logger.info(
            "llm call",
            extra={
                "data": {
                    "purpose": purpose,
                    "model": self.model,
                    "latency_ms": latency_ms,
                    "prompt_tokens": usage.prompt_tokens if usage else None,
                    "completion_tokens": usage.completion_tokens if usage else None,
                    "retries": attempt,
                }
            },
        )
        content = response.choices[0].message.content or ""
        try:
            data = schema.model_validate(parse_json_object(content))
        except ValidationError as exc:
            raise LLMBadOutput(f"schema mismatch: {exc.error_count()} error(s)") from exc
        return LLMResult(
            data=data,
            model=self.model,
            latency_ms=latency_ms,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
        )


@lru_cache
def get_llm_client() -> LLMClient:
    return LLMClient()
