"""🔊 Read an answer aloud. POST registers a signed answer and returns its audio URL; GET streams/serves it."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.dependencies import http_error
from app.models.tts_client import TTSError, TTSQuotaExceeded
from app.services import tts_service

router = APIRouter(prefix="/tts", tags=["tts"])

TTS_DOWN_TEXT = "এই মুহূর্তে উত্তরটি শোনানো যাচ্ছে না।"


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    token: str = Field(min_length=10, max_length=100)


class SpeechResponse(BaseModel):
    audio_url: str
    cached: bool
    chars: int


@router.post("", response_model=SpeechResponse)
async def prepare_speech(body: SpeechRequest) -> SpeechResponse:
    if not tts_service.is_enabled():
        raise http_error("tts_disabled", TTS_DOWN_TEXT)
    try:
        prepared = tts_service.prepare(body.text, body.token)
    except tts_service.InvalidSpeechToken as exc:
        raise HTTPException(403, detail={"code": "bad_speech_token", "message": TTS_DOWN_TEXT}) from exc
    return SpeechResponse(audio_url=f"/api/v1/tts/{prepared.key}.mp3", cached=prepared.cached, chars=prepared.chars)


@router.get("/{key}.mp3", response_model=None)
async def get_speech(key: str) -> FileResponse | StreamingResponse:
    try:
        audio = await tts_service.resolve_audio(key)
    except tts_service.UnknownAudio as exc:
        raise HTTPException(404, detail={"code": "audio_not_found", "message": TTS_DOWN_TEXT}) from exc
    except TTSQuotaExceeded as exc:
        raise http_error("tts_quota", TTS_DOWN_TEXT) from exc
    except TTSError as exc:
        raise http_error("tts_unavailable", TTS_DOWN_TEXT) from exc
    if isinstance(audio, Path):
        return FileResponse(audio, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})
    return StreamingResponse(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
