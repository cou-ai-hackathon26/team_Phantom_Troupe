"""Admin knowledge management: list, upload (background ingestion) and delete documents.

An upload is indexed incrementally — only the new document's chunks are embedded — then the BM25 index
is rebuilt from all chunks and swapped into the running API. Every change clears the answer cache,
because cached answers (and cached refusals) may no longer match the knowledge base.
"""

import asyncio
import contextlib
import logging
import re
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from qdrant_client import models

from app.core.config import DATA_DIR, settings
from app.ingestion import bdlaws_parser, generic_parser
from app.ingestion.area_map import PDF_FOLDERS, DocumentSpec
from app.ingestion.chunker import chunk_section, model_token_counter
from app.ingestion.indexer import document_specs, write_postgres_document, write_qdrant
from app.ingestion.jsonl_loader import rebuild_all_documents, write_jsonl
from app.ingestion.source_registry import load_registry, log_source, preserve_original, register
from app.ingestion.upload_text import UnsupportedFile, extract_upload, file_kind
from app.models.embedding_client import get_embedding_client
from app.repositories.bm25_repository import BM25Index
from app.repositories.qdrant_repository import QdrantRepository
from app.schemas.ingestion import ChunkRecord, SectionRecord
from app.services.answer_cache import get_answer_cache
from app.services.retrieval_service import get_retriever

logger = logging.getLogger(__name__)
PROCESSED = DATA_DIR / "processed"
UPLOADS = DATA_DIR / "uploads"


@dataclass
class Job:
    id: str
    filename: str
    document_id: str
    title: str
    area: str
    status: str = "queued"  # queued | running | done | failed
    steps: list[str] = field(default_factory=list)
    error: str | None = None
    sections: int = 0
    chunks: int = 0
    needs_review: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    finished_at: str | None = None

    def step(self, message: str) -> None:
        self.steps.append(message)
        logger.info("admin ingest", extra={"data": {"job": self.id, "step": message}})


_jobs: dict[str, Job] = {}
_lock = asyncio.Lock()


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:50]


def builtin_ids() -> set[str]:
    from app.ingestion.dataset_indexer import dataset_specs

    return {s.document_id for s in PDF_FOLDERS.values()} | set(dataset_specs())


def list_jobs() -> list[Job]:
    return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)[:30]


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def _parse(path: Path, data: bytes, filename: str, content_type: str | None, spec: DocumentSpec, job: Job):
    """Blocking: returns (records, extraction method, needs_review)."""
    kind = file_kind(filename, content_type)
    if kind == "pdf" and spec.parser in ("auto", "bdlaws") and (spec.parser == "bdlaws" or _is_bdlaws(path)):
        spec_used = DocumentSpec(**{**asdict(spec), "parser": "bdlaws"})
        recs = bdlaws_parser.to_section_records(bdlaws_parser.parse_bdlaws_pdf(path), spec_used, filename)
        return recs, "pymupdf+bdlaws", False
    # generic: free the GPU from the embedding model before any OCR model loads
    get_embedding_client().unload()
    extracted = extract_upload(data, filename, content_type)
    parsed = generic_parser.ParsedPdf(pages=extracted.pages, reports=extracted.reports)
    for r in extracted.reports:
        conf = f", confidence {r.confidence:.0f}" if r.confidence is not None else ""
        job.step(f"page {r.page_number}: {r.kind} → {r.method}{conf}{' (needs review)' if r.needs_review else ''}")
    return (
        generic_parser.to_section_records(parsed, spec, filename),
        "+".join(extracted.methods),
        extracted.needs_review,
    )


def _is_bdlaws(path: Path) -> bool:
    import pymupdf

    with pymupdf.open(path) as doc:
        return doc.page_count > 0 and "bdlaws.minlaw.gov.bd" in doc[0].get_text()


async def _rebuild_bm25(chunks: list[ChunkRecord]) -> int:
    index = await asyncio.to_thread(BM25Index.build, chunks)
    await asyncio.to_thread(index.save, settings.bm25_path)
    get_retriever().replace_index(index)
    return len(index)


async def _run_job(job: Job, path: Path, data: bytes, content_type: str | None, spec: DocumentSpec) -> None:
    async with _lock:  # one ingestion at a time (GPU memory, BM25 rebuild)
        job.status = "running"
        try:
            job.step("saving original and checksum")
            original, digest = preserve_original(path, spec.area)

            job.step("extracting text")
            records, method, review = await asyncio.to_thread(_parse, path, data, job.filename, content_type, spec, job)
            if not records:
                raise UnsupportedFile("ফাইল থেকে কোনো লেখা পাওয়া যায়নি (OCR-ও ব্যর্থ)।")
            job.sections, job.needs_review = len(records), review
            log_source(spec, original, digest, method, "needs_review" if review else "unverified")
            register(spec)
            write_jsonl(records, PROCESSED / f"{spec.document_id}.jsonl")
            rebuild_all_documents(PROCESSED)
            job.step(f"{len(records)} sections → data/processed/{spec.document_id}.jsonl")

            job.step("chunking and embedding (local e5)")
            count = model_token_counter(settings.embedding_model)
            chunks = [c for r in records for c in chunk_section(r, count)]
            vectors = await asyncio.to_thread(
                get_embedding_client().embed_passages, [c.embedding_text() for c in chunks]
            )
            job.chunks = len(chunks)

            job.step("writing Qdrant")
            repo = QdrantRepository()
            await repo.ensure_collection(vectors.shape[1])
            await repo.delete_document(spec.document_id)  # re-upload replaces the old version
            await write_qdrant(repo, chunks, vectors, cleanup=False)

            if settings.database_url is not None:
                job.step("writing Postgres")
                await write_postgres_document(spec, chunks, job.filename)

            job.step("rebuilding BM25 and reloading the live index")
            retriever = get_retriever()
            others = [c for c in retriever.chunks.values() if c.document_id != spec.document_id]
            total = await _rebuild_bm25(others + chunks)
            await get_answer_cache().clear()
            job.step(f"done: {len(chunks)} chunks added; knowledge base now has {total} chunks; answer cache cleared")
            job.status = "done"
        except Exception as exc:  # noqa: BLE001 - surface every failure to the admin UI
            logger.exception("admin ingest failed")
            job.status, job.error = (
                "failed",
                str(exc) if isinstance(exc, UnsupportedFile) else f"{type(exc).__name__}: {exc}",
            )
            job.step(f"failed: {job.error}")
        finally:
            job.finished_at = datetime.now(UTC).isoformat(timespec="seconds")
            path.unlink(missing_ok=True)
            with contextlib.suppress(OSError):
                path.parent.rmdir()


def start_upload(
    data: bytes, filename: str, content_type: str | None, *, area: str, title: str, issuer: str,
    source_url: str | None, document_id: str | None, parser: str,
) -> Job:  # fmt: skip
    file_kind(filename, content_type)  # validate early (raises UnsupportedFile)
    # Bangla titles slugify to "", so fall back to a short random id rather than a long filename slug
    doc_id = document_id or f"{area}-{slugify(title)[:40] or 'doc-' + uuid.uuid4().hex[:8]}"
    if doc_id in builtin_ids():
        raise UnsupportedFile("এই নথিটি প্রকল্পের অংশ (built-in); একই আইডি দিয়ে আপলোড করা যাবে না।")
    spec = DocumentSpec(document_id=doc_id, area=area, title=title, issuer=issuer, parser=parser, source_url=source_url)  # type: ignore[arg-type]
    # keep the original filename (it is preserved in data/originals/) inside a unique temp folder
    tmp_dir = UPLOADS / uuid.uuid4().hex
    tmp_dir.mkdir(parents=True, exist_ok=True)
    path = tmp_dir / (Path(filename).name or "upload")
    path.write_bytes(data)
    job = Job(id=uuid.uuid4().hex[:12], filename=filename, document_id=doc_id, title=title, area=area)
    _jobs[job.id] = job
    asyncio.create_task(_run_job(job, path, data, content_type, spec))
    return job


async def delete_document(document_id: str) -> int:
    if document_id in builtin_ids():
        raise UnsupportedFile("built-in নথি অ্যাডমিন প্যানেল থেকে মোছা যায় না (area_map.py থেকে সরান)।")
    if document_id not in load_registry() and document_id not in {
        c.document_id for c in get_retriever().chunks.values()
    }:
        raise KeyError(document_id)
    async with _lock:
        repo = QdrantRepository()
        await repo.client.create_payload_index(repo.collection, "document_id", models.PayloadSchemaType.KEYWORD)
        await repo.delete_document(document_id)
        if settings.database_url is not None:
            from sqlalchemy import delete

            from app.db.models import Document
            from app.db.session import get_sessionmaker

            async with get_sessionmaker()() as session:
                await session.execute(delete(Document).where(Document.id == document_id))
                await session.commit()
        (PROCESSED / f"{document_id}.jsonl").unlink(missing_ok=True)
        rebuild_all_documents(PROCESSED)
        _unregister(document_id)
        remaining = [c for c in get_retriever().chunks.values() if c.document_id != document_id]
        total = await _rebuild_bm25(remaining)
        await get_answer_cache().clear()
        return total


def _unregister(document_id: str) -> None:
    import json

    specs = load_registry()
    if document_id in specs:
        del specs[document_id]
        from app.ingestion import source_registry

        source_registry.REGISTRY_PATH.write_text(
            json.dumps([asdict(s) for s in specs.values()], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


@dataclass
class DocumentRow:
    document_id: str
    title: str
    area: str
    issuer: str | None
    source_url: str | None
    sections: int
    chunks: int
    builtin: bool
    source_files: list[str]


def list_documents() -> list[DocumentRow]:
    specs = document_specs()
    builtin = builtin_ids()
    rows: dict[str, DocumentRow] = {}
    for c in get_retriever().chunks.values():
        spec = specs.get(c.document_id)
        row = rows.setdefault(
            c.document_id,
            DocumentRow(
                document_id=c.document_id,
                title=spec.title if spec else c.act,
                area=c.area,
                issuer=spec.issuer if spec else None,
                source_url=spec.source_url if spec else None,
                sections=0,
                chunks=0,
                builtin=c.document_id in builtin,
                source_files=[],
            ),
        )
        row.chunks += 1
        row.sections += 1 if c.part in (None, 1) else 0
    for path in PROCESSED.glob("*.jsonl"):
        if path.name == "all_documents.jsonl" or path.stem not in rows:
            continue
        import json

        lines = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        rows[path.stem].sections = len(lines)
        rows[path.stem].source_files = sorted({ln.get("source_file", "") for ln in lines})[:50]
    return sorted(rows.values(), key=lambda r: (r.area, r.title))


def records_for(document_id: str) -> list[SectionRecord]:
    from app.ingestion.dataset_indexer import dataset_step_of
    from app.ingestion.jsonl_loader import read_jsonl

    path = PROCESSED / f"{document_id}.jsonl"
    if path.exists():
        return read_jsonl(path)
    step = dataset_step_of(document_id)  # built-in dataset documents live in one file per step
    if step is None or not (PROCESSED / f"{step}.jsonl").exists():
        return []
    import json

    out: list[SectionRecord] = []
    with (PROCESSED / f"{step}.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            if f'"document_id": "{document_id}"' in line:
                raw = json.loads(line)
                if raw.get("document_id") == document_id:
                    out.append(SectionRecord(**raw))
    return out
