"""Pydantic schemas for every LLM JSON output."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

FollowupIntent = Literal["CONTINUE", "EXPAND", "NEW_TOPIC", "CLARIFY"]
FOLLOWUP_INTENTS: tuple[str, ...] = ("CONTINUE", "EXPAND", "NEW_TOPIC", "CLARIFY")


class NormalizeOutput(BaseModel):
    """Call 1: rewrite + classify."""

    standard_bangla: str = Field(min_length=1)
    search_query: str = ""  # retrieval-oriented rewrite; empty -> standard_bangla is searched
    extra_queries: list[str] = Field(default_factory=list)  # other problems in the same question (retrieval only)
    area: Literal["land", "gd", "allowance", "labour", "general", "unknown"] = "unknown"
    in_scope: bool = True
    needs_clarification: bool = False
    clarification_question: str | None = None
    # follow-up mode only (prompts/followup_normalize.md); absent for a first question
    followup_intent: FollowupIntent | None = None
    referenced_turns: list[str] = Field(default_factory=list)  # history labels such as "T2"

    @field_validator("area", mode="before")
    @classmethod
    def _lower(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("followup_intent", mode="before")
    @classmethod
    def _intent(cls, v: object) -> object:
        """An unknown intent must not fail the whole of Call 1: treat it as missing (→ fresh retrieval)."""
        if not isinstance(v, str):
            return None
        v = v.strip().upper()
        return v if v in FOLLOWUP_INTENTS else None

    @field_validator("referenced_turns", mode="before")
    @classmethod
    def _turns(cls, v: object) -> object:
        if not isinstance(v, list):
            return []
        return [str(x).strip().strip("[]").upper() for x in v if isinstance(x, str | int)]


class AnswerOutput(BaseModel):
    """Call 2: grounded answer."""

    answer: str = ""
    used_chunk_ids: list[str] = Field(default_factory=list)
    found: bool = False
