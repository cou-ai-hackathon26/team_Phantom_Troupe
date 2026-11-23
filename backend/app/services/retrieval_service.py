"""Hybrid retrieval: dense (Qdrant, e5 "query: ") + BM25, fused with RRF.

Exact section references ("ধারা ১২৩", "section 123", "১২৩ ধারা", and the Constitution's
"অনুচ্ছেদ ২৭" / "article 27") are resolved directly against chunk
metadata and placed at the top of the sparse ranking, so a section-number question always hits.
With many acts indexed, "ধারা ১২৩" exists in hundreds of them, so the exact list is limited to the act
the query names, else the acts already among the dense/BM25 hits, else the area's primary act.
"""

import asyncio
import re
import unicodedata
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

_SECTION_BEFORE = re.compile(
    r"(?:ধারা|অনুচ্ছেদ|section|sec\.?|s\.|article|art\.)\s*-?\s*([0-9০-৯]+[ক-ঞa-j]?)", re.IGNORECASE
)
_SECTION_AFTER = re.compile(r"([0-9০-৯]+[ক-ঞ]?)\s*(?:নং|নম্বর)?\s*(?:ধারা|অনুচ্ছেদ)")
# "অনুচ্ছেদ"/"article" means the Constitution, whose chunks are cited as "…, অনুচ্ছেদ N"
_ARTICLE_WORD = re.compile(r"অনুচ্ছেদ|\barticle\b|\bart\.", re.IGNORECASE)
ARTICLE_LABEL = "অনুচ্ছেদ"
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


# where a bare "ধারা N" goes when several acts have that section and the query names none of them
# (before any act that merely appears among the hits: "শ্রম আইনের ধারা ১৯" means the 2006 Act, not an amendment)
PRIMARY_DOCUMENTS: dict[str, str] = {"labour": "labour-act-2006"}
MAX_EXACT_DOCS = 2
REPEALED_MARK = "[রহিত]"  # added to repealed act titles at ingestion (sqlite_laws.document_spec)
_AMENDMENT = re.compile(r"সংশোধন|amendment", re.IGNORECASE)


def _nfc_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(unicodedata.normalize("NFC", pattern), re.IGNORECASE)


# Acts that apply only to a special zone or situation: (act title pattern, query words that ask for it). They rank
# after general law unless the query uses those words. The EPZ Labour Act answered a general worker's lay-off
# question wrongly, and the land-acquisition rules' compensation-claim document list was given as the namjari list.
# (The State Acquisition and Tenancy Act 1950 is core land law, not acquisition: "হুকুমদখল"/"ভূমি অধিগ্রহণ" skip it.)
SPECIAL_SCOPE: list[tuple[re.Pattern[str], re.Pattern[str]]] = [
    (_nfc_pattern(r"ইপিজেড|\bEPZ\b|রপ্তানি প্রক্রিয়াকরণ"), _nfc_pattern(r"ইপিজেড|\bEPZ\b|রপ্তানি প্রক্রিয়াকরণ")),
    (_nfc_pattern(r"হুকুমদখল|ভূমি অধিগ্রহণ"), _nfc_pattern(r"অধিগ্রহণ|হুকুমদখল|acquisition|requisition")),
]


def special_scope(act: str, query: str) -> bool:
    """True when the act applies only to a special scope that the query does not ask about."""
    act, query = unicodedata.normalize("NFC", act), unicodedata.normalize("NFC", query)
    return any(act_re.search(act) and not query_re.search(query) for act_re, query_re in SPECIAL_SCOPE)


# Allowance programmes. A question about one never gets passages from a document about another (the
# widow policy's age and income rules answered an old-age question). Applies to allowance-area chunks.
PROGRAMMES: dict[str, re.Pattern[str]] = {
    "old_age": _nfc_pattern(r"বয়স্ক|old.?age"),
    "widow": _nfc_pattern(r"বিধবা|স্বামী নিগৃহীতা|widow"),
    "disability": _nfc_pattern(r"প্রতিবন্ধী|disab"),
}
PROGRAMME_MIN_MENTIONS = 5
PROGRAMME_MIN_SHARE = 0.6


def programmes_named(text: str) -> set[str]:
    text = unicodedata.normalize("NFC", text)
    return {name for name, pattern in PROGRAMMES.items() if pattern.search(text)}


def document_programmes(chunks: dict[str, ChunkRecord]) -> dict[str, str]:
    """document_id -> the one allowance programme it is about. Titles of many DSS PDFs are OCR noise, so a
    programme named in the act title wins, else the programme with most mentions across the document's text
    (at least PROGRAMME_MIN_MENTIONS and PROGRAMME_MIN_SHARE of all mentions). Mixed documents get none."""
    counts: dict[str, dict[str, int]] = {}
    titles: dict[str, str] = {}
    for chunk in chunks.values():
        if chunk.area != "allowance":
            continue
        titles[chunk.document_id] = chunk.act
        text = unicodedata.normalize("NFC", chunk.text)
        doc = counts.setdefault(chunk.document_id, dict.fromkeys(PROGRAMMES, 0))
        for name, pattern in PROGRAMMES.items():
            doc[name] += len(pattern.findall(text))
    out: dict[str, str] = {}
    for doc_id, doc in counts.items():
        in_title = programmes_named(titles[doc_id])
        if len(in_title) == 1:
            out[doc_id] = next(iter(in_title))
            continue
        total = sum(doc.values())
        name, top = max(doc.items(), key=lambda kv: kv[1])
        if top >= PROGRAMME_MIN_MENTIONS and top / total >= PROGRAMME_MIN_SHARE:
            out[doc_id] = name
    return out


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
    programmes: dict[str, str] = field(default_factory=dict)  # document_id -> allowance programme

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
        self._programmes = None

    _by_section: dict[str, list[str]] | None = None
    _acts: dict[str, str] | None = None
    _programmes: dict[str, str] | None = None

    def programmes(self) -> dict[str, str]:
        if self._programmes is None:
            self._programmes = document_programmes(self.chunks)
        return self._programmes

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

    def _primary_documents(self, query: str, area: str | None, docs: Sequence[str]) -> list[str]:
        """The area's primary act if it has the section; with no area, a primary act whose distinctive
        title word the query uses (e.g. "শ্রম")."""
        if area is not None:
            primary = PRIMARY_DOCUMENTS.get(area)
            return [primary] if primary in docs else []
        words = set(tokenize(query))
        acts = self._acts or {}
        return [
            doc
            for doc in PRIMARY_DOCUMENTS.values()
            if doc in docs and (set(tokenize(acts.get(doc, ""))) - _TITLE_STOPWORDS) & words
        ][:1]

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
        if _ARTICLE_WORD.search(query):
            articles = [cid for cid in ids if f", {ARTICLE_LABEL} " in self.chunks[cid].citation]
            ids = articles or ids
        docs = list(dict.fromkeys(self.chunks[cid].document_id for cid in ids))
        if len(docs) > 1:
            keep = self._named_documents(query, docs) or self._primary_documents(query, area, docs)
            if not keep:
                acts = self._acts or {}
                hinted = (self.chunks[h].document_id for h in hint_ids if h in self.chunks)
                keep = [d for d in dict.fromkeys(hinted) if d in docs and not _AMENDMENT.search(acts.get(d, ""))]
                keep = keep[:MAX_EXACT_DOCS]
            if not keep:
                primary = PRIMARY_DOCUMENTS.get(area) if area else None
                candidates = [primary] if primary else list(PRIMARY_DOCUMENTS.values())
                keep = [d for d in candidates if d in docs][:1]
            ids = [cid for cid in ids if self.chunks[cid].document_id in keep]
        return sorted(
            ids, key=lambda cid: (refs.index(bn_to_ascii_digits(self.chunks[cid].section)), self.chunks[cid].part or 0)
        )

    def title_match_ids(self, query: str, hint_ids: Sequence[str]) -> list[str]:
        """Retrieved chunks whose whole section title (minus stop words) is in the query, in hit order:
        "ছাঁটাই হলে শ্রমিক কী পায়" is about the section titled "ছাঁটাই" even when longer sections outscore it."""
        words = set(tokenize(query))
        out: list[str] = []
        for cid in dict.fromkeys(hint_ids):
            chunk = self.chunks.get(cid)
            title = set(tokenize(chunk.title)) - _TITLE_STOPWORDS if chunk else set()
            if title and title <= words:
                out.append(cid)
        return out

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
        titled = self.title_match_ids(query, hints)
        pool = reciprocal_rank_fusion(
            dense_hits, sparse_hits, k=settings.rrf_k, top_n=top_n * 4, exact=exact, title_matches=titled
        )
        fused = diversify(pool, self.chunks, top_n, query=query, programmes=self.programmes())
        return RetrievalResult(
            query=query,
            area=area,
            candidates=fused,
            chunks=self.chunks,
            dense=dense_hits,
            sparse=sparse_hits,
            programmes=self.programmes(),
        )


def diversify(
    candidates: list[FusedCandidate],
    chunks: dict[str, ChunkRecord],
    top_n: int,
    query: str = "",
    programmes: dict[str, str] | None = None,
) -> list[FusedCandidate]:
    """Keep at most one chunk per section title across different documents: ~70 university acts share
    sections like "সংবিধি প্রণয়ন", and five near-identical copies would otherwise fill the top 5.
    Parts of the same section (same document) and exact section matches are never dropped.
    Chunks of repealed acts ("[রহিত]" in the title) rank after current law, which usually carries the same text,
    and so do special-scope acts (EPZ, land acquisition) unless the query asks about that scope.
    When the query names exactly one allowance programme, chunks of documents about another programme are dropped."""
    asked = programmes_named(query)

    def other_programme(cand: FusedCandidate) -> bool:
        chunk = chunks.get(cand.chunk_id)
        if len(asked) != 1 or not chunk or chunk.area != "allowance":
            return False
        own = (programmes or {}).get(chunk.document_id)
        return own is not None and own not in asked

    def demoted(cand: FusedCandidate) -> bool:
        chunk = chunks.get(cand.chunk_id)
        if not chunk or cand.exact_section:
            return False
        return REPEALED_MARK in chunk.act or special_scope(chunk.act, query)

    candidates = [c for c in candidates if not other_programme(c)]
    candidates = [c for c in candidates if not demoted(c)] + [c for c in candidates if demoted(c)]
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
        candidates=diversify(
            [by_id[cid] for cid in order], primary.chunks, top_n, query=primary.query, programmes=primary.programmes
        ),
        chunks=primary.chunks,
        dense=[*primary.dense, *wide.dense],
        sparse=[*primary.sparse, *wide.sparse],
        programmes=primary.programmes,
    )


@lru_cache
def get_retriever() -> Retriever:
    """Loads the BM25 pickle once per process (call at startup)."""
    if not settings.bm25_path.exists():
        raise FileNotFoundError(f"{settings.bm25_path} missing — run scripts/ingest_jsonl.py")
    return Retriever(BM25Index.load(settings.bm25_path), QdrantRepository(), get_embedding_client())
