"""Retrieval metrics over ranked chunk-id lists."""

from collections.abc import Sequence


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Proportion of the relevant ids that appear in the top k."""
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def hit_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    return 1.0 if set(ranked[:k]) & relevant else 0.0


def reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float:
    for i, cid in enumerate(ranked, start=1):
        if cid in relevant:
            return 1.0 / i
    return 0.0


def section_level(chunk_ids: Sequence[str]) -> list[str]:
    """Map chunk ids to section ids ("…-s2-p3" -> "…-s2"), de-duplicated in rank order.
    Lets a gold label name a section while the index holds several parts of it."""
    seen: list[str] = []
    for cid in chunk_ids:
        base = cid.rsplit("-p", 1)[0] if cid.rsplit("-p", 1)[-1].isdigit() else cid
        if base not in seen:
            seen.append(base)
    return seen
