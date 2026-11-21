"""Ingest data/DataSet one step at a time (see app/ingestion/dataset_sources.py for the steps).

Usage (from backend/):
    python scripts/ingest_dataset.py --list                 # steps, file counts, duplicates, done/pending
    python scripts/ingest_dataset.py --status               # counts in every store + Postgres size
    python scripts/ingest_dataset.py --wipe --yes           # empty Qdrant, Postgres, BM25, processed outputs
    python scripts/ingest_dataset.py --step labour-2006     # convert + chunk + embed + index one step
    python scripts/ingest_dataset.py --step land-static --convert-only   # OCR/parse only (cached)

A step replaces only its own documents; earlier steps are never re-embedded. Parsed/OCR'd text is
cached per file (data/ocr/dataset/<sha256>.json), so a re-run after a crash skips finished files.
OCR models are released before the embedding model loads (6 GB GPU).
"""

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402

from app.core.config import DATA_DIR, settings  # noqa: E402
from app.ingestion import bdlaws_parser, generic_parser, markdown_parser, sqlite_laws  # noqa: E402
from app.ingestion.area_map import DocumentSpec  # noqa: E402
from app.ingestion.dataset_indexer import index_step, is_done, load_dataset_registry, wipe_all  # noqa: E402
from app.ingestion.dataset_sources import (  # noqa: E402
    COMPILED_ISSUER,
    DATASET_DIR,
    SKIPPED_PATTERNS,
    STEP_BY_NAME,
    STEPS,
    SourceFile,
    Step,
    clean_filename,
    step_files,
)
from app.ingestion.source_registry import log_source  # noqa: E402
from app.schemas.ingestion import SectionRecord  # noqa: E402

OCR_CACHE = DATA_DIR / "ocr" / "dataset"
TITLE_MAX = 90


# ---------------------------------------------------------------------------- conversion


def _first_good_line(pages: list[tuple[int, str]]) -> str:
    for _, text in pages[:3]:
        for line in text.splitlines():
            line = line.strip()
            if len(line) >= 8 and generic_parser.ocr_quality(line) >= 0.8:
                return line if len(line) <= TITLE_MAX else line[:TITLE_MAX].rsplit(" ", 1)[0] + " …"
    return ""


def _is_bdlaws(path: Path) -> bool:
    with pymupdf.open(path) as doc:
        return doc.page_count > 0 and "bdlaws.minlaw.gov.bd" in doc[0].get_text()


def _json_default(value: object) -> object:
    """OCR engines report numpy scalars (confidence, needs_review); store them as plain JSON values."""
    if hasattr(value, "item"):
        return value.item()  # type: ignore[union-attr]
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _parse_generic_cached(src: SourceFile, ocr: generic_parser.PageOcrRunner) -> generic_parser.ParsedPdf:
    cache = OCR_CACHE / f"{src.sha256}.json"
    if cache.exists():
        raw = json.loads(cache.read_text(encoding="utf-8"))
        parsed = generic_parser.ParsedPdf(
            pages=[(p, t) for p, t in raw["pages"]],
            reports=[generic_parser.PageReport(**r) for r in raw["reports"]],
        )
        # parses cached before the unreadable-text-layer check: OCR just those pages, then re-cache
        redone = generic_parser.reocr_unreadable_pages(src.path, parsed, ocr)
        if not redone:
            return parsed
        print(f"            re-OCR'd {redone} unreadable text-layer pages")
    else:
        parsed = generic_parser.parse_generic_pdf(src.path, ocr, drop_garbage=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps({"file": str(src.rel), "pages": parsed.pages, "reports": [asdict(r) for r in parsed.reports]},
                   ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )  # fmt: skip
    return parsed


def convert_bdlaws(step: Step, files: list[SourceFile]) -> tuple[list[DocumentSpec], list[SectionRecord]]:
    assert step.document_id and step.title
    spec = DocumentSpec(step.document_id, step.area, step.title, step.issuer, "bdlaws", "bn", step.source_url)
    by_id: dict[str, SectionRecord] = {}
    for src in files:
        recs = bdlaws_parser.to_section_records(bdlaws_parser.parse_bdlaws_pdf(src.path), spec, src.path.name)
        if not recs:
            print(f"WARN  no sections in {src.rel.name}")
        for r in recs:
            if r.id in by_id:
                print(
                    f"WARN  section id {r.id} appears twice ({by_id[r.id].source_file}, {r.source_file}); kept longer"
                )
                if len(r.text) <= len(by_id[r.id].text):
                    continue
            by_id[r.id] = r
        log_source(spec, src.path, src.sha256, "pymupdf+bdlaws", "unverified")
    records = sorted(by_id.values(), key=lambda r: bdlaws_parser.section_sort_key(r.section))
    return [spec], records


SECOND_OCR = True  # --no-second-ocr: Tesseract only (CPU), much faster for bulk runs


def convert_pdfs(step: Step, files: list[SourceFile]) -> tuple[list[DocumentSpec], list[SectionRecord]]:
    specs: list[DocumentSpec] = []
    records: list[SectionRecord] = []
    ocr = generic_parser.PageOcrRunner() if SECOND_OCR else generic_parser.PageOcrRunner(secondary="")
    try:
        for i, src in enumerate(files, start=1):
            t0 = time.perf_counter()
            doc_id = f"{step.name}-{src.sha256[:10]}"
            name_title = clean_filename(src.path.name)
            if _is_bdlaws(src.path):
                parsed_b = bdlaws_parser.parse_bdlaws_pdf(src.path)
                title = parsed_b.act or name_title or src.path.stem
                spec = DocumentSpec(doc_id, src.area, title, step.issuer, "bdlaws", "bn", step.source_url)
                recs = bdlaws_parser.to_section_records(parsed_b, spec, src.path.name)
                method = "pymupdf+bdlaws"
                summary = f"bdlaws, {len(recs)} sections"
            else:
                parsed = _parse_generic_cached(src, ocr)
                title = name_title or _first_good_line(parsed.pages) or f"{src.rel.parent.name} — {src.sha256[:6]}"
                spec = DocumentSpec(doc_id, src.area, title, step.issuer, "generic", "bn", step.source_url)
                recs = generic_parser.to_section_records(parsed, spec, src.path.name)
                kinds = Counter(r.method for r in parsed.reports)
                method = "+".join(sorted(kinds))
                summary = " ".join(f"{k}={v}" for k, v in sorted(kinds.items()))
            took = time.perf_counter() - t0
            print(f"  [{i:>3}/{len(files)}] {src.area:<9} {len(recs):>4} rec  {took:5.1f}s  {summary}  ← {src.rel}")
            print(f"            title: {title}")
            if recs:
                specs.append(spec)
                records += recs
                review = "needs_review" if "dropped" in method or "skipped" in method else "unverified"
                log_source(spec, src.path, src.sha256, method, review)
            else:
                print("            WARN  no usable text; document skipped")
    finally:
        ocr.release()  # free OCR models / GPU before the embedding model loads
    return specs, records


def convert_markdown(step: Step, files: list[SourceFile]) -> tuple[list[DocumentSpec], list[SectionRecord]]:
    specs: list[DocumentSpec] = []
    records: list[SectionRecord] = []
    for src in files:
        parsed = markdown_parser.read_markdown(src.path)
        base = parsed.title or clean_filename(src.path.name) or src.rel.parent.name
        title = f"{base} (সংকলিত নির্দেশিকা)"
        spec = DocumentSpec(f"md-{src.sha256[:10]}", src.area, title, COMPILED_ISSUER, "markdown", "bn",
                            parsed.source_url)  # fmt: skip
        recs = markdown_parser.to_section_records(parsed, spec, str(src.rel))
        print(f"  {src.area:<9} {len(recs):>3} sections  {title}  ← {src.rel}")
        if recs:
            specs.append(spec)
            records += recs
    return specs, records


def convert_sqlite(step: Step, files: list[SourceFile]) -> tuple[list[DocumentSpec], list[SectionRecord]]:
    specs: list[DocumentSpec] = []
    records: list[SectionRecord] = []
    if not files:
        return specs, records
    src = files[0]
    conn = sqlite_laws.connect(src.path)
    try:
        for act in sqlite_laws.iter_acts(conn, step.years):
            spec = sqlite_laws.document_spec(act, step.issuer)
            recs = sqlite_laws.act_records(conn, act, spec, src.path.name)
            if recs:
                specs.append(spec)
                records += recs
    finally:
        conn.close()
    areas = Counter(s.area for s in specs)
    print(f"  {len(specs)} acts, {len(records)} sections; acts per area: {dict(areas)}")
    return specs, records


CONVERTERS = {"bdlaws": convert_bdlaws, "pdf": convert_pdfs, "markdown": convert_markdown, "sqlite": convert_sqlite}


# ---------------------------------------------------------------------------- commands


def cmd_list() -> int:
    registry = load_dataset_registry()
    total = 0
    for step in STEPS:
        files = step_files(step)
        dups = sum(1 for f in files if f.duplicate_of)
        done = f"done ({len(registry.get(step.name, []))} docs)" if is_done(step.name) else "pending"
        print(f"{step.name:<16} {step.kind:<8} {step.area:<9} {len(files) - dups:>4} files"
              f"{f' (+{dups} duplicates skipped)' if dups else '':<28} {done:<18} {step.description}")  # fmt: skip
        total += len(files) - dups
    print(f"\n{total} source files in {len(STEPS)} steps. Not ingested:")
    for pattern, why in SKIPPED_PATTERNS.items():
        print(f"  {pattern:<45} {why}")
    return 0


async def cmd_status() -> int:
    from app.ingestion.dataset_indexer import load_cached_chunks
    from app.repositories.qdrant_repository import QdrantRepository

    chunks = load_cached_chunks()
    print(f"chunk cache: {len(chunks)} chunks; per area {dict(Counter(c.area for c in chunks))}")
    print(f"qdrant:      {await QdrantRepository().count()} points")
    if settings.bm25_path.exists():
        from app.repositories.bm25_repository import BM25Index

        print(f"bm25:        {len(BM25Index.load(settings.bm25_path))} docs")
    if settings.database_url is not None:
        from sqlalchemy import text

        from app.db.session import get_sessionmaker

        async with get_sessionmaker()() as s:
            n_docs = (await s.execute(text("select count(*) from documents"))).scalar()
            n_chunks = (await s.execute(text("select count(*) from chunks"))).scalar()
            size = (await s.execute(text("select pg_size_pretty(pg_database_size(current_database()))"))).scalar()
        print(f"postgres:    {n_docs} documents, {n_chunks} chunks, database size {size}")
    return 0


async def cmd_step(name: str, convert_only: bool, skip_postgres: bool) -> int:
    step = STEP_BY_NAME.get(name)
    if step is None:
        print(f"FAIL  unknown step {name!r}; see --list")
        return 1
    t0 = time.perf_counter()
    files = [f for f in step_files(step) if f.duplicate_of is None]
    print(f"OK    step {step.name}: {len(files)} files ({step.kind}, default area {step.area})")
    specs, records = CONVERTERS[step.kind](step, files)
    if not records:
        print("FAIL  nothing extracted")
        return 1
    print(f"OK    {len(specs)} documents, {len(records)} section records ({time.perf_counter() - t0:.0f}s)")
    if convert_only:
        return 0

    from app.ingestion.chunker import chunk_section, model_token_counter
    from app.models.embedding_client import get_embedding_client

    count = model_token_counter(settings.embedding_model)
    chunks = [c for r in records for c in chunk_section(r, count)]
    print(f"OK    {len(chunks)} chunks (max {max(c.token_count for c in chunks)} tokens)")
    t1 = time.perf_counter()
    client = get_embedding_client()
    vectors = client.embed_passages([c.embedding_text() for c in chunks])
    print(f"OK    embedded on {client.device} in {time.perf_counter() - t1:.0f}s")

    report = await index_step(step.name, specs, records, chunks, vectors, skip_postgres=skip_postgres)
    print(
        f"{'OK  ' if report.consistent else 'FAIL'}  stores after {step.name}: chunks={report.total_chunks} "
        f"qdrant={report.qdrant} bm25={report.bm25} postgres={report.postgres}  ({time.perf_counter() - t0:.0f}s total)"
    )
    return 0 if report.consistent else 1


async def cmd_resume(skip_postgres: bool, pause: int) -> int:
    """Run every pending step in manifest order, one at a time, with a progress line and ETA."""
    pending = [s.name for s in STEPS if not is_done(s.name)]
    if not pending:
        print("OK    every step is done")
        return 0
    print(f"OK    {len(pending)} pending steps: {', '.join(pending)}")
    t0 = time.perf_counter()
    failed: list[str] = []
    for i, name in enumerate(pending, start=1):
        elapsed = time.perf_counter() - t0
        eta = f", ETA ~{elapsed / (i - 1) * (len(pending) - i + 1) / 60:.0f} min" if i > 1 else ""
        bar = "#" * (i - 1) + "." * (len(pending) - i + 1)
        print(f"\n[{bar}] step {i}/{len(pending)}: {name}  (elapsed {elapsed / 60:.0f} min{eta})", flush=True)
        try:
            if await cmd_step(name, convert_only=False, skip_postgres=skip_postgres) != 0:
                failed.append(name)
        except Exception as exc:  # noqa: BLE001 - keep going; the step stays pending and can be re-run
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            failed.append(name)
        if pause and i < len(pending):
            print(f"      pausing {pause}s to let the laptop cool", flush=True)
            await asyncio.sleep(pause)
    print(f"\n{'OK  ' if not failed else 'FAIL'}  finished in {(time.perf_counter() - t0) / 60:.0f} min; "
          f"failed: {failed or 'none'} (re-run --resume to retry them)")  # fmt: skip
    return 0 if not failed else 1


def main() -> int:
    global SECOND_OCR
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--wipe", action="store_true")
    ap.add_argument("--yes", action="store_true", help="confirm --wipe")
    ap.add_argument("--step")
    ap.add_argument("--convert-only", action="store_true")
    ap.add_argument("--skip-postgres", action="store_true")
    ap.add_argument("--no-second-ocr", action="store_true", help="Tesseract only; skip the GPU second engine")
    ap.add_argument("--resume", action="store_true", help="run all pending steps (Tesseract only, cooler)")
    ap.add_argument("--pause", type=int, default=20, help="seconds to rest between steps with --resume")
    args = ap.parse_args()
    if args.no_second_ocr:
        SECOND_OCR = False
    if not DATASET_DIR.exists():
        print(f"FAIL  {DATASET_DIR} not found")
        return 1
    if args.list:
        return cmd_list()
    if args.status:
        return asyncio.run(cmd_status())
    if args.wipe:
        if not args.yes:
            print("Refusing to wipe without --yes (deletes every chunk in Qdrant, Postgres and BM25).")
            return 1
        asyncio.run(wipe_all(args.skip_postgres))
        print("OK    wiped Qdrant, Postgres (documents, chunks, answer_cache), BM25 and processed outputs")
        return 0
    if args.step:
        return asyncio.run(cmd_step(args.step, args.convert_only, args.skip_postgres))
    if args.resume:
        import os

        SECOND_OCR = False
        os.environ.setdefault("OMP_THREAD_LIMIT", "2")  # Tesseract threads: slower but much cooler
        return asyncio.run(cmd_resume(args.skip_postgres, args.pause))
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
