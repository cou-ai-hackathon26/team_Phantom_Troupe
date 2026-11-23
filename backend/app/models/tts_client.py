"""ElevenLabs text-to-speech client (streaming endpoint, httpx).

Opens the audio stream only after a 200, so callers can turn failures into a clean HTTP error before any
audio is sent. 429/5xx/network errors are retried with exponential backoff (max 3 retries, as for Groq).
The API key is sent only in the `xi-api-key` header and never logged.
"""

import asyncio
import logging
from functools import lru_cache

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.elevenlabs.io/v1"
MAX_RETRIES = 3


class TTSError(Exception):
    """Speech could not be generated (not configured, quota used up, provider down)."""


class TTSNotConfigured(TTSError):
    pass


class TTSQuotaExceeded(TTSError):
    pass


class ElevenLabsClient:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None, backoff_s: float = 1.0) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(settings.tts_timeout_s, connect=10.0))
        self._backoff_s = backoff_s

    async def open_stream(self, text: str) -> httpx.Response:
        """Returns a streaming response with status 200; the caller must `aclose()` it."""
        url = f"{API_BASE}/text-to-speech/{settings.tts_voice_id}/stream"
        body = {"text": text, "model_id": settings.tts_model_id, "language_code": "bn"}
        headers = {"xi-api-key": self._api_key, "Accept": "audio/mpeg"}
        for attempt in range(MAX_RETRIES + 1):
            request = self._client.build_request(
                "POST", url, params={"output_format": settings.tts_output_format}, json=body, headers=headers
            )
            try:
                response = await self._client.send(request, stream=True)
            except httpx.TransportError as exc:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(self._backoff_s * 2**attempt)
                    continue
                raise TTSError(f"ElevenLabs unreachable: {type(exc).__name__}") from exc
            if response.status_code == 200:
                return response
            detail = await _error_detail(response)
            if (response.status_code == 429 or response.status_code >= 500) and attempt < MAX_RETRIES:
                await asyncio.sleep(self._backoff_s * 2**attempt)
                continue
            logger.warning("tts provider error", extra={"data": {"status": response.status_code, "code": detail}})
            if "quota" in detail or response.status_code == 402:
                raise TTSQuotaExceeded("ElevenLabs character quota used up")
            raise TTSError(f"ElevenLabs error {response.status_code}")
        raise TTSError("ElevenLabs retries exhausted")  # unreachable; keeps type checkers happy


async def _error_detail(response: httpx.Response) -> str:
    """The provider's error code/status (e.g. "quota_exceeded"), lower-cased; never the request body."""
    try:
        await response.aread()
        detail = response.json().get("detail", {})
        if isinstance(detail, dict):
            return f"{detail.get('code', '')} {detail.get('status', '')}".strip().lower()
        return str(detail)[:120].lower()
    except (ValueError, AttributeError):
        return ""
    finally:
        await response.aclose()


@lru_cache
def _client(api_key: str) -> ElevenLabsClient:
    return ElevenLabsClient(api_key)


def get_tts_client() -> ElevenLabsClient:
    if not settings.tts_enabled or settings.elevenlabs_api_key is None:
        raise TTSNotConfigured("ELEVENLABS_API_KEY not set or TTS_ENABLED=false")
    return _client(settings.elevenlabs_api_key.get_secret_value())
