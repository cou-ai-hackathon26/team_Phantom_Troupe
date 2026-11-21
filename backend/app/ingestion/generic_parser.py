"""Generic PDF -> section records (citizen charters, policies, circulars…).

Each page is classified as text / legacy-font / scanned and turned into Unicode text:
- text:    rebuilt visual rows (pdf_parser) + repair
- legacy:  Bijoy -> Unicode; if the conversion is untrustworthy, OCR the page instead
- scanned: local OCR (tesseract, then the second engine)
One record per page keeps citations page-precise; the chunker splits long pages at clause lines.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pymupdf

from app.ingestion.area_map import DocumentSpec
from app.ingestion.legacy_font_converter import convert_bijoy
from app.ingestion.ocr_service import OcrUnavailable, PageOcrRunner
from app.ingestion.pdf_parser import extract_rows
from app.ingestion.text_normalizer import ascii_to_bn_digits, normalize_text
from app.ingestion.text_repair import looks_like_legacy_bijoy, repair_bangla
from app.schemas.ingestion import SectionRecord

logger = logging.getLogger(__name__)

PageKind = Literal["text", "legacy", "scanned"]
MIN_TEXT_CHARS = 25
TITLE_MAX = 90
MIN_OCR_QUALITY = 0.5  # share of tokens that look like real words; below this an OCR page is noise

_BN_LETTER = re.compile(r"[\u0985-\u09B9\u09CE\u09DC-\u09DF]")
_EN_WORD = re.compile(r"^[A-Za-z][a-z]*[aeiouy][a-z]*$|^[A-Z]{2,}$", re.IGNORECASE)
_NUMBER = re.compile(r"^[0-9০-৯][0-9০-৯.,/:%-]*$")


def ocr_quality(text: str) -> float:
    """Length-weighted share of characters in plausible words (0..1); numbers are ignored.

    Tables and stamps scanned at low quality come out as 'esi em SS dou} a shee' — mostly 1-3 letter
    fragments — which scores low; real Bangla or English prose is dominated by longer words and scores high.
    """
    good = total = 0
    for raw in text.split():
        t = raw.strip(".,;:!?()[]'\"“”‘’।|-–—")
        if not t or _NUMBER.match(t):
            continue
        total += len(t)
        if len(_BN_LETTER.findall(t)) >= 2 or (len(t) >= 3 and _EN_WORD.match(t)):
            good += len(t)
    return good / total if total else 0.0


def classify_page(text: str, has_images: bool) -> PageKind:
    visible = sum(1 for ch in text if not ch.isspace())
    if visible < MIN_TEXT_CHARS:
        return "scanned" if has_images or visible == 0 else "text"
    if looks_like_legacy_bijoy(text):
        return "legacy"
    return "text"


@dataclass
class PageReport:
    page_number: int
    kind: PageKind
    method: str  # pymupdf | bijoy | tesseract | easyocr | skipped
    confidence: float | None = None
    needs_review: bool = False
    chars: int = 0


@dataclass
class ParsedPdf:
    pages: list[tuple[int, str]] = field(default_factory=list)
    reports: list[PageReport] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return any(r.needs_review for r in self.reports)


def parse_generic_pdf(path: str | Path, ocr: PageOcrRunner | None = None, drop_garbage: bool = False) -> ParsedPdf:
    """drop_garbage: discard OCR pages whose ocr_quality() is below MIN_OCR_QUALITY (bulk ingestion)."""
    out = ParsedPdf()
    with pymupdf.open(path) as doc:
        for page in doc:
            pno = page.number + 1
            raw = "\n".join(r.text for r in extract_rows(page))
            kind = classify_page(raw, has_images=bool(page.get_images()))
            report = PageReport(pno, kind, "pymupdf")
            text = raw
            if kind == "legacy":
                conv = convert_bijoy(raw)
                text, report.method = conv.text, "bijoy"
                if not conv.trustworthy:
                    report.needs_review = True
                    kind = "scanned"  # fall through to OCR when available
            if kind == "scanned":
                if ocr is None:
                    report.method, report.needs_review, text = "skipped", True, ""
                else:
                    try:
                        res = ocr.ocr_page(page)
                        text, report.method = res.result.text, res.result.engine
                        report.confidence, report.needs_review = res.result.confidence, res.needs_review
                    except OcrUnavailable as exc:
                        logger.warning("ocr unavailable", extra={"data": {"page": pno, "error": str(exc)}})
                        report.needs_review = True
                        report.method = report.method if report.method == "bijoy" else "skipped"
                        text = text if report.method == "bijoy" else ""
            text = normalize_text(repair_bangla(text))
            if (
                drop_garbage
                and report.method not in ("pymupdf", "bijoy")
                and text
                and ocr_quality(text) < MIN_OCR_QUALITY
            ):
                report.method, report.needs_review, text = f"{report.method}+dropped", True, ""
            report.chars = len(text)
            out.reports.append(report)
            if text:
                out.pages.append((pno, text))
    return out


def _page_title(text: str) -> str:
    first = next((ln.strip() for ln in text.splitlines() if len(ln.strip()) > 3), "")
    return first if len(first) <= TITLE_MAX else first[:TITLE_MAX].rsplit(" ", 1)[0] + " …"


def to_section_records(parsed: ParsedPdf, spec: DocumentSpec, source_file: str) -> list[SectionRecord]:
    records: list[SectionRecord] = []
    for pno, text in parsed.pages:
        page_bn = ascii_to_bn_digits(str(pno))
        records.append(
            SectionRecord(
                id=f"{spec.document_id}-p{pno}",
                document_id=spec.document_id,
                area=spec.area,
                act=spec.title,
                chapter=None,
                section=f"পৃষ্ঠা {page_bn}",
                title=_page_title(text) or f"পৃষ্ঠা {page_bn}",
                citation=f"{spec.title}, পৃষ্ঠা {page_bn}",
                text=text,
                source_url=spec.source_url,
                source_file=source_file,
                page_start=pno,
                page_end=pno,
            )
        )
    return records
