"""Source browsing, served from the loaded index metadata (works even if Postgres is down)."""

from collections import Counter, OrderedDict
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import retriever_dep
from app.core.constants import Area
from app.ingestion.bdlaws_parser import section_sort_key
from app.ingestion.indexer import document_specs
from app.schemas.ingestion import ChunkRecord
from app.schemas.source import ChunkDetail, DocumentDetail, DocumentPage, DocumentSummary, SectionSummary
from app.services.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, IndexCache, matches, paginate, search_key
from app.services.retrieval_service import Retriever

router = APIRouter(prefix="/sources", tags=["sources"])


@dataclass
class _Catalog:
    documents: list[DocumentSummary]  # sorted by area, title
    by_id: dict[str, DocumentSummary]
    chunks_by_doc: dict[str, list[ChunkRecord]]  # sorted by section, part
    search_keys: dict[str, str]


_catalog_cache: IndexCache[_Catalog] = IndexCache()


def _build_catalog(retriever: Retriever) -> _Catalog:
    specs = document_specs()
    out: dict[str, DocumentSummary] = {}
    sections: dict[str, set[str]] = {}
    chunks_by_doc: dict[str, list[ChunkRecord]] = {}
    for chunk in retriever.chunks.values():
        spec = specs.get(chunk.document_id)
        summary = out.setdefault(
            chunk.document_id,
            DocumentSummary(
                document_id=chunk.document_id,
                title=spec.title if spec else chunk.act,
                area=chunk.area,
                issuer=spec.issuer if spec else None,
                source_url=spec.source_url if spec else chunk.source_url,
                section_count=0,
                chunk_count=0,
            ),
        )
        summary.chunk_count += 1
        sections.setdefault(chunk.document_id, set()).add(chunk.section)
        chunks_by_doc.setdefault(chunk.document_id, []).append(chunk)
    for doc_id, secs in sections.items():
        out[doc_id].section_count = len(secs)
    for chunks in chunks_by_doc.values():
        chunks.sort(key=lambda c: (section_sort_key(c.section), c.part or 0))
    documents = sorted(out.values(), key=lambda d: (d.area, d.title))
    keys = {d.document_id: search_key(d.title, d.issuer, d.document_id) for d in documents}
    return _Catalog(documents, out, chunks_by_doc, keys)


def catalog(retriever: Retriever) -> _Catalog:
    """Built once per loaded index (a scan of every chunk), reused until an upload/delete swaps the index."""
    return _catalog_cache.get(retriever.bm25, lambda: _build_catalog(retriever))


@router.get("", response_model=DocumentPage)
async def list_documents(
    area: Area | None = Query(None),
    q: str | None = Query(None, max_length=100, description="words that must all appear in the title or issuer"),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    retriever: Retriever = Depends(retriever_dep),
):
    cat = catalog(retriever)
    found = [d for d in cat.documents if matches(q, cat.search_keys[d.document_id])]
    counts = Counter(d.area for d in found)
    counts["all"] = len(found)
    sliced = paginate([d for d in found if area is None or d.area == area], page, page_size)
    return DocumentPage(
        items=sliced.items,
        total=sliced.total,
        page=sliced.page,
        page_size=sliced.page_size,
        pages=sliced.pages,
        counts=dict(counts),
    )


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: str, retriever: Retriever = Depends(retriever_dep)):
    cat = catalog(retriever)
    if document_id not in cat.by_id:
        raise HTTPException(404, detail="document not found")
    grouped: OrderedDict[str, SectionSummary] = OrderedDict()
    for c in cat.chunks_by_doc[document_id]:
        sec = grouped.setdefault(
            c.section, SectionSummary(section=c.section, title=c.title, citation=c.citation, chunk_ids=[])
        )
        sec.chunk_ids.append(c.id)
    return DocumentDetail(document=cat.by_id[document_id], sections=list(grouped.values()))


@router.get("/{chunk_id}", response_model=ChunkDetail)
async def get_chunk(chunk_id: str, retriever: Retriever = Depends(retriever_dep)):
    chunk = retriever.chunks.get(chunk_id)
    if chunk is None:
        raise HTTPException(404, detail="chunk not found")
    return ChunkDetail(chunk_id=chunk.id, **chunk.model_dump(exclude={"id", "normalized_text", "token_count"}))
