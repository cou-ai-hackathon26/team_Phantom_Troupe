"""Local BM25 index (rank_bm25) over chunk normalized_text, pickled with the chunk-id order.

The pickle also carries each chunk's display metadata, so retrieval and citations keep working
from the local file if Postgres is unreachable (weak venue internet).
"""

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.ingestion.text_normalizer import tokenize
from app.schemas.ingestion import ChunkRecord

FORMAT_VERSION = 1


@dataclass
class SparseHit:
    chunk_id: str
    score: float
    rank: int  # 1-based


class BM25Index:
    def __init__(self, chunk_ids: list[str], bm25: BM25Okapi, chunks: dict[str, ChunkRecord]) -> None:
        self.chunk_ids = chunk_ids
        self.bm25 = bm25
        self.chunks = chunks

    @classmethod
    def build(cls, chunks: list[ChunkRecord]) -> "BM25Index":
        if not chunks:
            raise ValueError("cannot build a BM25 index with no chunks")
        corpus = [tokenize(c.normalized_text) for c in chunks]
        return cls([c.id for c in chunks], BM25Okapi(corpus), {c.id: c for c in chunks})

    def __len__(self) -> int:
        return len(self.chunk_ids)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("wb") as f:
            pickle.dump(
                {
                    "version": FORMAT_VERSION,
                    "chunk_ids": self.chunk_ids,
                    "bm25": self.bm25,
                    "chunks": {cid: c.model_dump() for cid, c in self.chunks.items()},
                },
                f,
            )
        tmp.replace(path)  # atomic: a running API never sees a half-written file

    @classmethod
    def load(cls, path: Path) -> "BM25Index":
        with path.open("rb") as f:
            data = pickle.load(f)  # noqa: S301 - our own file, written by save()
        if data.get("version") != FORMAT_VERSION:
            raise RuntimeError(f"{path} has an old format; re-run ingestion")
        chunks = {cid: ChunkRecord(**c) for cid, c in data["chunks"].items()}
        return cls(data["chunk_ids"], data["bm25"], chunks)

    def shared_term_weight(self, query: str, chunk_id: str, min_idf: float) -> float:
        """Sum of the IDF of query terms that also occur in the chunk, counting only distinctive terms
        (IDF >= min_idf, i.e. not words found in a large share of all chunks). 0.0 = no meaningful overlap."""
        chunk = self.chunks.get(chunk_id)
        if chunk is None:
            return 0.0
        shared = set(tokenize(query)) & set(tokenize(chunk.normalized_text))
        idf = self.bm25.idf
        return float(sum(w for t in shared if (w := idf.get(t, 0.0)) >= min_idf))

    def search(self, query: str, top_k: int, area: str | None = None) -> list[SparseHit]:
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = np.asarray(self.bm25.get_scores(tokens))
        order = np.argsort(-scores)
        hits: list[SparseHit] = []
        for idx in order:
            if scores[idx] <= 0 or len(hits) >= top_k:
                break
            cid = self.chunk_ids[idx]
            if area and self.chunks[cid].area != area:
                continue
            hits.append(SparseHit(chunk_id=cid, score=float(scores[idx]), rank=len(hits) + 1))
        return hits
