"""Text extraction for uploaded files (admin knowledge uploads and users' personal documents).

PDF  -> per page: text layer (rebuilt rows), Bijoy conversion, or local OCR (generic_parser)
image -> local OCR (Tesseract, then EasyOCR)
"""

import io
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

from app.ingestion.generic_parser import PageReport, parse_generic_pdf
from app.ingestion.ocr_service import OcrUnavailable, PageOcrRunner
from app.ingestion.text_normalizer import normalize_text
from app.ingestion.text_repair import repair_bangla

PDF_TYPES = {"application/pdf"}
IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/tiff", "image/bmp"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}


class UnsupportedFile(ValueError):
    """User-facing Bangla message."""


@dataclass
class ExtractedText:
    pages: list[tuple[int, str]] = field(default_factory=list)
    reports: list[PageReport] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return sum(len(t) for _, t in self.pages)

    @property
    def needs_review(self) -> bool:
        return any(r.needs_review for r in self.reports)

    @property
    def methods(self) -> list[str]:
        return sorted({r.method for r in self.reports})


def file_kind(filename: str | None, content_type: str | None) -> str:
    ctype = (content_type or "").split(";")[0].strip().lower()
    suffix = Path(filename or "").suffix.lower()
    if ctype in PDF_TYPES or suffix == ".pdf":
        return "pdf"
    if ctype in IMAGE_TYPES or suffix in IMAGE_SUFFIXES:
        return "image"
    raise UnsupportedFile("শুধু PDF বা ছবি (JPG, PNG) আপলোড করা যাবে।")


def extract_pdf(path: Path, ocr: PageOcrRunner | None) -> ExtractedText:
    parsed = parse_generic_pdf(path, ocr)
    return ExtractedText(pages=parsed.pages, reports=parsed.reports)


def extract_image(data: bytes, ocr: PageOcrRunner) -> ExtractedText:
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise UnsupportedFile("ছবিটি খোলা যায়নি। অন্য ফাইল দিন।") from exc
    res = ocr.ocr_image(image, 1)
    text = normalize_text(repair_bangla(res.result.text))
    report = PageReport(1, "scanned", res.result.engine, res.result.confidence, res.needs_review, len(text))
    return ExtractedText(pages=[(1, text)] if text else [], reports=[report])


def extract_upload(data: bytes, filename: str | None, content_type: str | None) -> ExtractedText:
    """Blocking (run in a thread). OCR models are released before returning."""
    kind = file_kind(filename, content_type)
    ocr = PageOcrRunner()
    try:
        if kind == "image":
            return extract_image(data, ocr)
        with tempfile.TemporaryDirectory(prefix="adhikarai-upload-") as tmp:
            path = Path(tmp) / "upload.pdf"
            path.write_bytes(data)
            try:
                return extract_pdf(path, ocr)
            except OcrUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001
                raise UnsupportedFile("PDF ফাইলটি পড়া যায়নি। ফাইলটি ঠিক আছে কি না দেখুন।") from exc
    finally:
        ocr.release()
