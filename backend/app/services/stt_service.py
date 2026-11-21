"""Groq Whisper fallback speech-to-text (browser speech recognition is the default path).

ffmpeg -> 16 kHz mono WAV -> whisper (language "bn" or "en" as chosen in the UI, temperature 0;
the Bangla domain-word prompt only for "bn", where it helps spelling and would bias English).
The transcript then goes through the normal Call 1 normalization like typed text.
"""

import asyncio
import logging
import re
import time

import groq

from app.core.config import settings
from app.models.llm_client import LLMError, LLMRateLimited, _retry_after_seconds, get_raw_groq_client
from app.services.audio_utils import wav_16k_mono

logger = logging.getLogger(__name__)

DOMAIN_WORDS = "নামজারি, খতিয়ান, খাজনা, জিডি, থানা, বয়স্ক ভাতা, বিধবা ভাতা, প্রতিবন্ধী ভাতা, শ্রম আইন"
# Whisper imitates the style of its prompt: a natural Bangla question in Bangla script (with the domain
# words) steers it to standard Bangla spelling better than a bare word list. Example phrasing only, no facts.
BN_PROMPT = (
    "আমি একটি প্রশ্ন করতে চাই। জমির নামজারি ও খতিয়ান, খাজনা, থানায় জিডি, বয়স্ক ভাতা, বিধবা ভাতা, "
    "প্রতিবন্ধী ভাতা, ফ্যামিলি কার্ড এবং শ্রম আইন নিয়ে আমার প্রশ্ন।"
)

_DOMAIN_SET = {w.strip() for w in DOMAIN_WORDS.split(",")}


def is_prompt_echo(text: str) -> bool:
    """Whisper hallucinates prompt words on non-speech audio (seen: a pure tone -> "প্রতিবন্ধী ভাতা")."""
    parts = [p.strip(" ।,.?!") for p in re.split(r"[,،।\n]+", text) if p.strip(" ।,.?!")]
    if parts and all(p in _DOMAIN_SET for p in parts):
        return True
    # or it repeats the prompt sentence itself
    squash = re.sub(r"[\s।,.?!]+", "", text)
    return len(squash) > 10 and squash in re.sub(r"[\s।,.?!]+", "", BN_PROMPT)


_SUFFIX_BY_TYPE = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
}


def suffix_for(content_type: str | None, filename: str | None) -> str:
    base = (content_type or "").split(";")[0].strip().lower()
    if base in _SUFFIX_BY_TYPE:
        return _SUFFIX_BY_TYPE[base]
    if filename and "." in filename:
        return "." + filename.rsplit(".", 1)[-1].lower()[:5]
    return ".webm"


STT_LANGUAGES = ("bn", "en")


async def _whisper(wav_bytes: bytes, language: str = "bn") -> str:
    client = get_raw_groq_client()
    attempt = 0
    while True:
        try:
            result = await client.audio.transcriptions.create(
                file=("audio.wav", wav_bytes),
                model=settings.stt_model,
                language=language,
                temperature=0,
                prompt=BN_PROMPT if language == "bn" else None,
                response_format="json",
            )
            return (result.text or "").strip()
        except (groq.RateLimitError, groq.InternalServerError, groq.APITimeoutError, groq.APIConnectionError) as exc:
            attempt += 1
            if attempt > settings.llm_max_retries:
                if isinstance(exc, groq.RateLimitError):
                    raise LLMRateLimited("Groq rate limit reached (whisper)") from exc
                raise LLMError(f"Whisper unavailable: {type(exc).__name__}") from exc
            await asyncio.sleep(min(_retry_after_seconds(exc) or 2 ** (attempt - 1), 8.0))
        except groq.APIStatusError as exc:
            raise LLMError(f"Whisper error {exc.status_code}") from exc


async def transcribe(
    data: bytes, content_type: str | None = None, filename: str | None = None, language: str = "bn"
) -> str:
    language = language if language in STT_LANGUAGES else "bn"
    start = time.perf_counter()
    async with wav_16k_mono(data, suffix_for(content_type, filename)) as wav:
        wav_bytes = wav.read_bytes()
    # temp files are already deleted here; only the in-memory WAV goes to Whisper
    text = (await _whisper(wav_bytes, language)).strip()
    if is_prompt_echo(text):
        logger.info("stt prompt echo discarded")
        text = ""
    logger.info(
        "stt",
        extra={
            "data": {"model": settings.stt_model, "chars": len(text), "ms": int((time.perf_counter() - start) * 1000)}
        },
    )
    return text
