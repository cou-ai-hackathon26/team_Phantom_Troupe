import logging
import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import log_event

router = APIRouter(tags=["feedback"])
logger = logging.getLogger("adhikarai.feedback")


class FeedbackRequest(BaseModel):
    query_log_id: str | None = None
    rating: Literal["up", "down"]
    comment: str | None = Field(None, max_length=1000)


class FeedbackResponse(BaseModel):
    ok: bool
    stored: bool


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(body: FeedbackRequest) -> FeedbackResponse:
    log_event(logger, "feedback", query_log_id=body.query_log_id, rating=body.rating)
    if settings.database_url is None:
        return FeedbackResponse(ok=True, stored=False)
    try:
        from app.db.models import Feedback
        from app.db.session import get_sessionmaker

        qid = uuid.UUID(body.query_log_id) if body.query_log_id else None
        async with get_sessionmaker()() as session:
            session.add(Feedback(query_log_id=qid, rating=body.rating, comment=body.comment))
            await session.commit()
        return FeedbackResponse(ok=True, stored=True)
    except Exception as exc:  # noqa: BLE001 - feedback must never error for the user
        logger.warning("feedback write failed", extra={"data": {"error": type(exc).__name__}})
        return FeedbackResponse(ok=True, stored=False)
