"""Deterministic gates around the LLM calls. Decisions here never call an LLM."""

from dataclasses import dataclass
from typing import Literal

from app.core.config import settings
from app.services.query_normalizer import NormalizedQuery
from app.services.retrieval_service import RetrievalResult

GateDecision = Literal["continue", "refuse", "clarify"]


@dataclass
class Gate:
    decision: GateDecision
    reason: str


def pre_retrieval_gate(query: NormalizedQuery) -> Gate:
    if not query.in_scope:
        return Gate("refuse", "out_of_scope")
    if query.needs_clarification and query.clarification_question:
        return Gate("clarify", "needs_clarification")
    return Gate("continue", "in_scope")


def retrieval_gate(result: RetrievalResult, min_score: float | None = None) -> Gate:
    """Refuse when nothing relevant was found: weak dense similarity AND no strong lexical evidence."""
    threshold = settings.retrieval_min_score if min_score is None else min_score
    if not result.candidates:
        return Gate("refuse", "no_candidates")
    if any(c.exact_section for c in result.candidates):
        return Gate("continue", "exact_section")
    if result.best_dense_score < threshold and not result.bm25_hit_in_top(3):
        return Gate("refuse", f"low_score<{threshold:.2f}")
    return Gate("continue", "score_ok")
