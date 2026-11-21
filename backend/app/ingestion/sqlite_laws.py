"""bdlaws Chronological Index (laws_of_bangladesh.sqlite) -> one document per act, one record per section.

The SQLite is opened read-only. Act-952 (Labour Act 2006) and act-1672 (its 2026 amendment) are
skipped because they are ingested from their official section-print PDFs. Each act gets an area
from title keywords (labour / land / gd / allowance), else `general`. Repealed acts stay searchable
but their title is marked [রহিত] so answers never present them as current law.
"""

import html
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

_BN = r"(?<![ঀ-৿])"  # Bangla keyword must start a word: শ্রম, not পারিশ্রমিক / আশ্রম

_AREA_RULES: list[tuple[Area, re.Pattern[str]]] = [
    (
        "labour",
        re.compile(
            rf"{_BN}(?:শ্রম|মজুর|কারখানা|ট্রেড ইউনিয়ন)|labour|labor\b|workmen|workers?\b|wages?\b|factories act|"
            r"trade unions?|industrial relations|maternity benefit|shops and establishments|employment",
            re.IGNORECASE,
        ),
    ),
    (
        "land",
        re.compile(
            rf"{_BN}(?:ভূমি|জমি|প্রজাস্বত্ব|খাস|অধিগ্রহণ|হুকুম ?দখল|অর্পিত|স্থাবর সম্পত্তি|বালুমহাল|জলমহাল)|"
            r"\blands?\b|tenancy|(?:land|state) acquisition|acquisition (?:of|and) (?:waste land|immovable|tenancy)|"
            r"requisition|immovable property|evacuee|abandoned property|survey act",
            re.IGNORECASE,
        ),
    ),
    ("gd", re.compile(rf"{_BN}পুলিশ|police", re.IGNORECASE)),
    ("allowance", re.compile(rf"{_BN}প্রতিবন্ধী|disabled persons|disability\b", re.IGNORECASE)),
]

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_SUP = re.compile(r"<sup>.*?</sup>", re.DOTALL)  # footnote reference markers: "<sup><a href="#fn-2">2</a></sup>"
_TAG = re.compile(r"<[^>]+>")
_MD_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>|])")  # "5\." -> "5."
# 38 English acts are stored as one block; their sections start a paragraph: "\n\n5\. (1) The Commission…"
_INLINE_SECTION = re.compile(r"(?m)^[ \t]*\[?([0-9]{1,3}[A-Z]?|[০-৯]{1,3}[ক-ঢ]?)\\?[.।][ \t]")
ONE_BLOCK_MIN_CHARS = 3000
ONE_BLOCK_MIN_SECTIONS = 3
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
    text = _SUP.sub("", text)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    text = _MD_ESCAPE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return normalize_text(text).strip()


def section_number(body: str) -> str | None:
    m = _SECTION_NO.match(body)
    return ascii_to_bn_digits(m.group(1)) if m else None


def split_one_block(body: str) -> list[tuple[str | None, str]]:
    """Split an act stored as a single block into (section number, text) pieces at paragraph-initial
    "N." / "N।"; the text before the first section has number None. Returns [] when it does not look
    like a sequence of sections (fewer than ONE_BLOCK_MIN_SECTIONS starts, or numbers not starting at 1)."""
    starts = list(_INLINE_SECTION.finditer(body))
    if len(starts) < ONE_BLOCK_MIN_SECTIONS or bn_to_ascii(starts[0].group(1)) not in ("1", "2"):
        return []
    pieces: list[tuple[str | None, str]] = []
    if starts[0].start() > 0:
        pieces.append((None, body[: starts[0].start()]))
    for m, nxt in zip(starts, [*starts[1:], None], strict=True):
        pieces.append((m.group(1), body[m.start() : nxt.start() if nxt else len(body)]))
    return pieces


def bn_to_ascii(number: str) -> str:
    return number.translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789"))


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
    if len(rows) <= 2 and rows and len(rows[0][2] or "") > ONE_BLOCK_MIN_CHARS:
        pieces = split_one_block(rows[0][2] or "")
        if pieces:  # the whole act was stored as its first "section": expand it into real sections
            expanded = [(number, None, text, -1 if number is None else i) for i, (number, text) in enumerate(pieces)]
            rows = [*expanded, *rows[1:]]
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
