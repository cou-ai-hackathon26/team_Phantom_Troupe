"""bdlaws Chronological Index (laws_of_bangladesh.sqlite) -> one document per act, one record per section.

The SQLite is opened read-only. Act-952 (Labour Act 2006) and act-1672 (its 2026 amendment) are
skipped because they are ingested from their official section-print PDFs. Each act gets an area
from title keywords (labour / land / gd / allowance), else `general`. Repealed acts stay searchable
but their title is marked [রহিত] so answers never present them as current law.
"""

import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.core.constants import Area
from app.ingestion.area_map import DocumentSpec
from app.ingestion.text_normalizer import ascii_to_bn_digits, normalize_text
from app.schemas.ingestion import SectionRecord

SKIP_SLUGS = frozenset({"act-952", "act-1672"})
BDLAWS_URL = "http://bdlaws.minlaw.gov.bd/{slug}.html"

_AREA_RULES: list[tuple[Area, re.Pattern[str]]] = [
    (
        "labour",
        re.compile(
            r"শ্রম|শ্রমিক|মজুর|কারখানা|ট্রেড ইউনিয়ন|labour|labor\b|workmen|worker|wages?\b|factor(?:y|ies)|"
            r"trade unions?|industrial relations|maternity benefit|shops and establishments|employment",
            re.IGNORECASE,
        ),
    ),
    (
        "land",
        re.compile(
            r"ভূমি|জমি|প্রজাস্বত্ব|খাস|অধিগ্রহণ|হুকুম ?দখল|অর্পিত|স্থাবর সম্পত্তি|বালুমহাল|জলমহাল|"
            r"\bland|tenancy|acquisition|requisition|immovable property|evacuee|abandoned property|survey",
            re.IGNORECASE,
        ),
    ),
    ("gd", re.compile(r"পুলিশ|police", re.IGNORECASE)),
    ("allowance", re.compile(r"প্রতিবন্ধী|ভাতা|disab", re.IGNORECASE)),
]

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_SECTION_NO = re.compile(r"^\s*\[?([0-9০-৯]{1,4}[A-Za-zক-ঢ]?)\]?\s*[।.]")
_REPEALED = "রহিত"


@dataclass(frozen=True)
class SqliteAct:
    id: int
    slug: str
    title: str
    year: int | None
    act_number: str | None
    language: str | None
    status: str | None


def area_for_title(title: str) -> Area:
    for area, pattern in _AREA_RULES:
        if pattern.search(title):
            return area
    return "general"


def clean_body(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return normalize_text(text).strip()


def section_number(body: str) -> str | None:
    m = _SECTION_NO.match(body)
    return ascii_to_bn_digits(m.group(1)) if m else None


def connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def iter_acts(conn: sqlite3.Connection, years: tuple[int, int] | None = None) -> Iterator[SqliteAct]:
    sql = "select id, slug, title, year, act_number, language, status from acts"
    args: tuple[int, ...] = ()
    if years:
        sql += " where year between ? and ?"
        args = years
    for row in conn.execute(sql + " order by year, id", args):
        act = SqliteAct(*row)
        if act.slug not in SKIP_SLUGS:
            yield act


def document_spec(act: SqliteAct, issuer: str) -> DocumentSpec:
    title = normalize_text(act.title).strip().rstrip(",")
    if (act.status or "").lower() == "repealed":
        title = f"{title} [{_REPEALED}]"
    return DocumentSpec(
        document_id=f"bdlaws-{act.slug}",
        area=area_for_title(act.title),
        title=title,
        issuer=issuer,
        parser="sqlite",
        language="en" if act.language == "en" else "bn",
        source_url=BDLAWS_URL.format(slug=act.slug),
    )


def act_records(conn: sqlite3.Connection, act: SqliteAct, spec: DocumentSpec, source_file: str) -> list[SectionRecord]:
    rows = conn.execute(
        "select section_number, heading, body, ordinal from sections where act_id = ? order by ordinal, id", (act.id,)
    ).fetchall()
    records: list[SectionRecord] = []
    seen: set[str] = set()
    for i, (number, heading, body, ordinal) in enumerate(rows, start=1):
        text = clean_body(body or "")
        if not text:
            continue
        if ordinal is not None and ordinal < 0:
            section, title = "প্রস্তাবনা", "প্রস্তাবনা"
        else:
            section = (ascii_to_bn_digits(str(number)) if number else None) or section_number(text)
            if not section or section in seen:
                section = f"অংশ {ascii_to_bn_digits(str(i))}"
            title = normalize_text(heading or "").strip() or section
        seen.add(section)
        label = section if section.startswith(("প্রস্তাবনা", "অংশ")) else f"ধারা {section}"
        records.append(
            SectionRecord(
                id=f"{spec.document_id}-s{i}",
                document_id=spec.document_id,
                area=spec.area,
                act=spec.title,
                section=section,
                title=title,
                citation=f"{spec.title}, {label}",
                text=text,
                source_url=spec.source_url,
                source_file=source_file,
            )
        )
    return records
