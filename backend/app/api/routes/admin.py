"""Admin panel API: knowledge-base documents (list, inspect, upload, delete) and ingestion jobs."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.core.constants import Area
from app.core.security import require_admin
from app.ingestion.upload_text import UnsupportedFile
from app.services import knowledge_admin as ka

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/check")
async def check() -> dict[str, object]:
    return {"ok": True, "llm_model": settings.llm_model, "embedding_model": settings.embedding_model}


@router.get("/documents")
async def documents() -> list[dict]:
    return [asdict(d) for d in ka.list_documents()]


@router.get("/documents/{document_id}")
async def document(document_id: str) -> dict:
    rows = {d.document_id: d for d in ka.list_documents()}
    if document_id not in rows:
        raise HTTPException(404, detail="document not found")
    records = ka.records_for(document_id)
    return {
        "document": asdict(rows[document_id]),
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
            for r in records
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
