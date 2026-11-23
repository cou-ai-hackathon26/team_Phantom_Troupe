"""Voice fallback endpoints (browsers without bn-BD speech recognition, e.g. Firefox)."""

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.dependencies import http_error, orchestrator_dep
from app.api.routes.chat import LLM_DOWN_TEXT
from app.models.llm_client import LLMError, LLMNotConfigured, LLMRateLimited
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import stt_service, tts_service
from app.services.audio_utils import MAX_AUDIO_BYTES, AudioError
from app.services.orchestrator import Orchestrator

router = APIRouter(prefix="/chat/voice", tags=["voice"])

NOT_UNDERSTOOD_TEXT = "কথা বোঝা যায়নি। আরেকবার স্পষ্ট করে বলুন, অথবা প্রশ্নটি লিখুন।"


class TranscriptResponse(BaseModel):
    transcript: str


class VoiceChatResponse(ChatResponse):
    transcript: str


Language = Literal["bn", "en"]


async def _read_and_transcribe(audio: UploadFile, language: str = "bn") -> str:
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    try:
        transcript = await stt_service.transcribe(data, audio.content_type, audio.filename, language)
    except AudioError as exc:
        raise HTTPException(422, detail={"code": "bad_audio", "message": str(exc)}) from exc
    except LLMRateLimited as exc:
        raise http_error("rate_limited") from exc
    except LLMNotConfigured as exc:
        raise http_error("llm_not_configured", LLM_DOWN_TEXT) from exc
    except LLMError as exc:
        raise http_error("llm_unavailable", LLM_DOWN_TEXT) from exc
    if len(transcript.strip()) < 2:
        raise HTTPException(422, detail={"code": "empty_transcript", "message": NOT_UNDERSTOOD_TEXT})
    return transcript


@router.post("/transcribe", response_model=TranscriptResponse)
async def transcribe(audio: UploadFile = File(...), language: Language = Form("bn")) -> TranscriptResponse:
    """Transcribe only — the UI puts the text in the input box for the user to check before sending."""
    return TranscriptResponse(transcript=await _read_and_transcribe(audio, language))


@router.post("", response_model=VoiceChatResponse)
async def chat_voice(
    audio: UploadFile = File(...),
    language: Language = Form("bn"),
    orchestrator: Orchestrator = Depends(orchestrator_dep),
) -> VoiceChatResponse:
    """Transcribe and answer in one call (docs/pipeline.md 13.4a)."""
    transcript = await _read_and_transcribe(audio, language)
    try:
        result = await orchestrator.run(ChatRequest(message=transcript[:2000]))
    except LLMRateLimited as exc:
        raise http_error("rate_limited") from exc
    except LLMError as exc:
        raise http_error("llm_unavailable", LLM_DOWN_TEXT) from exc
    result.speech_token = tts_service.speech_token(result.answer)
    return VoiceChatResponse(**result.model_dump(), transcript=transcript)
