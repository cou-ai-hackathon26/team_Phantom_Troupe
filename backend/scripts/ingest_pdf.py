"""Ingest a new PDF (or a folder of PDFs) end to end.

Usage (from backend/):
    python scripts/ingest_pdf.py path/to/file.pdf --area allowance --title "বয়স্ক ভাতা কর্মসূচি বাস্তবায়ন নীতিমালা" \\
        --issuer "সমাজসেবা অধিদফতর" --source-url "https://…"
    python scripts/ingest_pdf.py "data/Land — …/" --area land --title "…" --parser bdlaws

Steps: preserve original in data/originals/<area>/ + sha256 + sources_log.csv row -> parse
(bdlaws section-print PDFs, or generic: text / Bijoy legacy font / local OCR per page) ->
data/processed/<document_id>.jsonl -> all_documents.jsonl -> chunks -> Postgres + Qdrant + BM25.
OCR models are released (GPU freed) before the embedding model loads.
"""

import argparse
import asyncio
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402

from app.core.config import DATA_DIR  # noqa: E402
from app.ingestion import bdlaws_parser, generic_parser  # noqa: E402
from app.ingestion.area_map import DocumentSpec  # noqa: E402
from app.ingestion.jsonl_loader import rebuild_all_documents, write_jsonl  # noqa: E402
from app.ingestion.ocr_service import PageOcrRunner  # noqa: E402
from app.ingestion.source_registry import log_source, preserve_original, register  # noqa: E402
from app.schemas.ingestion import SectionRecord  # noqa: E402


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:60] or "document"


def is_bdlaws(pdf: Path) -> bool:
    with pymupdf.open(pdf) as doc:
        return "bdlaws.minlaw.gov.bd" in doc[0].get_text() if doc.page_count else False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path, help="a PDF file or a folder of PDFs")
    ap.add_argument("--area", required=True, choices=["land", "gd", "allowance", "labour"])
    ap.add_argument("--title", required=True, help="official document title (Bangla)")
    ap.add_argument("--issuer", default="", help="issuing authority (verified)")
    ap.add_argument("--source-url", default=None, help="official URL (verified)")
    ap.add_argument("--document-id", default=None)
    ap.add_argument("--parser", default="auto", choices=["auto", "bdlaws", "generic"])
    ap.add_argument("--no-index", action="store_true", help="convert + register only; skip embedding/indexing")
    ap.add_argument("--skip-postgres", action="store_true")
    args = ap.parse_args()

    pdfs = sorted(args.path.glob("*.pdf")) if args.path.is_dir() else [args.path]
    if not pdfs or not all(p.exists() for p in pdfs):
        print(f"FAIL  no PDF found at {args.path}")
        return 1
    doc_id = args.document_id or f"{args.area}-{slugify(args.path.stem if args.path.is_file() else args.path.name)}"
    parser = args.parser
    if parser == "auto":
        parser = "bdlaws" if is_bdlaws(pdfs[0]) else "generic"
    spec = DocumentSpec(
        document_id=doc_id,
        area=args.area,
        title=args.title,
        issuer=args.issuer,
        parser=parser,
        source_url=args.source_url,
    )
    print(f"OK    document {doc_id!r}  area={args.area}  parser={parser}  files={len(pdfs)}")

    records: list[SectionRecord] = []
    ocr = PageOcrRunner() if parser == "generic" else None
    try:
        for pdf in pdfs:
            original, digest = preserve_original(pdf, args.area)
            if parser == "bdlaws":
                recs = bdlaws_parser.to_section_records(bdlaws_parser.parse_bdlaws_pdf(pdf), spec, pdf.name)
                method, review = "pymupdf+bdlaws", False
            else:
                parsed = generic_parser.parse_generic_pdf(pdf, ocr)
                recs = generic_parser.to_section_records(parsed, spec, pdf.name)
                methods = sorted({r.method for r in parsed.reports})
                method, review = "+".join(methods), parsed.needs_review
                for r in parsed.reports:
                    conf = f" conf={r.confidence:.0f}" if r.confidence is not None else ""
                    flag = "  needs_review" if r.needs_review else ""
                    print(f"        p{r.page_number:<3} {r.kind:<8} {r.method:<10} {r.chars:>6} chars{conf}{flag}")
            log_source(spec, original, digest, method, "needs_review" if review else "unverified")
            print(f"OK    {pdf.name}: {len(recs)} records  sha256={digest[:12]}…  -> {original.relative_to(DATA_DIR)}")
            records += recs
    finally:
        if ocr is not None:
            ocr.release()  # free OCR models / GPU before the embedding model loads

    if not records:
        print("FAIL  no text could be extracted (install Tesseract with Bengali for scanned PDFs)")
        return 1
    register(spec)
    processed = DATA_DIR / "processed"
    n = write_jsonl(records, processed / f"{doc_id}.jsonl")
    total = rebuild_all_documents(processed)
    print(f"OK    data/processed/{doc_id}.jsonl: {n} records; all_documents.jsonl: {total}")
    if args.no_index:
        return 0

    from app.ingestion.pipeline import ingest_all

    return asyncio.run(ingest_all(skip_postgres=args.skip_postgres))


if __name__ == "__main__":
    raise SystemExit(main())
