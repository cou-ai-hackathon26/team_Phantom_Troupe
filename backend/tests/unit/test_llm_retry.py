"""Retry delays for Groq errors (no network: fake exceptions carry only the response headers)."""

import groq
import httpx

from app.core.config import settings
from app.models.llm_client import RETRY_MAX_WAIT_S, retry_delay


def _response(status: int, retry_after: str | None) -> httpx.Response:
    headers = {"retry-after": retry_after} if retry_after else {}
    return httpx.Response(status, headers=headers, request=httpx.Request("POST", "https://example.invalid"))


def _rate_limit(retry_after: str | None) -> groq.RateLimitError:
    return groq.RateLimitError("429", response=_response(429, retry_after), body=None)


def _server_error(retry_after: str | None) -> groq.InternalServerError:
    return groq.InternalServerError("500", response=_response(500, retry_after), body=None)


def test_rate_limit_honours_retry_after_beyond_the_outage_cap(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_rate_limit_max_wait_s", 20.0)
    assert retry_delay(_rate_limit("14"), 1) == 14.0  # previously cut to 8 s: still inside the token window
    assert retry_delay(_rate_limit("90"), 1) == 20.0  # capped


def test_rate_limit_without_header_backs_off_longer(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_rate_limit_max_wait_s", 20.0)
    assert [retry_delay(_rate_limit(None), a) for a in (1, 2, 3)] == [2.0, 4.0, 8.0]


def test_other_errors_keep_short_backoff() -> None:
    assert [retry_delay(_server_error(None), a) for a in (1, 2, 3)] == [1.0, 2.0, 4.0]
    assert retry_delay(_server_error("30"), 1) == RETRY_MAX_WAIT_S
