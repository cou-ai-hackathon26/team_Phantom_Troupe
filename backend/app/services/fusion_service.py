"""Reciprocal Rank Fusion: score(d) = Σ 1 / (k + rank_i(d)). Uses ranks, never raw scores."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class RankedHit(Protocol):
    chunk_id: str
    score: float
    rank: int


@dataclass
class FusedCandidate:
    chunk_id: str
    fused_score: float
    dense_rank: int | None = None
    dense_score: float | None = None  # cosine similarity
    bm25_rank: int | None = None
    bm25_score: float | None = None
    exact_section: bool = False  # query named this chunk's section ("ধারা ১৯")


def reciprocal_rank_fusion(
    dense: Sequence[RankedHit],
    sparse: Sequence[RankedHit],
    k: int = 60,
    top_n: int = 5,
    exact: Sequence[str] = (),
    title_matches: Sequence[str] = (),
) -> list[FusedCandidate]:
    """`exact` is a third ranked list (chunks whose section the query names explicitly);
    `title_matches` a fourth (retrieved chunks whose whole section title appears in the query)."""
    by_id: dict[str, FusedCandidate] = {}
    for hit in dense:
        cand = by_id.setdefault(hit.chunk_id, FusedCandidate(hit.chunk_id, 0.0))
        cand.dense_rank, cand.dense_score = hit.rank, hit.score
        cand.fused_score += 1.0 / (k + hit.rank)
    for hit in sparse:
        cand = by_id.setdefault(hit.chunk_id, FusedCandidate(hit.chunk_id, 0.0))
        cand.bm25_rank, cand.bm25_score = hit.rank, hit.score
        cand.fused_score += 1.0 / (k + hit.rank)
    for rank, chunk_id in enumerate(exact, start=1):
        cand = by_id.setdefault(chunk_id, FusedCandidate(chunk_id, 0.0))
        cand.exact_section = True
        cand.fused_score += 1.0 / (k + rank)
    for rank, chunk_id in enumerate(title_matches, start=1):
        cand = by_id.setdefault(chunk_id, FusedCandidate(chunk_id, 0.0))
        cand.fused_score += 1.0 / (k + rank)
    ordered = sorted(
        by_id.values(),
        key=lambda c: (-c.fused_score, c.dense_rank or 10_000, c.bm25_rank or 10_000),
    )
    return ordered[:top_n]
