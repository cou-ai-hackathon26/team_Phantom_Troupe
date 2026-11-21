"""Ingestion core: data/processed/all_documents.jsonl -> chunks -> Qdrant + BM25 (+ Postgres).

Used by scripts/ingest_jsonl.py and scripts/ingest_pdf.py. Idempotent (deterministic ids, stale cleanup).
"""

import time
from collections import Counter

from app.core.config import DATA_DIR, settings
from app.ingestion.chunker import chunk_section, model_token_counter
from app.ingestion.embedder import embed_chunks
from app.ingestion.indexer import write_bm25, write_postgres, write_qdrant
from app.ingestion.jsonl_loader import ALL_DOCUMENTS, read_jsonl
from app.models.embedding_client import get_embedding_client
from app.repositories.qdrant_repository import QdrantRepository


async def ingest_all(skip_postgres: bool = False, recreate: bool = False) -> int:
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
