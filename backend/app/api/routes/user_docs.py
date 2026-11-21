"""Personal document upload for a question. Text stays in memory only; nothing is indexed or stored."""

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.ingestion.ocr_service import OcrUnavailable
from app.ingestion.upload_text import UnsupportedFile, extract_upload
from app.services.user_docs import UserDoc, UserDocExpired, get_user_doc_store

router = APIRouter(prefix="/user-docs", tags=["user documents"])


class UserDocInfo(BaseModel):
    doc_id: str
    filename: str
    pages: int
    chars: int
    methods: list[str]
    needs_review: bool
    preview: str
    expires_at: str


def _info(doc: UserDoc) -> UserDocInfo:
    first = doc.passages[0].text if doc.passages else ""
    return UserDocInfo(
        doc_id=doc.id,
        filename=doc.filename,
        pages=doc.pages,
        chars=doc.chars,
        methods=doc.methods,
        needs_review=doc.needs_review,
        preview=first[:300],
        expires_at=datetime.fromtimestamp(doc.expires_at, UTC).isoformat(timespec="seconds"),
    )


@router.post("", response_model=UserDocInfo)
async def upload(file: UploadFile = File(...)) -> UserDocInfo:
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, detail={"code": "too_large", "message": f"ফাইল {settings.max_upload_mb} MB-এর বেশি।"})
    try:
        extracted = await asyncio.to_thread(extract_upload, data, file.filename, file.content_type)
    except UnsupportedFile as exc:
        raise HTTPException(422, detail={"code": "unsupported", "message": str(exc)}) from exc
    except OcrUnavailable as exc:
        raise HTTPException(
            503, detail={"code": "ocr_unavailable", "message": "এই ফাইল পড়তে OCR দরকার, কিন্তু সার্ভারে OCR চালু নেই।"}
        ) from exc
    finally:
        del data
    if extracted.chars < 10:
        raise HTTPException(
            422, detail={"code": "no_text", "message": "নথি থেকে কোনো লেখা পড়া যায়নি। স্পষ্ট ছবি বা PDF দিন।"}
        )
    doc = get_user_doc_store().add(
        file.filename or "document", extracted.pages, extracted.methods, extracted.needs_review
    )
    return _info(doc)


@router.get("/{doc_id}", response_model=UserDocInfo)
async def info(doc_id: str) -> UserDocInfo:
    try:
        return _info(get_user_doc_store().get(doc_id))
    except UserDocExpired as exc:
        raise HTTPException(404, detail={"code": "expired", "message": "নথির মেয়াদ শেষ। আবার আপলোড করুন।"}) from exc


@router.delete("/{doc_id}")
async def remove(doc_id: str) -> dict[str, bool]:
    return {"deleted": get_user_doc_store().delete(doc_id)}
