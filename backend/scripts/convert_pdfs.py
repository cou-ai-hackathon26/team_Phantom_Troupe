"""Convert registered PDF folders (data/<folder>/*.pdf) into section JSONL in data/processed/.

Usage (from backend/):  python scripts/convert_pdfs.py
Writes data/processed/<document_id>.jsonl per folder and regenerates all_documents.jsonl.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import DATA_DIR  # noqa: E402
from app.ingestion.area_map import PDF_FOLDERS  # noqa: E402
from app.ingestion.bdlaws_parser import parse_bdlaws_pdf, section_sort_key, to_section_records  # noqa: E402
from app.ingestion.jsonl_loader import rebuild_all_documents, write_jsonl  # noqa: E402
from app.schemas.ingestion import SectionRecord  # noqa: E402


def main() -> int:
    start = time.perf_counter()
    processed = DATA_DIR / "processed"
    registered = set(PDF_FOLDERS)
    for folder in sorted(p for p in DATA_DIR.iterdir() if p.is_dir() and any(p.glob("*.pdf"))):
        if folder.name not in registered and folder.name != "originals":
            print(f"WARN  unregistered PDF folder skipped: {folder.name!r} (add it to app/ingestion/area_map.py)")

    for folder_name, spec in PDF_FOLDERS.items():
        folder = DATA_DIR / folder_name
        pdfs = sorted(folder.glob("*.pdf"))
        if not pdfs:
            print(f"WARN  no PDFs in {folder}")
            continue
        if spec.parser != "bdlaws":
            print(f"WARN  parser {spec.parser!r} not implemented yet for {folder_name!r}")
            continue
        records: list[SectionRecord] = []
        for pdf in pdfs:
            parsed = parse_bdlaws_pdf(pdf)
            recs = to_section_records(parsed, spec, pdf.name)
            if not recs:
                print(f"WARN  no sections found in {pdf.name}")
            records += recs
        records.sort(key=lambda r: section_sort_key(r.section))
        n = write_jsonl(records, processed / f"{spec.document_id}.jsonl")
        print(f"OK    {spec.document_id}: {len(pdfs)} PDFs -> {n} sections")

    total = rebuild_all_documents(processed)
    print(f"OK    all_documents.jsonl: {total} records ({time.perf_counter() - start:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
