from fastapi import APIRouter, Depends

from app.api.dependencies import conversation_service_dep, http_error
from app.models.llm_client import LLMError, LLMNotConfigured, LLMRateLimited
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import tts_service
from app.services.conversation_service import ConversationService
from app.services.conversation_store import ConversationBusy, ConversationNotFound
from app.services.user_docs import UserDocExpired

router = APIRouter(tags=["chat"])

LLM_DOWN_TEXT = "উত্তর তৈরির সেবা এই মুহূর্তে পাওয়া যাচ্ছে না। কিছুক্ষণ পর আবার চেষ্টা করুন।"
CONVERSATION_EXPIRED_TEXT = "আগের কথোপকথনটি আর পাওয়া যাচ্ছে না (মেয়াদ শেষ)। নতুন কথোপকথন শুরু করে প্রশ্নটি আবার করুন।"
CONVERSATION_BUSY_TEXT = "আগের প্রশ্নের উত্তর এখনো তৈরি হচ্ছে। উত্তর আসার পর আবার পাঠান।"


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, service: ConversationService = Depends(conversation_service_dep)) -> ChatResponse:
    try:
        result = await service.handle(request)
    except ConversationNotFound as exc:
        raise http_error("conversation_expired", CONVERSATION_EXPIRED_TEXT, 404) from exc
    except ConversationBusy as exc:
        raise http_error("conversation_busy", CONVERSATION_BUSY_TEXT, 409) from exc
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
