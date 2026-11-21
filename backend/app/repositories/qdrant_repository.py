"""Qdrant Cloud access: collection setup, idempotent upserts, filtered dense search."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import AsyncQdrantClient, models

from app.core.config import settings

# Fixed namespace: point id = uuid5(NAMESPACE, chunk_id), so re-ingesting overwrites instead of duplicating.
POINT_NAMESPACE = uuid.UUID("6f1c2d64-5b9e-4b8a-9a77-0d4a1b2c3d4e")  # never change: ids would all move


class QdrantNotConfigured(RuntimeError):
    pass


def point_id_for(chunk_id: str) -> uuid.UUID:
    return uuid.uuid5(POINT_NAMESPACE, chunk_id)


@lru_cache
def get_qdrant_client() -> AsyncQdrantClient:
    if not settings.qdrant_url:
        raise QdrantNotConfigured("QDRANT_URL is not set in .env")
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    return AsyncQdrantClient(url=settings.qdrant_url, api_key=api_key, timeout=30)


@dataclass
class DenseHit:
    chunk_id: str
    score: float  # cosine similarity
    rank: int  # 1-based


class QdrantRepository:
    def __init__(self, client: AsyncQdrantClient | None = None, collection: str | None = None) -> None:
        self.client = client or get_qdrant_client()
        self.collection = collection or settings.qdrant_collection

    async def ensure_collection(self, dim: int) -> None:
        if await self.client.collection_exists(self.collection):
            info = await self.client.get_collection(self.collection)
            vectors = info.config.params.vectors
            existing = vectors.size if isinstance(vectors, models.VectorParams) else None
            if existing is not None and existing != dim:
                raise RuntimeError(
                    f"Collection {self.collection!r} has dim {existing}, model gives {dim}. "
                    "Run scripts/ingest_jsonl.py --recreate after changing the embedding model."
                )
        else:
            await self.client.create_collection(
                self.collection,
                vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
            )
        await self.client.create_payload_index(self.collection, "area", models.PayloadSchemaType.KEYWORD)

    async def recreate(self, dim: int) -> None:
        if await self.client.collection_exists(self.collection):
            await self.client.delete_collection(self.collection)
        await self.ensure_collection(dim)

    async def upsert(self, ids: Sequence[str], vectors: Sequence[Sequence[float]], payloads: Sequence[dict]) -> None:
        points = [
            models.PointStruct(id=str(point_id_for(cid)), vector=list(vec), payload={**payload, "chunk_id": cid})
            for cid, vec, payload in zip(ids, vectors, payloads, strict=True)
        ]
        await self.client.upsert(self.collection, points=points, wait=True)

    async def delete_missing(self, keep_chunk_ids: set[str]) -> int:
        """Remove points whose chunk no longer exists (e.g. a section was re-split)."""
        stale: list[str] = []
        offset = None
        while True:
            records, offset = await self.client.scroll(
                self.collection, limit=256, offset=offset, with_payload=["chunk_id"], with_vectors=False
            )
            stale += [str(r.id) for r in records if (r.payload or {}).get("chunk_id") not in keep_chunk_ids]
            if offset is None:
                break
        if stale:
            await self.client.delete(self.collection, points_selector=models.PointIdsList(points=stale))
        return len(stale)

    async def count(self) -> int:
        return (await self.client.count(self.collection, exact=True)).count

    async def search(self, vector: Sequence[float], top_k: int, area: str | None = None) -> list[DenseHit]:
        query_filter = (
            models.Filter(must=[models.FieldCondition(key="area", match=models.MatchValue(value=area))])
            if area
            else None
        )
        result = await self.client.query_points(
            self.collection, query=list(vector), limit=top_k, query_filter=query_filter, with_payload=["chunk_id"]
        )
        return [
            DenseHit(chunk_id=str((p.payload or {})["chunk_id"]), score=float(p.score), rank=i)
            for i, p in enumerate(result.points, start=1)
        ]
