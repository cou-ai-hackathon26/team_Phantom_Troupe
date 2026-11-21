"""Scraped markdown guides (data/DataSet/**/*.md) -> section records, one per heading.

These files mix file-inventory tables (links to the PDFs, sizes) with scraped portal text inside
``` blocks. Inventory rows, image/link markup and emphasis are dropped; prose, list items, content
tables and code-block text are kept. Sections shorter than MIN_CHARS are merged into the next one.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.ingestion.area_map import DocumentSpec
from app.ingestion.text_normalizer import ascii_to_bn_digits, normalize_text
from app.schemas.ingestion import SectionRecord

MIN_CHARS = 80
TITLE_MAX = 90

_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$")
_SOURCE = re.compile(r"(?:উৎস|Source)\s*[:：]\**\s*<?(https?://[^\s>)`]+)", re.IGNORECASE)
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_INVENTORY = re.compile(r"\.(?:pdf|md|html|sqlite|jsonl|csv|json)\b|\bbytes\b|\d+(?:\.\d+)?\s*(?:KB|MB|GB)\b", re.I)
_TABLE_RULE = re.compile(r"^\|?\s*:?-{3,}")


@dataclass
class MdSection:
    heading: str
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


@dataclass
class ParsedMarkdown:
    title: str
    source_url: str | None
    sections: list[MdSection]


def _clean_line(line: str) -> str:
    line = _IMAGE.sub("", line)
    line = _LINK.sub(r"\1", line)
    line = line.replace("**", "").replace("__", "").replace("`", "")
    return line.strip()


def parse_markdown(text: str) -> ParsedMarkdown:
    title = ""
    m = _SOURCE.search(text)
    source_url = m.group(1).rstrip(".,") if m else None
    sections: list[MdSection] = [MdSection(heading="")]
    in_code = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            h = _HEADING.match(stripped)
            if h:
                heading = _clean_line(h.group(2))
                if not title and len(h.group(1)) == 1:
                    title = heading
                sections.append(MdSection(heading=heading))
                continue
            if stripped.startswith("|"):
                if _TABLE_RULE.match(stripped) or _INVENTORY.search(stripped):
                    continue  # table rule, or a row of the file inventory
                cells = [_clean_line(c) for c in stripped.strip("|").split("|")]
                stripped = " | ".join(c for c in cells if c)
            elif _INVENTORY.search(stripped) and ("](" in stripped or stripped.startswith(("-", "*"))):
                continue  # "- [file.pdf](./file.pdf) - description (123 bytes)"
            if _SOURCE.search(stripped):
                continue
        line = _clean_line(stripped)
        if line:
            sections[-1].lines.append(line)
    # merge tiny sections forward so every record carries enough context to be retrievable
    merged: list[MdSection] = []
    carry: MdSection | None = None
    for sec in sections:
        if carry is not None:
            sec = MdSection(heading=sec.heading or carry.heading, lines=[carry.heading, *carry.lines, *sec.lines])
            sec.lines = [ln for ln in sec.lines if ln]
            carry = None
        if len(sec.text) < MIN_CHARS:
            carry = sec
            continue
        merged.append(sec)
    if carry is not None and carry.text:
        if merged:
            merged[-1].lines += [carry.heading, *carry.lines]
        else:
            merged.append(carry)
    return ParsedMarkdown(title=title, source_url=source_url, sections=merged)


def _short(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= TITLE_MAX else text[:TITLE_MAX].rsplit(" ", 1)[0] + " …"


def to_section_records(parsed: ParsedMarkdown, spec: DocumentSpec, source_file: str) -> list[SectionRecord]:
    records: list[SectionRecord] = []
    for i, sec in enumerate(parsed.sections, start=1):
        text = normalize_text(sec.text)
        if not text:
            continue
        part = f"অংশ {ascii_to_bn_digits(str(i))}"
        records.append(
            SectionRecord(
                id=f"{spec.document_id}-h{i}",
                document_id=spec.document_id,
                area=spec.area,
                act=spec.title,
                section=part,
                title=_short(normalize_text(sec.heading)) or part,
                citation=f"{spec.title}, {part}",
                text=text,
                source_url=spec.source_url,
                source_file=source_file,
            )
        )
    return records


def read_markdown(path: Path) -> ParsedMarkdown:
    return parse_markdown(path.read_text(encoding="utf-8", errors="replace"))
