from typing import Literal

from pydantic import BaseModel, Field

from app.core.constants import Area, Status


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)
    area: Area | None = None
    debug: bool = False
    user_doc_id: str | None = Field(None, max_length=64)  # a personal document uploaded via /user-docs
    # Follow-up mode: both come from an earlier response of the same chat. No id = a new conversation.
    # The token is the conversation's secret (proof of ownership); the id alone grants nothing.
    conversation_id: str | None = Field(None, max_length=64)
    conversation_token: str | None = Field(None, max_length=128)


class Citation(BaseModel):
    marker: int  # 1-based; shown as [১], [২] … in the answer text
    kind: Literal["official", "user", "web"] = "official"  # user = own uploaded document; web = official website
    chunk_id: str
    act: str
    section: str
    title: str
    citation: str
    excerpt: str
    source_url: str | None = None
    notes: list[str] = Field(default_factory=list)  # amendment footnotes for the section


class TraceCandidate(BaseModel):
    chunk_id: str
    citation: str
    title: str
    part: int | None = None
    dense_rank: int | None
    dense_score: float | None
    bm25_rank: int | None
    bm25_score: float | None
    fused_score: float
    exact_section: bool = False


class Trace(BaseModel):
    candidates: list[TraceCandidate]
    best_dense_score: float
    llm_calls: int
    model: str | None
    gate: str  # which decision ended the pipeline
    followup_intent: str | None = None  # CONTINUE | EXPAND | NEW_TOPIC | CLARIFY; None = first question
    reused_chunk_ids: list[str] = Field(default_factory=list)  # earlier sources re-checked and reused
    dropped_reuse: dict[str, str] = Field(default_factory=dict)  # earlier source -> why it was not reused


class ChatResponse(BaseModel):
    status: Status
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    normalized_question: str
    area: str
    warnings: list[str] = Field(default_factory=list)
    trace: Trace | None = None
    latency_ms: int
    cached: bool = False
    request_id: str | None = None
    speech_token: str | None = None  # lets the 🔊 button send this answer to /tts; None = browser voice only
    conversation_id: str | None = None  # send back with the next message of this chat
    conversation_token: str | None = None  # only in the first response of a conversation; keep it with the id
    turn_id: str | None = None  # this assistant turn


class ErrorDetail(BaseModel):
    code: Literal[
        "rate_limited",
        "llm_not_configured",
        "llm_unavailable",
        "index_missing",
        "conversation_expired",
        "conversation_busy",
    ]
    message: str
