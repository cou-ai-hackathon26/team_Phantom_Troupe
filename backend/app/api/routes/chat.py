from fastapi import APIRouter, Depends

from app.api.dependencies import http_error, orchestrator_dep
from app.models.llm_client import LLMError, LLMNotConfigured, LLMRateLimited
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import tts_service
from app.services.orchestrator import Orchestrator
from app.services.user_docs import UserDocExpired

router = APIRouter(tags=["chat"])

LLM_DOWN_TEXT = "উত্তর তৈরির সেবা এই মুহূর্তে পাওয়া যাচ্ছে না। কিছুক্ষণ পর আবার চেষ্টা করুন।"


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, orchestrator: Orchestrator = Depends(orchestrator_dep)) -> ChatResponse:
    try:
        result = await orchestrator.run(request)
    except UserDocExpired as exc:
        raise http_error("user_doc_expired", "আপনার নথির মেয়াদ শেষ (১ ঘণ্টা)। নথিটি আবার যুক্ত করুন।", 404) from exc
    except LLMRateLimited as exc:
        raise http_error("rate_limited") from exc
    except LLMNotConfigured as exc:
        raise http_error("llm_not_configured", LLM_DOWN_TEXT) from exc
    except LLMError as exc:
        raise http_error("llm_unavailable", LLM_DOWN_TEXT) from exc
    result.speech_token = tts_service.speech_token(result.answer, request.user_doc_id)
    return result
