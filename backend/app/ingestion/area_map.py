"""Explicit source registry: which folder / JSONL source_file belongs to which document and area.

Unknown sources fail loudly; add them here deliberately (with a verified issuer and URL).
"""

from dataclasses import dataclass

from app.core.constants import Area


@dataclass(frozen=True)
class DocumentSpec:
    document_id: str
    area: Area
    title: str
    issuer: str
    parser: str  # "bdlaws" (section-print PDFs) | "generic_pdf" | "jsonl"
    language: str = "bn"
    source_url: str | None = None


# data/<folder>/*.pdf  ->  document
PDF_FOLDERS: dict[str, DocumentSpec] = {
    "Workers — Bangladesh Labour Act 2006": DocumentSpec(
        document_id="labour-act-2006",
        area="labour",
        title="বাংলাদেশ শ্রম আইন, ২০০৬",
        issuer="লেজিসলেটিভ ও সংসদ বিষয়ক বিভাগ, আইন, বিচার ও সংসদ বিষয়ক মন্ত্রণালয়",
        parser="bdlaws",
        source_url="https://bdlaws.minlaw.gov.bd/act-952.html",
    ),
}

# data/processed/all_documents.jsonl  source_file  ->  document (filled when the team's JSONL arrives)
JSONL_SOURCE_FILES: dict[str, DocumentSpec] = {}


class UnknownSource(KeyError):
    pass


def spec_for_folder(folder_name: str) -> DocumentSpec:
    try:
        return PDF_FOLDERS[folder_name]
    except KeyError as exc:
        raise UnknownSource(f"PDF folder {folder_name!r} is not registered in app/ingestion/area_map.py") from exc


def spec_for_source_file(source_file: str) -> DocumentSpec:
    try:
        return JSONL_SOURCE_FILES[source_file]
    except KeyError as exc:
        raise UnknownSource(f"source_file {source_file!r} is not registered in app/ingestion/area_map.py") from exc
