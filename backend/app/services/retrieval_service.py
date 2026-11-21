"""Hybrid retrieval: dense (Qdrant, e5 "query: ") + BM25, fused with RRF.

Exact section references ("ধারা ১২৩", "section 123", "১২৩ ধারা") are resolved directly against chunk
metadata and placed at the top of the sparse ranking, so a section-number question always hits.
"""

import asyncio
import re
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import settings
from app.ingestion.text_normalizer import bn_to_ascii_digits, normalize_text
from app.models.embedding_client import EmbeddingClient, get_embedding_client
from app.repositories.bm25_repository import BM25Index, SparseHit
from app.repositories.qdrant_repository import DenseHit, QdrantRepository
from app.schemas.ingestion import ChunkRecord
from app.services.fusion_service import FusedCandidate, reciprocal_rank_fusion

_SECTION_REF = re.compile(
    r"(?:ধারা|section|sec\.?|s\.)\s*-?\s*([0-9০-৯]+[ক-ঞa-j]?)|([0-9০-৯]+[ক-ঞ]?)\s*(?:নং|নম্বর)?\s*ধারা",
    re.IGNORECASE,
)
_LATIN_SUFFIX = dict(zip("abcdefghij", "কখগঘঙচছজঝঞ", strict=True))


def section_refs(query: str) -> list[str]:
    """Section numbers mentioned in a query, as ASCII digits + Bangla suffix (e.g. "3ক")."""
    refs: list[str] = []
    for m in _SECTION_REF.finditer(normalize_text(query)):
        raw = bn_to_ascii_digits(m.group(1) or m.group(2))
        refs.append("".join(_LATIN_SUFFIX.get(ch.lower(), ch) for ch in raw))
    return refs


@dataclass
class RetrievalResult:
    query: str
    area: str | None
    candidates: list[FusedCandidate]
    chunks: dict[str, ChunkRecord]
    dense: list[DenseHit] = field(default_factory=list)
    sparse: list[SparseHit] = field(default_factory=list)

    @property
    def best_dense_score(self) -> float:
        return max((h.score for h in self.dense), default=0.0)

    def bm25_hit_in_top(self, n: int) -> bool:
        return any(c.bm25_rank is not None and c.bm25_rank <= n for c in self.candidates)

    def top_chunks(self) -> list[ChunkRecord]:
        return [self.chunks[c.chunk_id] for c in self.candidates if c.chunk_id in self.chunks]


class Retriever:
    def __init__(
        self,
        bm25: BM25Index,
        qdrant: QdrantRepository,
        embedder: EmbeddingClient,
    ) -> None:
        self.bm25 = bm25
        self.qdrant = qdrant
        self.embedder = embedder

    @property
    def chunks(self) -> dict[str, ChunkRecord]:
        return self.bm25.chunks

    async def dense(self, query: str, area: str | None, top_k: int) -> list[DenseHit]:
        vector = await asyncio.to_thread(self.embedder.embed_query, query)
        return await self.qdrant.search(vector, top_k=top_k, area=area)

    def exact_section_ids(self, query: str, area: str | None) -> list[str]:
        refs = section_refs(query)
        if not refs:
            return []
        ids = [
            cid
            for cid, chunk in self.chunks.items()
            if bn_to_ascii_digits(chunk.section) in refs and (area is None or chunk.area == area)
        ]
        return sorted(
            ids, key=lambda cid: (refs.index(bn_to_ascii_digits(self.chunks[cid].section)), self.chunks[cid].part or 0)
        )

    def sparse(self, query: str, area: str | None, top_k: int) -> list[SparseHit]:
        """BM25 hits, with explicitly named sections moved to the top."""
        hits = self.bm25.search(query, top_k, area)
        exact = self.exact_section_ids(query, area)
        if not exact:
            return hits
        top_score = hits[0].score if hits else 1.0
        merged = [SparseHit(cid, top_score, 0) for cid in exact] + [h for h in hits if h.chunk_id not in exact]
        return [SparseHit(h.chunk_id, h.score, i) for i, h in enumerate(merged[:top_k], start=1)]

    async def retrieve(
        self,
        query: str,
        area: str | None = None,
        dense_k: int | None = None,
        sparse_k: int | None = None,
        top_n: int | None = None,
        mode: str = "hybrid",  # hybrid | dense | bm25 (for ablations)
    ) -> RetrievalResult:
        dense_k = dense_k or settings.dense_top_k
        sparse_k = sparse_k or settings.bm25_top_k
        top_n = top_n or settings.fused_top_k
        dense_hits = await self.dense(query, area, dense_k) if mode in ("hybrid", "dense") else []
        sparse_hits = self.sparse(query, area, sparse_k) if mode in ("hybrid", "bm25") else []
        exact = self.exact_section_ids(query, area) if mode != "dense" else []
        fused = reciprocal_rank_fusion(dense_hits, sparse_hits, k=settings.rrf_k, top_n=top_n, exact=exact)
        return RetrievalResult(
            query=query, area=area, candidates=fused, chunks=self.chunks, dense=dense_hits, sparse=sparse_hits
        )


@lru_cache
def get_retriever() -> Retriever:
    """Loads the BM25 pickle once per process (call at startup)."""
    if not settings.bm25_path.exists():
        raise FileNotFoundError(f"{settings.bm25_path} missing — run scripts/ingest_jsonl.py")
    return Retriever(BM25Index.load(settings.bm25_path), QdrantRepository(), get_embedding_client())
