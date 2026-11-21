"""Answer-level metrics. Only computed for rows a human has labelled."""

import math
from collections.abc import Sequence

from app.ingestion.text_normalizer import normalize_for_search


def includes_all(answer: str, facts: Sequence[str]) -> float:
    """Share of must_include facts present in the answer (normalized, digits unified)."""
    if not facts:
        return 0.0
    text = normalize_for_search(answer)
    return sum(1 for f in facts if normalize_for_search(f) in text) / len(facts)


def violates(answer: str, forbidden: Sequence[str]) -> bool:
    text = normalize_for_search(answer)
    return any(normalize_for_search(f) in text for f in forbidden if f.strip())


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)
