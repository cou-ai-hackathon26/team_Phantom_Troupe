"""Follow-up resolution: how a new message relates to the earlier turns of its conversation."""

from pydantic import BaseModel, Field

from app.schemas.llm import FollowupIntent


class FollowupResolution(BaseModel):
    """Validated in code from Call 1's output (services/followup_resolver.py); never trusted as-is."""

    is_follow_up: bool
    intent: FollowupIntent
    resolved_query: str  # standalone standard-Bangla question; the original message is kept separately
    area: str | None
    referenced_turn_ids: list[str] = Field(default_factory=list)  # assistant turn ids from the supplied history
    reuse_previous_sources: bool = False
    needs_new_retrieval: bool = True
    clarification_question: str | None = None
