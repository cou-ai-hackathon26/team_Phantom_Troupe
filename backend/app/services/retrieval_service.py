"""Hybrid retrieval: dense (Qdrant, e5 "query: ") + BM25, fused with RRF.

Exact section references ("ধারা ১২৩", "section 123", "১২৩ ধারা") are resolved directly against chunk
metadata and placed at the top of the sparse ranking, so a section-number question always hits.
With many acts indexed, "ধারা ১২৩" exists in hundreds of them, so the exact list is limited to the act
the query names, else the acts already among the dense/BM25 hits, else the area's primary act.
"""

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import settings
from app.ingestion.text_normalizer import bn_to_ascii_digits, normalize_text, tokenize
from app.models.embedding_client import EmbeddingClient, get_embedding_client
from app.repositories.bm25_repository import BM25Index, SparseHit
from app.repositories.qdrant_repository import DenseHit, QdrantRepository
from app.schemas.ingestion import ChunkRecord
from app.services.fusion_service import FusedCandidate, reciprocal_rank_fusion

_SECTION_BEFORE = re.compile(r"(?:ধারা|section|sec\.?|s\.)\s*-?\s*([0-9০-৯]+[ক-ঞa-j]?)", re.IGNORECASE)
_SECTION_AFTER = re.compile(r"([0-9০-৯]+[ক-ঞ]?)\s*(?:নং|নম্বর)?\s*ধারা")
_LATIN_SUFFIX = dict(zip("abcdefghij", "কখগঘঙচছজঝঞ", strict=True))


def section_refs(query: str) -> list[str]:
    """Section numbers mentioned in a query, as ASCII digits + Bangla suffix (e.g. "3ক").

    "ধারা N" is matched first; "N ধারা" only on the remaining text and never for 4-digit numbers,
    so the year in "শ্রম আইন ২০০৬ ধারা ৪" is not read as a section.
    """
    text = normalize_text(query)
    found: list[tuple[int, str]] = [(m.start(), m.group(1)) for m in _SECTION_BEFORE.finditer(text)]
    rest = _SECTION_BEFORE.sub(lambda m: " " * len(m.group(0)), text)
    for m in _SECTION_AFTER.finditer(rest):
        digits = bn_to_ascii_digits(m.group(1))
        if sum(ch.isdigit() for ch in digits) < 4:
            found.append((m.start(), m.group(1)))
    refs: list[str] = []
    for _, raw in sorted(found):
        ascii_raw = bn_to_ascii_digits(raw)
        refs.append("".join(_LATIN_SUFFIX.get(ch.lower(), ch) for ch in ascii_raw))
    return refs


# where a bare "ধারা N" goes when several acts in the area have that section and none is named or hit
PRIMARY_DOCUMENTS: dict[str, str] = {"labour": "labour-act-2006"}
MAX_EXACT_DOCS = 2
_TITLE_STOPWORDS = frozenset(
    {
        "আইন", "অধ্যাদেশ", "আদেশ", "বিধিমালা", "প্রবিধানমালা", "নীতিমালা", "বাংলাদেশ", "সনের", "নং", "এর", "ধারা",
        "act", "ordinance", "order", "rules", "regulation", "regulations", "the", "of", "and", "bangladesh",
        "section", "president's",
    }
)  # fmt: skip


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

    def replace_index(self, bm25: BM25Index) -> None:
        """Swap in a rebuilt BM25 index (after an admin upload/delete) without restarting the API."""
        self.bm25 = bm25
        self._by_section = None
        self._acts = None

    _by_section: dict[str, list[str]] | None = None
    _acts: dict[str, str] | None = None

    def _sections(self) -> dict[str, list[str]]:
        """ASCII section number -> chunk ids, in index order (built once per index)."""
        if self._by_section is None:
            index: dict[str, list[str]] = {}
            for cid, chunk in self.chunks.items():
                index.setdefault(bn_to_ascii_digits(chunk.section), []).append(cid)
            self._by_section = index
            self._acts = {chunk.document_id: chunk.act for chunk in self.chunks.values()}
        return self._by_section

    def _named_documents(self, query: str, document_ids: Sequence[str]) -> list[str]:
        """Documents whose act title the query names (its distinctive title words, incl. the year)."""
        words = set(tokenize(query))
        self._sections()
        acts = self._acts or {}
        named: list[str] = []
        for doc_id in document_ids:
            act = acts.get(doc_id, "")
            distinct = set(tokenize(act.replace("[রহিত]", ""))) - _TITLE_STOPWORDS
            if distinct and len(distinct & words) >= min(2, len(distinct)):
                named.append(doc_id)
        return named

    async def dense(self, query: str, area: str | None, top_k: int) -> list[DenseHit]:
        vector = await asyncio.to_thread(self.embedder.embed_query, query)
        return await self.qdrant.search(vector, top_k=top_k, area=area)

    def exact_section_ids(self, query: str, area: str | None, hint_ids: Sequence[str] = ()) -> list[str]:
        """Chunks of the sections the query names. hint_ids: dense/BM25 hits, in rank order."""
        refs = section_refs(query)
        if not refs:
            return []
        index = self._sections()
        ids = [
            cid
            for ref in dict.fromkeys(refs)
            for cid in index.get(ref, [])
            if area is None or self.chunks[cid].area == area
        ]
        docs = list(dict.fromkeys(self.chunks[cid].document_id for cid in ids))
        if len(docs) > 1:
            keep = self._named_documents(query, docs)
            if not keep:
                hinted = (self.chunks[h].document_id for h in hint_ids if h in self.chunks)
                keep = [d for d in dict.fromkeys(hinted) if d in docs][:MAX_EXACT_DOCS]
            if not keep:
                primary = PRIMARY_DOCUMENTS.get(area) if area else None
                candidates = [primary] if primary else list(PRIMARY_DOCUMENTS.values())
                keep = [d for d in candidates if d in docs][:1]
            ids = [cid for cid in ids if self.chunks[cid].document_id in keep]
        return sorted(
            ids, key=lambda cid: (refs.index(bn_to_ascii_digits(self.chunks[cid].section)), self.chunks[cid].part or 0)
        )

    def sparse(self, query: str, area: str | None, top_k: int, hint_ids: Sequence[str] = ()) -> list[SparseHit]:
        """BM25 hits, with explicitly named sections moved to the top."""
        hits = self.bm25.search(query, top_k, area)
        exact = self.exact_section_ids(query, area, [*hint_ids, *(h.chunk_id for h in hits)])
        return self._merge_exact(hits, exact, top_k)

    @staticmethod
    def _merge_exact(hits: list[SparseHit], exact: list[str], top_k: int) -> list[SparseHit]:
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
        raw_sparse = self.bm25.search(query, sparse_k, area) if mode in ("hybrid", "bm25") else []
        hints = [h.chunk_id for h in dense_hits] + [h.chunk_id for h in raw_sparse]
        exact = self.exact_section_ids(query, area, hints) if mode != "dense" else []
        sparse_hits = self._merge_exact(raw_sparse, exact, sparse_k) if mode in ("hybrid", "bm25") else []
        pool = reciprocal_rank_fusion(dense_hits, sparse_hits, k=settings.rrf_k, top_n=top_n * 4, exact=exact)
        fused = diversify(pool, self.chunks, top_n)
        return RetrievalResult(
            query=query, area=area, candidates=fused, chunks=self.chunks, dense=dense_hits, sparse=sparse_hits
        )


def diversify(candidates: list[FusedCandidate], chunks: dict[str, ChunkRecord], top_n: int) -> list[FusedCandidate]:
    """Keep at most one chunk per section title across different documents: ~70 university acts share
    sections like "সংবিধি প্রণয়ন", and five near-identical copies would otherwise fill the top 5.
    Parts of the same section (same document) and exact section matches are never dropped."""
    picked: list[FusedCandidate] = []
    seen: dict[str, str] = {}  # title -> document_id of the first chunk with it
    for cand in candidates:
        chunk = chunks.get(cand.chunk_id)
        title = chunk.title.strip() if chunk else ""
        if chunk and title and not cand.exact_section and seen.get(title, chunk.document_id) != chunk.document_id:
            continue
        if chunk and title:
            seen.setdefault(title, chunk.document_id)
        picked.append(cand)
        if len(picked) == top_n:
            break
    return picked


def merge_results(primary: RetrievalResult, wide: RetrievalResult, top_n: int, k: int = 60) -> RetrievalResult:
    """RRF over two fused rankings (classified area first, then all areas). Ties favour the area's ranking."""
    by_id: dict[str, FusedCandidate] = {}
    score: dict[str, float] = {}
    for result in (primary, wide):
        for rank, cand in enumerate(result.candidates, start=1):
            by_id.setdefault(cand.chunk_id, cand)
            score[cand.chunk_id] = score.get(cand.chunk_id, 0.0) + 1.0 / (k + rank)
    order = sorted(by_id, key=lambda cid: -score[cid])  # stable: primary's order wins ties
    return RetrievalResult(
        query=primary.query,
        area=primary.area,
        candidates=diversify([by_id[cid] for cid in order], primary.chunks, top_n),
        chunks=primary.chunks,
        dense=[*primary.dense, *wide.dense],
        sparse=[*primary.sparse, *wide.sparse],
    )


@lru_cache
def get_retriever() -> Retriever:
    """Loads the BM25 pickle once per process (call at startup)."""
    if not settings.bm25_path.exists():
        raise FileNotFoundError(f"{settings.bm25_path} missing — run scripts/ingest_jsonl.py")
    return Retriever(BM25Index.load(settings.bm25_path), QdrantRepository(), get_embedding_client())
