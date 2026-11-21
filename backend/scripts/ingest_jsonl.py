"""Idempotent ingestion: data/processed/all_documents.jsonl -> chunks -> Postgres + Qdrant + BM25.

Usage (from backend/):
    python scripts/ingest_jsonl.py                  # all three stores
    python scripts/ingest_jsonl.py --skip-postgres  # until DATABASE_URL is configured
    python scripts/ingest_jsonl.py --recreate       # drop + recreate the Qdrant collection (model change)

Re-running gives identical counts: Postgres rows and Qdrant points are upserted by deterministic ids,
stale chunks are deleted, and the BM25 pickle is rebuilt from the same chunk list.
"""

import argparse
import asyncio
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import DATA_DIR, settings  # noqa: E402
from app.ingestion.chunker import chunk_section, model_token_counter  # noqa: E402
from app.ingestion.embedder import embed_chunks  # noqa: E402
from app.ingestion.indexer import write_bm25, write_postgres, write_qdrant  # noqa: E402
from app.ingestion.jsonl_loader import ALL_DOCUMENTS, read_jsonl  # noqa: E402
from app.models.embedding_client import get_embedding_client  # noqa: E402
from app.repositories.qdrant_repository import QdrantRepository  # noqa: E402


async def run(skip_postgres: bool, recreate: bool) -> int:
    t0 = time.perf_counter()
    source = DATA_DIR / "processed" / ALL_DOCUMENTS
    if not source.exists():
        print(f"FAIL  {source} not found. Run scripts/convert_pdfs.py first (or add the team's JSONL).")
        return 1
    sections = read_jsonl(source)
    print(f"OK    {len(sections)} sections from {source.name}")

    count = model_token_counter(settings.embedding_model)
    chunks = [c for s in sections for c in chunk_section(s, count)]
    split = sum(1 for c in chunks if c.part == 1)
    print(f"OK    {len(chunks)} chunks ({split} sections split; max {max(c.token_count for c in chunks)} tokens)")
    for area, n in sorted(Counter(c.area for c in chunks).items()):
        print(f"        {area:<10} {n} chunks")

    t1 = time.perf_counter()
    client = get_embedding_client()
    vectors = embed_chunks(chunks, client)
    print(f"OK    embedded on {client.device} in {time.perf_counter() - t1:.1f}s, dim {vectors.shape[1]}")
    if vectors.shape[1] != settings.embedding_dim:
        print(f"FAIL  model dim {vectors.shape[1]} != EMBEDDING_DIM {settings.embedding_dim}")
        return 1

    repo = QdrantRepository()
    if recreate:
        await repo.recreate(vectors.shape[1])
    else:
        await repo.ensure_collection(vectors.shape[1])
    n_qdrant = await write_qdrant(repo, chunks, vectors)
    print(f"OK    qdrant '{repo.collection}': {n_qdrant} points")

    n_bm25 = write_bm25(chunks, settings.bm25_path)
    print(f"OK    bm25 {settings.bm25_path.relative_to(DATA_DIR.parent)}: {n_bm25} docs")

    n_pg: int | None = None
    if skip_postgres:
        print("SKIP  postgres (--skip-postgres)")
    else:
        from app.db.session import get_sessionmaker

        source_files = {s.document_id: s.source_file for s in sections}
        async with get_sessionmaker()() as session:
            n_pg = await write_postgres(session, chunks, source_files)
        print(f"OK    postgres chunks: {n_pg} rows")

    counts = {"chunks": len(chunks), "qdrant": n_qdrant, "bm25": n_bm25} | (
        {"postgres": n_pg} if n_pg is not None else {}
    )
    consistent = len(set(counts.values())) == 1
    print(f"{'OK  ' if consistent else 'FAIL'}  counts {counts}")

    sample = next((c for c in chunks if c.part is None and len(c.text) > 200), chunks[0])
    print(f"\nsample [{sample.id}] {sample.citation} — {sample.title}\n{sample.text[:300]}…")
    print(f"\ndone in {time.perf_counter() - t0:.1f}s")
    return 0 if consistent else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-postgres", action="store_true")
    parser.add_argument("--recreate", action="store_true", help="drop and recreate the Qdrant collection")
    args = parser.parse_args()
    return asyncio.run(run(args.skip_postgres, args.recreate))


if __name__ == "__main__":
    raise SystemExit(main())
