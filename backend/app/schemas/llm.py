"""Pydantic schemas for every LLM JSON output."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class NormalizeOutput(BaseModel):
    """Call 1: rewrite + classify."""

    standard_bangla: str = Field(min_length=1)
    area: Literal["land", "gd", "allowance", "labour", "general", "unknown"] = "unknown"
    in_scope: bool = True
    needs_clarification: bool = False
    clarification_question: str | None = None

    @field_validator("area", mode="before")
    @classmethod
    def _lower(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v


class AnswerOutput(BaseModel):
    """Call 2: grounded answer."""

    answer: str = ""
    used_chunk_ids: list[str] = Field(default_factory=list)
    found: bool = False
