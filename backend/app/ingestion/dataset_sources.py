"""Manifest of data/DataSet/: which files are ingested, in which step, under which area and issuer.

Ingestion runs one step at a time (scripts/ingest_dataset.py --step <name>). Every file under
data/DataSet/ is either covered by a step or listed in SKIPPED_PATTERNS with a reason.
Byte-identical PDFs are ingested once: the first copy in manifest order wins.
"""

import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from app.core.config import DATA_DIR
from app.core.constants import Area

DATASET_DIR = DATA_DIR / "DataSet"

StepKind = Literal["bdlaws", "pdf", "markdown", "sqlite"]

LABOUR_2006 = "Workers — Bangladesh Labour Act 2006"
LABOUR_2026 = "Bangladesh Labour (Amendment) Act 2026 — Act 1672"
LAND = "Land Law"
DSS = "Department of Social Services (DSS)"
POLICE = "Bangladesh Police"
ONLINE_GD = "Online GD (Bangladesh Police)"
NHRC = "National Human Rights Commission (NHRC)"
CHRONO = "Laws of Bangladesh (Chronological Index)"
CHRONO_SQLITE = f"{CHRONO}/01_Full_Database_and_Corpus/laws_of_bangladesh.sqlite"

BDLAWS_ISSUER = "লেজিসলেটিভ ও সংসদ বিষয়ক বিভাগ, আইন, বিচার ও সংসদ বিষয়ক মন্ত্রণালয়"
LAND_ISSUER = "ভূমি মন্ত্রণালয়"
DSS_ISSUER = "সমাজসেবা অধিদফতর"
POLICE_ISSUER = "বাংলাদেশ পুলিশ"
NHRC_ISSUER = "জাতীয় মানবাধিকার কমিশন"
COMPILED_ISSUER = "সংকলিত নির্দেশিকা (সরকারি ওয়েবসাইট থেকে সংগৃহীত লেখা)"

# what is deliberately not ingested, and why (reported by --list)
SKIPPED_PATTERNS: dict[str, str] = {
    "README.md (dataset root)": "file inventory of the dataset, no content",
    f"{CHRONO}/**": "ingested from the SQLite; its .md/.jsonl/.csv/.json/.html/.pdf copies duplicate it",
    "*.html": "cached web pages of acts already ingested from their PDFs",
    "*.py": "scripts, never executed or indexed",
}


@dataclass(frozen=True)
class Step:
    name: str
    kind: StepKind
    folder: str  # relative to DATASET_DIR
    area: Area
    issuer: str
    source_url: str | None = None
    description: str = ""
    # bdlaws steps: one document for the whole folder
    document_id: str | None = None
    title: str | None = None
    # sqlite steps: inclusive act-year range
    years: tuple[int, int] | None = None


def _pdf(name: str, folder: str, area: Area, issuer: str, url: str | None, desc: str) -> Step:
    return Step(name=name, kind="pdf", folder=folder, area=area, issuer=issuer, source_url=url, description=desc)


STEPS: list[Step] = [
    Step(
        name="labour-2006",
        kind="bdlaws",
        folder=LABOUR_2006,
        area="labour",
        issuer=BDLAWS_ISSUER,
        source_url="http://bdlaws.minlaw.gov.bd/act-952.html",
        document_id="labour-act-2006",
        title="বাংলাদেশ শ্রম আইন, ২০০৬",
        description="Bangladesh Labour Act 2006, one bdlaws PDF per section",
    ),
    Step(
        name="labour-2026",
        kind="bdlaws",
        folder=LABOUR_2026,
        area="labour",
        issuer=BDLAWS_ISSUER,
        source_url="http://bdlaws.minlaw.gov.bd/act-1672.html",
        document_id="labour-amendment-2026",
        title="বাংলাদেশ শ্রম (সংশোধন) আইন, ২০২৬",
        description="Bangladesh Labour (Amendment) Act 2026, one bdlaws PDF per section",
    ),
    _pdf("online-gd", ONLINE_GD, "gd", POLICE_ISSUER, "https://gd.police.gov.bd/", "Online GD manual and guide"),
    _pdf(
        "police", POLICE, "gd", POLICE_ISSUER, "https://www.police.gov.bd/", "Police portal, citizen charter, notices"
    ),
    _pdf("nhrc", NHRC, "general", NHRC_ISSUER, "https://nhrc.org.bd/", "NHRC acts, ordinances and rules"),
    _pdf("land-policies", f"{LAND}/01_Ministry_Policies", "land", LAND_ISSUER, "https://minland.gov.bd/", "policies"),
    _pdf("land-laws", f"{LAND}/02_Ministry_Laws_and_Rules", "land", LAND_ISSUER, "https://minland.gov.bd/", "laws"),
    _pdf(
        "land-static",
        f"{LAND}/03_Acts_Rules_Regulations_Static",
        "land",
        LAND_ISSUER,
        "https://minland.gov.bd/",
        "acts, rules, President's Orders",
    ),
    _pdf(
        "land-portal",
        f"{LAND}/04_Land_Portal_Services_and_Manuals",
        "land",
        LAND_ISSUER,
        "https://land.gov.bd/",
        "land portal and manuals",
    ),
    _pdf(
        "land-mutation", f"{LAND}/05_Mutation_Portal", "land", LAND_ISSUER, "https://mutation.land.gov.bd/", "namjari"
    ),
    _pdf("land-case", f"{LAND}/06_Case_Management_Portal", "land", LAND_ISSUER, "https://case.gov.bd/", "case portal"),
    _pdf("dss-portal", f"{DSS}/00_DSS_Portal_Overview", "allowance", DSS_ISSUER, "https://dss.gov.bd/", "portal"),
    _pdf("dss-laws", f"{DSS}/01_Laws_and_Acts", "general", DSS_ISSUER, "https://dss.gov.bd/", "laws and acts"),
    _pdf("dss-rules", f"{DSS}/02_Rules_and_Regulations", "general", DSS_ISSUER, "https://dss.gov.bd/", "rules"),
    _pdf("dss-policies", f"{DSS}/03_Policies_and_Guidelines", "general", DSS_ISSUER, "https://dss.gov.bd/", "policies"),
    _pdf(
        "dss-finance",
        f"{DSS}/04_Financial_Circulars_and_Orders",
        "general",
        DSS_ISSUER,
        "https://dss.gov.bd/",
        "orders",
    ),
    _pdf(
        "dss-allowances",
        f"{DSS}/05_Allowances_and_Social_Safety_Net",
        "allowance",
        DSS_ISSUER,
        "https://dss.gov.bd/",
        "old-age, widow, disability and other allowances",
    ),
    _pdf(
        "dss-child",
        f"{DSS}/06_Child_Protection_and_Care_Institutions",
        "general",
        DSS_ISSUER,
        "https://dss.gov.bd/",
        "child protection",
    ),
    _pdf(
        "dss-community",
        f"{DSS}/07_Community_and_Rehabilitation_Programs",
        "general",
        DSS_ISSUER,
        "https://dss.gov.bd/",
        "community programs",
    ),
    Step(
        name="md-guides",
        kind="markdown",
        folder="",
        area="general",
        issuer=COMPILED_ISSUER,
        description="scraped *_Guide_and_Information.md and folder README.md (compiled, not official text)",
    ),
    *[
        Step(
            name=f"laws-{label}",
            kind="sqlite",
            folder=CHRONO_SQLITE,
            area="general",
            issuer=BDLAWS_ISSUER,
            years=years,
            description=f"bdlaws Chronological Index, acts of {years[0]}–{years[1]}",
        )
        for label, years in [
            ("1799-1946", (1799, 1946)),
            ("1947-1970", (1947, 1970)),
            ("1971-1990", (1971, 1990)),
            ("1991-2010", (1991, 2010)),
            ("2011-2026", (2011, 2100)),
        ]
    ],
]

STEP_BY_NAME = {s.name: s for s in STEPS}

# area per top-level folder (markdown guides) and keyword overrides (DSS mixes allowance and other topics)
FOLDER_AREA: dict[str, Area] = {
    LABOUR_2006: "labour",
    LABOUR_2026: "labour",
    LAND: "land",
    POLICE: "gd",
    ONLINE_GD: "gd",
    NHRC: "general",
}
_ALLOWANCE_HINT = re.compile(r"ভাতা|allowance|উপবৃত্তি|stipend|safety_net", re.IGNORECASE)


def area_for_path(rel: Path, default: Area) -> Area:
    """Area of one file: DSS files about allowances go to `allowance`, everything else keeps the default."""
    top = rel.parts[0] if rel.parts else ""
    if top == DSS:
        portal = len(rel.parts) > 1 and rel.parts[1] == "00_DSS_Portal_Overview"
        return "allowance" if portal or _ALLOWANCE_HINT.search(str(rel)) else default
    return FOLDER_AREA.get(top, default)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _step_pdfs(step: Step, root: Path) -> list[Path]:
    folder = root / step.folder
    pattern = "*.pdf" if step.kind == "bdlaws" or step.name in ("online-gd", "nhrc") else "**/*.pdf"
    pdfs = sorted(folder.glob(pattern))
    if step.name == "police":  # top level and Announcements_and_Orders
        pdfs = sorted(folder.rglob("*.pdf"))
    return pdfs


@lru_cache
def _first_copy(root: Path) -> dict[str, Path]:
    """sha256 -> the first PDF with that content in manifest order (later copies are skipped)."""
    first: dict[str, Path] = {}
    for step in STEPS:
        if step.kind not in ("bdlaws", "pdf"):
            continue
        for pdf in _step_pdfs(step, root):
            first.setdefault(sha256_of(pdf), pdf)
    return first


@dataclass(frozen=True)
class SourceFile:
    path: Path
    rel: Path  # relative to DATASET_DIR
    sha256: str
    area: Area
    duplicate_of: Path | None = None


def step_files(step: Step, root: Path | None = None) -> list[SourceFile]:
    root = root or DATASET_DIR
    if step.kind == "sqlite":
        p = root / step.folder
        return [SourceFile(p, p.relative_to(root), "", step.area)] if p.exists() else []
    if step.kind == "markdown":
        return [SourceFile(p, p.relative_to(root), sha256_of(p), area_for_path(p.relative_to(root), step.area))
                for p in markdown_files(root)]  # fmt: skip
    first = _first_copy(root)
    out: list[SourceFile] = []
    for pdf in _step_pdfs(step, root):
        digest = sha256_of(pdf)
        rel = pdf.relative_to(root)
        dup = first.get(digest)
        out.append(SourceFile(pdf, rel, digest, area_for_path(rel, step.area), None if dup == pdf else dup))
    return out


def markdown_files(root: Path) -> Iterator[Path]:
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        if len(rel.parts) == 1 or rel.parts[0] == CHRONO:
            continue  # dataset-root inventory; chronological index comes from the SQLite
        yield p


# ---------------------------------------------------------------------------- titles

_HEX_TAIL = re.compile(
    r"_(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[A-Za-z0-9]{24})$"
)
_JUNK = re.compile(r"files-|title=|inherit;|div_style|webkit|ডাউনলোড|📎|^=|^[0-9]+$|\.pdf_")
_PRINT = re.compile(r"(?:_Page)?_Print$", re.IGNORECASE)


def clean_filename(name: str) -> str:
    """'03_ভূমি সংস্কার আইন, ২০২৩.pdf' -> 'ভূমি সংস্কার আইন, ২০২৩'. Returns '' for scraper-junk names."""
    stem = Path(name).stem.replace("&#39;", "'")
    stem = re.sub(r"^[0-9]{1,3}_", "", stem)
    stem = _HEX_TAIL.sub("", stem)
    if _JUNK.search(stem):
        return ""
    is_print = bool(_PRINT.search(stem))
    stem = _PRINT.sub("", stem)
    text = re.sub(r"\s+", " ", stem.replace("_", " ")).strip(" -,‘’'\"“”")
    if sum(ch.isalpha() for ch in text) < 4:
        return ""
    return f"{text} (ওয়েবপেজ)" if is_print else text
