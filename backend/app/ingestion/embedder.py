"""Embed chunks with the local e5 model ("passage: " prefix, normalized vectors)."""

import logging
import time

import numpy as np

from app.models.embedding_client import EmbeddingClient, get_embedding_client
from app.schemas.ingestion import ChunkRecord

logger = logging.getLogger(__name__)


def embed_chunks(chunks: list[ChunkRecord], client: EmbeddingClient | None = None) -> np.ndarray:
    client = client or get_embedding_client()
    start = time.perf_counter()
    vectors = client.embed_passages([c.embedding_text() for c in chunks])
    logger.info(
        "embedded chunks",
        extra={"data": {"n": len(chunks), "device": client.device, "seconds": round(time.perf_counter() - start, 1)}},
    )
    return vectors
