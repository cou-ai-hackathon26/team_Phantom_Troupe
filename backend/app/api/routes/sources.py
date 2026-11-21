"""Source browsing, served from the loaded index metadata (works even if Postgres is down)."""

from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import retriever_dep
from app.core.constants import Area
from app.ingestion.bdlaws_parser import section_sort_key
from app.ingestion.indexer import document_specs
from app.schemas.source import ChunkDetail, DocumentDetail, DocumentSummary, SectionSummary
from app.services.retrieval_service import Retriever

router = APIRouter(prefix="/sources", tags=["sources"])


def _summaries(retriever: Retriever) -> dict[str, DocumentSummary]:
    specs = document_specs()
    out: dict[str, DocumentSummary] = {}
    sections: dict[str, set[str]] = {}
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
    for doc_id, secs in sections.items():
        out[doc_id].section_count = len(secs)
    return out


@router.get("", response_model=list[DocumentSummary])
async def list_documents(area: Area | None = Query(None), retriever: Retriever = Depends(retriever_dep)):
    docs = sorted(_summaries(retriever).values(), key=lambda d: (d.area, d.title))
    return [d for d in docs if area is None or d.area == area]


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: str, retriever: Retriever = Depends(retriever_dep)):
    summaries = _summaries(retriever)
    if document_id not in summaries:
        raise HTTPException(404, detail="document not found")
    grouped: OrderedDict[str, SectionSummary] = OrderedDict()
    chunks = sorted(
        (c for c in retriever.chunks.values() if c.document_id == document_id),
        key=lambda c: (section_sort_key(c.section), c.part or 0),
    )
    for c in chunks:
        sec = grouped.setdefault(
            c.section, SectionSummary(section=c.section, title=c.title, citation=c.citation, chunk_ids=[])
        )
        sec.chunk_ids.append(c.id)
    return DocumentDetail(document=summaries[document_id], sections=list(grouped.values()))


@router.get("/{chunk_id}", response_model=ChunkDetail)
async def get_chunk(chunk_id: str, retriever: Retriever = Depends(retriever_dep)):
    chunk = retriever.chunks.get(chunk_id)
    if chunk is None:
        raise HTTPException(404, detail="chunk not found")
    return ChunkDetail(chunk_id=chunk.id, **chunk.model_dump(exclude={"id", "normalized_text", "token_count"}))
