"""Admin panel API: knowledge-base documents (list, inspect, upload, delete) and ingestion jobs."""

from collections import Counter
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.core.config import settings
from app.core.constants import Area
from app.core.security import require_admin
from app.ingestion.upload_text import UnsupportedFile
from app.services import knowledge_admin as ka
from app.services.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, IndexCache, matches, paginate, search_key

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/check")
async def check(admin: str = Depends(require_admin)) -> dict[str, object]:
    return {"ok": True, "email": admin, "llm_model": settings.llm_model, "embedding_model": settings.embedding_model}


DocumentKind = Literal["all", "builtin", "uploaded"]

# search text per document, rebuilt when the cached document list is (same list object until the index changes)
_search_keys: IndexCache[dict[str, str]] = IndexCache()


@router.get("/documents")
async def documents(
    q: str | None = Query(None, max_length=100),
    area: Area | None = Query(None),
    kind: DocumentKind = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> dict:
    """One page of knowledge-base documents, plus totals over the whole knowledge base for the dashboard."""
    rows = ka.list_documents()
    keys = _search_keys.get(rows, lambda: {r.document_id: search_key(r.title, r.issuer, r.document_id) for r in rows})
    by_area: Counter[str] = Counter()
    docs_by_area: Counter[str] = Counter()
    for r in rows:
        by_area[r.area] += r.chunks
        docs_by_area[r.area] += 1
    totals = {
        "docs": len(rows),
        "chunks": sum(r.chunks for r in rows),
        "uploaded": sum(1 for r in rows if not r.builtin),
        "chunks_by_area": dict(by_area),
        "docs_by_area": dict(docs_by_area),
    }
    found = [
        r
        for r in rows
        if (area is None or r.area == area)
        and (kind == "all" or r.builtin == (kind == "builtin"))
        and matches(q, keys[r.document_id])
    ]
    sliced = paginate(found, page, page_size)
    return {
        "items": [asdict(r) for r in sliced.items],
        "total": sliced.total,
        "page": sliced.page,
        "page_size": sliced.page_size,
        "pages": sliced.pages,
        "totals": totals,
    }


@router.get("/documents/{document_id}")
async def document(
    document_id: str,
    q: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> dict:
    """A document's sections, one page at a time (large acts have hundreds of sections)."""
    rows = {d.document_id: d for d in ka.list_documents()}
    if document_id not in rows:
        raise HTTPException(404, detail="document not found")
    records = [r for r in ka.records_for(document_id) if matches(q, search_key(r.section, r.title, r.citation))]
    sliced = paginate(records, page, page_size)
    return {
        "document": asdict(rows[document_id]),
        "total": sliced.total,
        "page": sliced.page,
        "page_size": sliced.page_size,
        "pages": sliced.pages,
        "sections": [
            {
                "id": r.id,
                "section": r.section,
                "title": r.title,
                "citation": r.citation,
                "chars": len(r.text),
                "notes": len(r.notes),
                "page_start": r.page_start,
                "source_file": r.source_file,
                "text": r.text,
            }
            for r in sliced.items
        ],
    }


@router.post("/documents")
async def upload(
    file: UploadFile = File(...),
    area: Area = Form(...),
    title: str = Form(..., min_length=2, max_length=300),
    issuer: str = Form("", max_length=300),
    source_url: str | None = Form(None, max_length=1000),
    document_id: str | None = Form(None, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$"),
    parser: str = Form("auto", pattern="^(auto|bdlaws|generic)$"),
) -> dict:
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, detail={"code": "too_large", "message": f"ফাইল {settings.max_upload_mb} MB-এর বেশি।"})
    try:
        job = ka.start_upload(
            data,
            file.filename or "upload",
            file.content_type,
            area=area,
            title=title.strip(),
            issuer=issuer.strip(),
            source_url=(source_url or "").strip() or None,
            document_id=document_id or None,
            parser=parser,
        )
    except UnsupportedFile as exc:
        raise HTTPException(422, detail={"code": "unsupported", "message": str(exc)}) from exc
    return asdict(job)


@router.get("/jobs")
async def jobs() -> list[dict]:
    return [asdict(j) for j in ka.list_jobs()]


@router.get("/jobs/{job_id}")
async def job(job_id: str) -> dict:
    j = ka.get_job(job_id)
    if j is None:
        raise HTTPException(404, detail="job not found")
    return asdict(j)


@router.delete("/documents/{document_id}")
async def delete(document_id: str) -> dict:
    try:
        total = await ka.delete_document(document_id)
    except UnsupportedFile as exc:
        raise HTTPException(409, detail={"code": "builtin", "message": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(404, detail="document not found") from exc
    return {"deleted": document_id, "chunks_remaining": total}
