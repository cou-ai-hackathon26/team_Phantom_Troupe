"""Incremental, per-step indexing of data/DataSet (used by scripts/ingest_dataset.py).

A step's outputs:
- data/processed/<step>.jsonl          section records (input to the old full rebuild too)
- data/processed/chunks/<step>.jsonl   chunk cache: BM25 is rebuilt from all caches without re-chunking
- data/dataset_registry.json           step -> document specs (built-in documents, never deletable in /admin)
Indexing a step replaces exactly that step's documents in Qdrant and Postgres (batched writes) and
embeds only its chunks, so earlier steps are never re-embedded. Re-running a step is idempotent.
"""

import json
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from qdrant_client import models
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import DATA_DIR, settings
from app.ingestion.area_map import DocumentSpec
from app.ingestion.jsonl_loader import rebuild_all_documents, write_jsonl
from app.repositories.bm25_repository import BM25Index
from app.repositories.qdrant_repository import QdrantRepository, point_id_for
from app.schemas.ingestion import ChunkRecord, SectionRecord

PROCESSED = DATA_DIR / "processed"
CHUNKS_DIR = PROCESSED / "chunks"
DATASET_REGISTRY = DATA_DIR / "dataset_registry.json"
QDRANT_BATCH = 128
PG_BATCH = 500


# ---------------------------------------------------------------------------- registry


def load_dataset_registry(path: Path | None = None) -> dict[str, list[DocumentSpec]]:
    path = path or DATASET_REGISTRY
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {step: [DocumentSpec(**d) for d in docs] for step, docs in raw.items()}


def dataset_specs(path: Path | None = None) -> dict[str, DocumentSpec]:
    return {s.document_id: s for docs in load_dataset_registry(path).values() for s in docs}


def dataset_step_of(document_id: str) -> str | None:
    for step, docs in load_dataset_registry().items():
        if any(d.document_id == document_id for d in docs):
            return step
    return None


def _save_registry(registry: dict[str, list[DocumentSpec]], path: Path) -> None:
    data = {step: [asdict(s) for s in docs] for step, docs in registry.items()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------- chunk cache


def write_chunk_cache(step: str, chunks: Sequence[ChunkRecord], chunks_dir: Path | None = None) -> Path:
    path = (chunks_dir or CHUNKS_DIR) / f"{step}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c.model_dump(), ensure_ascii=False) + "\n")
    return path


def load_cached_chunks(chunks_dir: Path | None = None) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    for path in sorted((chunks_dir or CHUNKS_DIR).glob("*.jsonl")):
        with path.open(encoding="utf-8") as f:
            chunks += [ChunkRecord(**json.loads(line)) for line in f if line.strip()]
    return chunks


# ---------------------------------------------------------------------------- stores


@dataclass
class StepReport:
    step: str
    documents: int
    sections: int
    chunks: int
    total_chunks: int  # in all caches
    qdrant: int
    bm25: int
    postgres: int | None
    seconds: float

    @property
    def consistent(self) -> bool:
        counts = {self.total_chunks, self.qdrant, self.bm25} | ({self.postgres} if self.postgres is not None else set())
        return len(counts) == 1


async def replace_in_qdrant(
    repo: QdrantRepository, document_ids: Sequence[str], chunks: Sequence[ChunkRecord], vectors: np.ndarray
) -> None:
    if document_ids:
        for start in range(0, len(document_ids), 500):
            await repo.client.delete(
                repo.collection,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id", match=models.MatchAny(any=list(document_ids[start : start + 500]))
                            )
                        ]
                    )
                ),
                wait=True,
            )
    for start in range(0, len(chunks), QDRANT_BATCH):
        batch = chunks[start : start + QDRANT_BATCH]
        await repo.upsert(
            [c.id for c in batch],
            vectors[start : start + QDRANT_BATCH].tolist(),
            [
                {
                    "area": c.area,
                    "act": c.act,
                    "section": c.section,
                    "citation": c.citation,
                    "document_id": c.document_id,
                }
                for c in batch
            ],
        )


async def replace_in_postgres(
    document_ids: Sequence[str],
    specs: Sequence[DocumentSpec],
    chunks: Sequence[ChunkRecord],
    source_files: dict[str, str],
) -> int:
    from app.db.models import Chunk, Document
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        for start in range(0, len(document_ids), PG_BATCH):
            # chunks go with their document (ON DELETE CASCADE)
            await session.execute(delete(Document).where(Document.id.in_(document_ids[start : start + PG_BATCH])))
        doc_rows = [
            {
                "id": s.document_id,
                "title": s.title,
                "area": s.area,
                "issuer": s.issuer,
                "source_url": s.source_url,
                "source_file": source_files.get(s.document_id),
                "language": s.language,
            }
            for s in specs
        ]
        for start in range(0, len(doc_rows), PG_BATCH):
            await session.execute(insert(Document), doc_rows[start : start + PG_BATCH])
        chunk_rows = [{**c.model_dump(), "qdrant_point_id": point_id_for(c.id)} for c in chunks]
        for start in range(0, len(chunk_rows), PG_BATCH):
            await session.execute(insert(Chunk), chunk_rows[start : start + PG_BATCH])
        await session.commit()
        return int((await session.execute(select(func.count()).select_from(Chunk))).scalar_one())


def rebuild_bm25(path: Path | None = None) -> int:
    chunks = load_cached_chunks()
    path = path or settings.bm25_path
    if not chunks:
        path.unlink(missing_ok=True)
        return 0
    BM25Index.build(chunks).save(path)
    return len(chunks)


# ---------------------------------------------------------------------------- one step


def save_step(step: str, specs: list[DocumentSpec], records: list[SectionRecord]) -> list[str]:
    """Write the step's section JSONL and registry entry; returns the document ids it replaces."""
    registry = load_dataset_registry()
    previous = [s.document_id for s in registry.get(step, [])]
    registry[step] = specs
    _save_registry(registry, DATASET_REGISTRY)
    write_jsonl(records, PROCESSED / f"{step}.jsonl")
    rebuild_all_documents(PROCESSED)
    return sorted(set(previous) | {s.document_id for s in specs})


async def index_step(
    step: str,
    specs: list[DocumentSpec],
    records: list[SectionRecord],
    chunks: list[ChunkRecord],
    vectors: np.ndarray,
    skip_postgres: bool = False,
) -> StepReport:
    t0 = time.perf_counter()
    replaced = save_step(step, specs, records)
    write_chunk_cache(step, chunks)

    repo = QdrantRepository()
    await repo.ensure_collection(settings.embedding_dim)
    await replace_in_qdrant(repo, replaced, chunks, vectors)
    n_qdrant = await repo.count()

    n_pg: int | None = None
    if not skip_postgres and settings.database_url is not None:
        source_files: dict[str, str] = {}
        for r in records:
            source_files.setdefault(r.document_id, r.source_file)
        n_pg = await replace_in_postgres(replaced, specs, chunks, source_files)

    n_bm25 = rebuild_bm25()
    return StepReport(
        step=step,
        documents=len(specs),
        sections=len(records),
        chunks=len(chunks),
        total_chunks=n_bm25,
        qdrant=n_qdrant,
        bm25=n_bm25,
        postgres=n_pg,
        seconds=time.perf_counter() - t0,
    )


async def wipe_all(skip_postgres: bool = False) -> None:
    """Empty every store: Qdrant collection recreated, Postgres documents/chunks/answer_cache deleted,
    processed outputs, registries and the BM25 pickle removed."""
    repo = QdrantRepository()
    await repo.recreate(settings.embedding_dim)
    if not skip_postgres and settings.database_url is not None:
        from sqlalchemy import text

        from app.db.session import get_sessionmaker

        async with get_sessionmaker()() as session:
            await session.execute(text("delete from chunks"))
            await session.execute(text("delete from documents"))
            await session.execute(text("delete from answer_cache"))
            await session.commit()
    for path in [*PROCESSED.glob("*.jsonl"), *CHUNKS_DIR.glob("*.jsonl")]:
        path.unlink()
    for path in (
        DATASET_REGISTRY,
        DATA_DIR / "sources_registry.json",
        DATA_DIR / "sources_log.csv",
        settings.bm25_path,
    ):
        path.unlink(missing_ok=True)
