from typing import Literal

from pydantic import BaseModel, Field

from app.core.constants import Area, Status


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)
    area: Area | None = None
    debug: bool = False
    user_doc_id: str | None = Field(None, max_length=64)  # a personal document uploaded via /user-docs


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


class ErrorDetail(BaseModel):
    code: Literal["rate_limited", "llm_not_configured", "llm_unavailable", "index_missing"]
    message: str
