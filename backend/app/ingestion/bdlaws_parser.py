"""Parser for section-print PDFs saved from bdlaws.minlaw.gov.bd (browser "print to PDF").

Page layout (US Letter, points):
- header row  (y < 25):  "<date> Laws of Bangladesh"          -> dropped
- footer row  (y > h-25): "<source url> <page>/<pages>"        -> source_url
- centred rows at the top: act title, act number, date, chapter heading + chapter name
- left margin column (x0 < 120, narrow): the section title, wrapped over several rows
- body (x0 ≈ 150–180): section text, starting with "২।" or "[৩ক।" ("[" marks amended text)
- after the body: amendment footnotes, numbered with ASCII digits, full width from x ≈ 62
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from app.ingestion.area_map import DocumentSpec
from app.ingestion.pdf_parser import Row, extract_rows
from app.ingestion.text_normalizer import bn_to_ascii_digits, normalize_text
from app.ingestion.text_repair import repair_bangla
from app.schemas.ingestion import SectionRecord

HEADER_MAX_Y = 25.0
FOOTER_MARGIN = 25.0
MARGIN_X0_MAX = 120.0  # margin-column fragments start left of this…
MARGIN_X1_MAX = 150.0  # …and end before the body column
CENTRED_X0_MIN = 190.0
PARAGRAPH_X0_MAX = 161.0  # body rows starting left of this begin a new paragraph/clause

_URL = re.compile(r"https://bdlaws\.minlaw\.gov\.bd/[\w\-/]+?\.html")
_SECTION_START = re.compile(r"^\[?\s*([০-৯]+[ক-ঞ]?)।\s*")
_CHAPTER = re.compile(r"অধ্যায়$")
_FOOTNOTE_NUM = re.compile(r"^([0-9]{1,3})(?:\s+|$)")
_ASCII_FOOTNOTE_REF = re.compile(r"(?<![A-Za-z0-9])[0-9]{1,2}(?![0-9A-Za-z])")
_CLAUSE_START = re.compile(r"^\[?\s*\((?:[০-৯]+[ক-ঞ]?(?:-[ক-ঞ])?|[ক-ঞ]{1,2})\)")
_SECTION_SUFFIX = dict(zip("কখগঘঙচছজঝঞ", "abcdefghij", strict=True))

END_MARKERS = ("Ministry of Law, Justice and Parliamentary Affairs",)


@dataclass
class _Line:
    page: int
    y: float
    x0: float
    text: str


@dataclass
class _SectionDraft:
    number: str
    page: int
    y: float
    lines: list[_Line] = field(default_factory=list)
    title_parts: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    return normalize_text(repair_bangla(text))


def _strip_footnote_refs(text: str) -> str:
    """bdlaws body text uses Bangla digits only; stray ASCII digits are footnote markers."""
    return re.sub(r"\s{2,}", " ", _ASCII_FOOTNOTE_REF.sub("", text)).strip()


def _is_margin(x0: float, x1: float) -> bool:
    return x0 < MARGIN_X0_MAX and x1 < MARGIN_X1_MAX


def section_slug(number_bn: str) -> str:
    ascii_num = bn_to_ascii_digits(number_bn)
    return "".join(_SECTION_SUFFIX.get(ch, ch) for ch in ascii_num)


@dataclass
class ParsedBdlaws:
    act: str | None = None
    chapter: str | None = None
    source_url: str | None = None
    preamble: list[str] = field(default_factory=list)
    sections: list[_SectionDraft] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    page_count: int = 0


def parse_bdlaws_pdf(path: str | Path) -> ParsedBdlaws:
    out = ParsedBdlaws()
    stream: list[tuple[_Line, bool]] = []  # (line, is_margin)
    with pymupdf.open(path) as doc:
        out.page_count = doc.page_count
        for page in doc:
            h = page.rect.height
            pno = page.number + 1
            for row in extract_rows(page):
                if row.y_mid > h - FOOTER_MARGIN and out.source_url is None:
                    m = _URL.search(row.text)
                    if m:
                        out.source_url = m.group(0)

            def in_body_area(r: Row, height: float = h) -> bool:
                return HEADER_MAX_Y < r.y_mid < height - FOOTER_MARGIN

            for row in extract_rows(page, keep=_is_margin):
                if in_body_area(row):
                    stream.append((_Line(pno, row.y_mid, row.x0, row.text), True))
            for row in extract_rows(page, keep=lambda x0, x1: not _is_margin(x0, x1)):
                if in_body_area(row):
                    stream.append((_Line(pno, row.y_mid, row.x0, row.text), False))

    stream.sort(key=lambda item: (item[0].page, item[0].y, item[0].x0))
    _assemble(out, stream)
    return out


def _is_section_start(line: _Line) -> bool:
    return line.x0 < CENTRED_X0_MIN and _SECTION_START.match(_strip_footnote_refs(_clean(line.text))) is not None


def _assemble(out: ParsedBdlaws, stream: list[tuple[_Line, bool]]) -> None:
    seen_chapter = False
    in_footnotes = False
    chapter_parts: list[str] = []
    current: _SectionDraft | None = None
    pending_titles: list[str] = []
    footnote: list[str] = []

    def flush_footnote() -> None:
        if footnote:
            out.notes.append(_strip_double_spaces(_clean(" ".join(footnote))))
            footnote.clear()

    for i, (line, is_margin) in enumerate(stream):
        text = line.text.strip()
        if not text or any(marker in text for marker in END_MARKERS) or text.startswith("Copyright"):
            continue
        cleaned = _clean(text)

        # ---- title block: act, act number, date, chapter heading + chapter name; then preamble
        if not seen_chapter:
            if line.x0 >= CENTRED_X0_MIN:
                if out.act is None:
                    out.act = cleaned
                elif _CHAPTER.search(cleaned):
                    chapter_parts = [cleaned]
                elif chapter_parts:
                    chapter_parts.append(cleaned)
                    out.chapter = " — ".join(chapter_parts)
                    seen_chapter = True
            elif not is_margin:
                out.preamble.append(_strip_footnote_refs(cleaned))
            continue

        # ---- amendment footnotes: introduced by an ASCII number in the margin zone; run to the end
        number = _FOOTNOTE_NUM.match(text) if line.x0 < MARGIN_X0_MAX else None
        if number:
            in_footnotes = True
            flush_footnote()
            rest = text[number.end() :].strip()
            if rest:
                footnote.append(rest)
            continue
        if in_footnotes:
            footnote.append(text)
            continue

        # ---- margin column: section title (may sit a few points above its section's first row)
        if is_margin:
            nxt = next((ln for ln, m in stream[i + 1 :] if not m), None)
            starts_soon = (
                nxt is not None and nxt.page == line.page and abs(nxt.y - line.y) < 12 and _is_section_start(nxt)
            )
            if current is None or starts_soon:
                pending_titles.append(cleaned)
            else:
                current.title_parts.append(cleaned)
            continue

        # ---- body
        body = _strip_footnote_refs(cleaned)
        if _is_section_start(line):
            number_match = _SECTION_START.match(body)
            assert number_match is not None
            current = _SectionDraft(number=number_match.group(1), page=line.page, y=line.y)
            current.title_parts.extend(pending_titles)
            pending_titles.clear()
            out.sections.append(current)
        if current is not None:
            current.lines.append(_Line(line.page, line.y, line.x0, body))
    flush_footnote()


def _strip_double_spaces(text: str) -> str:
    return re.sub(r"[ ]{2,}", " ", text).strip()


def _body_text(lines: list[_Line]) -> str:
    paragraphs: list[str] = []
    for line in lines:
        starts_clause = _CLAUSE_START.match(line.text) is not None
        if not paragraphs or line.x0 < PARAGRAPH_X0_MAX or starts_clause:
            paragraphs.append(line.text)
        else:
            paragraphs[-1] += " " + line.text
    return "\n".join(paragraphs)


def to_section_records(parsed: ParsedBdlaws, spec: DocumentSpec, source_file: str) -> list[SectionRecord]:
    act = parsed.act or spec.title
    records: list[SectionRecord] = []
    if parsed.preamble:
        records.append(
            SectionRecord(
                id=f"{spec.document_id}-preamble",
                document_id=spec.document_id,
                area=spec.area,
                act=act,
                chapter=None,
                section="প্রস্তাবনা",
                title="প্রস্তাবনা",
                citation=f"{act}, প্রস্তাবনা",
                text="\n".join(parsed.preamble),
                source_url=parsed.source_url,
                source_file=source_file,
                page_start=1,
                page_end=1,
            )
        )
    for i, sec in enumerate(parsed.sections):
        is_last = i == len(parsed.sections) - 1
        records.append(
            SectionRecord(
                id=f"{spec.document_id}-s{section_slug(sec.number)}",
                document_id=spec.document_id,
                area=spec.area,
                act=act,
                chapter=parsed.chapter,
                section=sec.number,
                title=" ".join(sec.title_parts).strip() or f"ধারা {sec.number}",
                citation=f"{act}, ধারা {sec.number}",
                text=_body_text(sec.lines),
                # bdlaws prints one section per file, so the file's footnotes belong to its last section
                notes=parsed.notes if is_last else [],
                source_url=parsed.source_url,
                source_file=source_file,
                page_start=sec.page,
                page_end=sec.lines[-1].page if sec.lines else sec.page,
            )
        )
    return records
