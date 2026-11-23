"""Read answers aloud (🔊) with ElevenLabs, built for the free tier (~10k characters a month).

Flow: /chat adds `speech_token` (an HMAC of the answer text) -> the UI posts {text, token} to /tts ->
we clean the text, register it under a content hash and return an audio URL -> GET streams the audio
from ElevenLabs while saving it to `data/tts_cache/<hash>.mp3`, so the same answer is never paid twice.

- Only text our API produced can be spoken (token check), so the endpoint can't be used to spend credits.
- Answers about a personal document get no token: their text never goes to ElevenLabs or the disk cache.
- The spoken text is the grounded answer itself (citation markers, links and markdown removed), so no new
  facts are introduced. Long answers are cut at a sentence end (TTS_MAX_CHARS) to save credits.
"""

import asyncio
import hashlib
import logging
import re
import time
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.security import sign_text, verify_text
from app.models.tts_client import ElevenLabsClient, TTSError, get_tts_client

logger = logging.getLogger(__name__)

PURPOSE = "tts"
KEY_RE = re.compile(r"^[0-9a-f]{64}$")
INFLIGHT_TTL_S = 120.0
MAX_PENDING = 512

_URL = re.compile(r"https?://\S+|www\.\S+")
_MARKER = re.compile(r"\[\s*[CWU]?[0-9০-৯]+\s*\]")  # [১], [2], [C1] …
_BULLET = re.compile(r"^\s*[-•*]\s+", re.MULTILINE)
_MARKDOWN = re.compile(r"[*_`#>]+")
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([।,.?!:;])")
_SENTENCE_END = ("।", "?", "!", "\n")


class InvalidSpeechToken(Exception):
    pass


class UnknownAudio(Exception):
    pass


@dataclass(frozen=True)
class PreparedAudio:
    key: str
    cached: bool
    chars: int


_pending: OrderedDict[str, str] = OrderedDict()  # key -> cleaned text, waiting for its GET
_inflight: dict[str, float] = {}  # key -> start time, while a stream is being generated


def is_enabled() -> bool:
    return settings.tts_enabled and settings.elevenlabs_api_key is not None


def clean_for_speech(text: str, max_chars: int | None = None) -> str:
    """What the voice should read: no citation markers, links or markdown; cut at a sentence end if long."""
    out = _URL.sub("", text)
    out = _MARKER.sub("", out)
    out = _BULLET.sub("", out)
    out = _MARKDOWN.sub("", out)
    out = re.sub(r"[ \t]+", " ", out)
    out = _SPACE_BEFORE_PUNCT.sub(r"\1", out)
    out = "\n".join(line.strip() for line in out.splitlines() if line.strip())
    limit = max_chars or settings.tts_max_chars
    if len(out) > limit:
        head = out[:limit]
        end = max(head.rfind(mark) for mark in _SENTENCE_END)
        out = head[: end + 1].strip() if end >= limit // 2 else head.rstrip()
    return out


def speech_token(answer: str, user_doc_id: str | None = None) -> str | None:
    """Token for the 🔊 button, or None when the answer must not (or can't) go to ElevenLabs."""
    if user_doc_id or not is_enabled() or not answer.strip():
        return None
    return sign_text(PURPOSE, answer)


def audio_key(clean_text: str) -> str:
    basis = "|".join([settings.tts_model_id, settings.tts_voice_id, settings.tts_output_format, clean_text])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def cached_path(key: str) -> Path | None:
    if not KEY_RE.match(key):
        return None
    path = settings.tts_cache_dir / f"{key}.mp3"
    return path if path.is_file() and path.stat().st_size > 0 else None


def _register(clean_text: str) -> str:
    key = audio_key(clean_text)
    _pending[key] = clean_text
    _pending.move_to_end(key)
    while len(_pending) > MAX_PENDING:
        _pending.popitem(last=False)
    return key


def prepare(text: str, token: str) -> PreparedAudio:
    if not verify_text(PURPOSE, text, token):
        raise InvalidSpeechToken
    clean = clean_for_speech(text)
    if not clean:
        raise InvalidSpeechToken
    key = _register(clean)
    return PreparedAudio(key=key, cached=cached_path(key) is not None, chars=len(clean))


def is_generating(key: str) -> bool:
    started = _inflight.get(key)
    if started is None:
        return False
    if time.monotonic() - started > INFLIGHT_TTL_S:
        _inflight.pop(key, None)  # a stream that never finished (client vanished before the first byte)
        return False
    return True


async def open_audio(key: str, client: ElevenLabsClient | None = None) -> AsyncIterator[bytes]:
    """Starts generation (raises TTSError before any byte if the provider refuses) and returns the byte stream."""
    text = _pending.get(key)
    if text is None:
        raise UnknownAudio
    tts = client or get_tts_client()
    _inflight[key] = time.monotonic()
    try:
        response = await tts.open_stream(text)
    except BaseException:
        _inflight.pop(key, None)
        raise
    return _stream_and_cache(key, len(text), response)


async def _stream_and_cache(key: str, chars: int, response: httpx.Response) -> AsyncIterator[bytes]:
    cache_dir = settings.tts_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    part = cache_dir / f"{key}.{uuid.uuid4().hex}.part"
    start = time.perf_counter()
    complete = False
    try:
        with part.open("wb") as fh:
            async for chunk in response.aiter_bytes():
                fh.write(chunk)
                yield chunk
        complete = True
    finally:
        await response.aclose()
        if complete and part.stat().st_size > 0:
            part.replace(cache_dir / f"{key}.mp3")
        else:
            part.unlink(missing_ok=True)
        _inflight.pop(key, None)
        logger.info(
            "tts",
            extra={"data": {"chars": chars, "complete": complete, "ms": int((time.perf_counter() - start) * 1000)}},
        )


async def resolve_audio(key: str, wait_s: float | None = None) -> Path | AsyncIterator[bytes]:
    """The cached file, or a live stream. If the same audio is already being generated (a second request
    from the audio element), wait for that file instead of paying for it twice."""
    if (path := cached_path(key)) is not None:
        return path
    if not KEY_RE.match(key):
        raise UnknownAudio
    deadline = time.monotonic() + (settings.tts_timeout_s if wait_s is None else wait_s)
    while is_generating(key) and time.monotonic() < deadline:
        await asyncio.sleep(0.3)
    if (path := cached_path(key)) is not None:
        return path
    return await open_audio(key)


async def synthesize_to_cache(text: str, client: ElevenLabsClient | None = None) -> Path | None:
    """Pre-generate audio for an answer (warmup.py), so the demo plays instantly and spends no live credits."""
    clean = clean_for_speech(text)
    if not clean:
        return None
    key = _register(clean)
    if (path := cached_path(key)) is not None:
        return path
    try:
        async for _ in await open_audio(key, client):
            pass
    except TTSError as exc:
        logger.warning("tts pre-generation failed", extra={"data": {"error": type(exc).__name__}})
        return None
    return cached_path(key)
