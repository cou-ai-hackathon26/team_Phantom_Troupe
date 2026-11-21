"""Write chunks to the three stores: Postgres (canonical), Qdrant (dense) and BM25 (sparse)."""

from collections.abc import Sequence

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document
from app.ingestion.area_map import PDF_FOLDERS, DocumentSpec
from app.repositories.bm25_repository import BM25Index
from app.repositories.qdrant_repository import QdrantRepository, point_id_for
from app.schemas.ingestion import ChunkRecord

QDRANT_BATCH = 64


def document_specs() -> dict[str, DocumentSpec]:
    from app.ingestion.area_map import JSONL_SOURCE_FILES
    from app.ingestion.source_registry import load_registry

    specs = {s.document_id: s for s in PDF_FOLDERS.values()}
    specs.update({s.document_id: s for s in JSONL_SOURCE_FILES.values()})
    specs.update(load_registry())
    return specs


async def write_postgres(session: AsyncSession, chunks: Sequence[ChunkRecord], source_files: dict[str, str]) -> int:
    specs = document_specs()
    for doc_id in sorted({c.document_id for c in chunks}):
        spec = specs[doc_id]
        values = {
            "id": doc_id,
            "title": spec.title,
            "area": spec.area,
            "issuer": spec.issuer,
            "source_url": spec.source_url,
            "source_file": source_files.get(doc_id),
            "language": spec.language,
        }
        stmt = insert(Document).values(**values)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[Document.id], set_={k: v for k, v in values.items() if k != "id"}
            )
        )

    keep = [c.id for c in chunks]
    await session.execute(delete(Chunk).where(Chunk.id.not_in(keep)))
    for c in chunks:
        values = {
            **c.model_dump(exclude={"id"}),
            "id": c.id,
            "qdrant_point_id": point_id_for(c.id),
        }
        stmt = insert(Chunk).values(**values)
        await session.execute(
            stmt.on_conflict_do_update(index_elements=[Chunk.id], set_={k: v for k, v in values.items() if k != "id"})
        )
    await session.commit()
    return int((await session.execute(select(func.count()).select_from(Chunk))).scalar_one())


async def write_qdrant(repo: QdrantRepository, chunks: Sequence[ChunkRecord], vectors: np.ndarray) -> int:
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
    await repo.delete_missing({c.id for c in chunks})
    return await repo.count()


def write_bm25(chunks: list[ChunkRecord], path) -> int:  # noqa: ANN001 - pathlib.Path
    index = BM25Index.build(chunks)
    index.save(path)
    return len(BM25Index.load(path))
