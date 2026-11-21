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
