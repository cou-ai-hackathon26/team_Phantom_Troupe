"""Evidence continuity for follow-ups: reload earlier cited sources by canonical id, re-check them, merge.

An earlier citation is reused only if ALL of these hold:
1. it was an official chunk (web passages are re-searched, personal-document passages are never stored);
2. the chunk still exists in the live index (an admin may have deleted or replaced the document);
3. its text is unchanged since it was cited (same content hash);
4. its act is not repealed ("[রহিত]");
5. it is relevant to the resolved follow-up: it is among the fresh retrieval results, or it shares a
   distinctive term (high BM25 IDF) with the resolved question.
Passages always come from the live index, never from earlier answer text. Whether a reused passage really
supports the new answer is then decided by Call 2 and the citation validator, as for any passage.
"""

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from app.repositories.bm25_repository import BM25Index
from app.schemas.ingestion import ChunkRecord
from app.services.conversation_store import SourceRef
from app.services.fusion_service import FusedCandidate
from app.services.retrieval_service import REPEALED_MARK

REUSE_MIN_TERM_IDF = 1.5  # a term in fewer than ~18% of chunks counts as distinctive
REUSED = "reused"


def source_version(chunk: ChunkRecord) -> str:
    """Content hash stored with a citation; a different hash later means the chunk was edited or replaced."""
    return hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()[:16]


def retrieval_method(candidate: FusedCandidate) -> str:
    if candidate.exact_section:
        return "exact"
    if candidate.dense_rank is not None and candidate.bm25_rank is not None:
        return "hybrid"
    return "dense" if candidate.dense_rank is not None else "bm25"


@dataclass
class ReuseReport:
    chunks: list[ChunkRecord] = field(default_factory=list)  # verified, in citation order
    dropped: dict[str, str] = field(default_factory=dict)  # chunk id -> reason


def reusable_sources(
    sources: Iterable[SourceRef],
    index: BM25Index,
    query: str,
    fresh_ids: Sequence[str],
    limit: int,
) -> ReuseReport:
    """Re-verify earlier citations (most relevant turn first) and keep at most `limit` of them."""
    report = ReuseReport()
    seen: set[str] = set()
    fresh = set(fresh_ids)
    for src in sources:
        if src.chunk_id in seen:
            continue
        seen.add(src.chunk_id)
        if src.kind != "official":
            report.dropped[src.chunk_id] = "not_official"
            continue
        chunk = index.chunks.get(src.chunk_id)
        if chunk is None:
            report.dropped[src.chunk_id] = "missing"
        elif src.source_version is not None and source_version(chunk) != src.source_version:
            report.dropped[src.chunk_id] = "changed"
        elif REPEALED_MARK in chunk.act:
            report.dropped[src.chunk_id] = "repealed"
        elif chunk.id not in fresh and index.shared_term_weight(query, chunk.id, REUSE_MIN_TERM_IDF) <= 0:
            report.dropped[src.chunk_id] = "not_relevant"
        elif len(report.chunks) >= limit:
            report.dropped[src.chunk_id] = "over_limit"
        else:
            report.chunks.append(chunk)
    return report


def merge_evidence(
    reused: Sequence[ChunkRecord],
    fresh: Sequence[ChunkRecord],
    fresh_methods: Mapping[str, str],
    limit: int,
) -> list[tuple[ChunkRecord, str]]:
    """Reused passages first (the conversation's subject), then fresh ones; deduplicated by chunk id and capped
    so the prompt stays as large as without follow-up. Each passage keeps how it was obtained."""
    out: list[tuple[ChunkRecord, str]] = []
    seen: set[str] = set()
    for chunk, method in [*((c, REUSED) for c in reused), *((c, fresh_methods.get(c.id, "hybrid")) for c in fresh)]:
        if chunk.id in seen:
            continue
        seen.add(chunk.id)
        out.append((chunk, method))
        if len(out) >= limit:
            break
    return out
