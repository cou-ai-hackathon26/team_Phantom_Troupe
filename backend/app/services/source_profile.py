"""What kind of source a passage comes from, using only metadata the repository actually has.

Evidence used: the dataset step and parser each document was ingested from (data/dataset_registry.json), its
title (type words such as আইন/বিধিমালা/নীতিমালা, the year printed in it, "(সংশোধন)", "[রহিত]") and the
compiled-guide marker. Never the domain name. Fields the data cannot support stay unknown: there are no
effective dates, no verified "active" status (a document not marked repealed is "unknown", not "active"),
and no supersession records except an amendment act naming the act it amends.
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from app.core.config import DATA_DIR
from app.ingestion.text_normalizer import bn_to_ascii_digits
from app.services.retrieval_service import REPEALED_MARK

REGISTRY_PATH = DATA_DIR / "dataset_registry.json"
COMPILED_STEP = "md-guides"
COMPILED_MARK = "(সংকলিত"

TYPE_LABELS: dict[str, str] = {
    "constitution": "সংবিধান",
    "act": "আইন",
    "ordinance": "অধ্যাদেশ",
    "order": "আদেশ",
    "rules": "বিধিমালা",
    "regulation": "প্রবিধানমালা",
    "policy": "নীতিমালা/নির্দেশিকা",
    "circular": "পরিপত্র/প্রজ্ঞাপন",
    "citizen_charter": "সিটিজেন চার্টার",
    "official_webpage": "সরকারি ওয়েবপেজ",
    "official_document": "সরকারি নথি",
    "compiled_guide": "সংকলিত নির্দেশিকা (মূল সরকারি নথি নয়)",
    "official_website": "সরকারি ওয়েবসাইট (ওয়েব অনুসন্ধান)",
    "unknown": "অজানা ধরনের সূত্র",
}


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(unicodedata.normalize("NFC", pattern), re.IGNORECASE)


# checked in order: the first match decides
_TITLE_TYPES: list[tuple[str, re.Pattern[str]]] = [
    ("citizen_charter", _p(r"সিটিজেন চার্টার|নাগরিক সনদ|citizen.?charter")),
    ("ordinance", _p(r"অধ্যাদেশ|\bordinance\b")),
    ("regulation", _p(r"প্রবিধানমালা|\bregulations?\b")),
    ("rules", _p(r"বিধিমালা|\brules\b")),
    ("policy", _p(r"নীতিমালা|নির্দেশিকা|\bpolicy\b|\bguidelines?\b")),  # not bare নীতি: দুর্নীতি দমন … আইন
    ("circular", _p(r"পরিপত্র|প্রজ্ঞাপন|\bcircular\b|\bnotification\b")),
    ("order", _p(r"আদেশ|\border\b")),
    ("act", _p(r"আইন|\bact\b")),
]
_STATUTE_TYPES = ("ordinance", "regulation", "rules", "order", "act")
_WEBPAGE = _p(r"ওয়েবপেজ|homepage|webpage")
_AMENDMENT = _p(r"\(\s*(?:সংশোধন|amendment)\s*\)")
_YEAR = re.compile(r"(?<![0-9])(1[6-9][0-9]{2}|20[0-9]{2})(?![0-9])")
_KEY_DROP = re.compile(r"[\[\]()0-9০-৯,.:;।'\"‘’“”\-–]+")


@dataclass(frozen=True)
class SourceProfile:
    document_id: str
    title: str
    source_type: str
    title_year: int | None  # the year printed in the title, if any: a publication hint, never "current"
    status: Literal["repealed", "unknown"]
    is_amendment: bool
    base_key: str  # title without year, "(সংশোধন)", "[রহিত]": links an amendment act to the act it amends
    origin: str  # dataset step, or "unregistered" (admin upload, web)

    @property
    def type_label(self) -> str:
        return TYPE_LABELS.get(self.source_type, TYPE_LABELS["unknown"])


@lru_cache
def _registry() -> dict[str, tuple[str, str]]:
    """document_id -> (dataset step, parser). Missing file: everything is "unregistered"."""
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {doc["document_id"]: (step, doc.get("parser", "")) for step, docs in data.items() for doc in docs}


def _title_key(title: str) -> str:
    title = unicodedata.normalize("NFC", title).replace(REPEALED_MARK, " ")
    title = _AMENDMENT.sub(" ", title)
    title = re.sub(r"সনের|সালের", " ", title)
    return " ".join(_KEY_DROP.sub(" ", title).lower().split())


def _type_from_title(title: str) -> str:
    if _WEBPAGE.search(title):
        return "official_webpage"
    for source_type, pattern in _TITLE_TYPES:
        if pattern.search(title):
            return source_type
    return "official_document"


def _title_year(title: str) -> int | None:
    years = _YEAR.findall(bn_to_ascii_digits(title))
    return int(years[-1]) if years else None


@lru_cache(maxsize=4096)
def profile_for(document_id: str, title: str) -> SourceProfile:
    title_nfc = unicodedata.normalize("NFC", title)
    step, parser = _registry().get(document_id, ("unregistered", ""))
    if step == COMPILED_STEP or document_id.startswith("md-") or COMPILED_MARK in title_nfc:
        source_type = "compiled_guide"
    elif document_id.startswith("constitution"):
        source_type = "constitution"
    elif parser in ("bdlaws", "sqlite"):
        source_type = next((t for t, p in _TITLE_TYPES if t in _STATUTE_TYPES and p.search(title_nfc)), "act")
    else:
        source_type = _type_from_title(title_nfc)
    # the year in a compiled guide's or webpage's title is the year of the law it describes, not its own
    year = None if source_type in ("compiled_guide", "official_webpage") else _title_year(title_nfc)
    return SourceProfile(
        document_id=document_id,
        title=title_nfc.replace(REPEALED_MARK, "").strip(),
        source_type=source_type,
        title_year=year,
        status="repealed" if REPEALED_MARK in title_nfc else "unknown",
        is_amendment=source_type != "compiled_guide" and bool(_AMENDMENT.search(title_nfc)),
        base_key=_title_key(title_nfc),
        origin=step,
    )


def web_profile(passage_id: str, title: str) -> SourceProfile:
    """A web-fallback passage: an allow-listed official site, but outside the verified corpus."""
    return SourceProfile(passage_id, title, "official_website", None, "unknown", False, _title_key(title), "web")


def amends(newer: SourceProfile, older: SourceProfile) -> bool:
    """True only when `newer` is an amendment act whose title names `older`'s act and is from a later year."""
    return (
        newer.is_amendment
        and not older.is_amendment
        and newer.base_key == older.base_key
        and newer.title_year is not None
        and older.title_year is not None
        and newer.title_year > older.title_year
    )
