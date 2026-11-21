"""Inspect hybrid retrieval for one question.

Usage (from backend/):
    python scripts/try_retrieval.py "মালিক বেতন না দিলে কী করব?" [--area labour] [--mode hybrid|dense|bm25]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.constants import AREAS  # noqa: E402
from app.services.retrieval_service import get_retriever  # noqa: E402


def _fmt(value: float | int | None, spec: str) -> str:
    return "-" if value is None else format(value, spec)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--area", choices=list(AREAS))
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "dense", "bm25"])
    args = parser.parse_args()

    retriever = get_retriever()
    result = await retriever.retrieve(args.question, area=args.area, mode=args.mode)
    print(f"query: {args.question}   area: {args.area or 'all'}   mode: {args.mode}")
    print(f"best dense cosine: {result.best_dense_score:.3f}\n")
    print(f"{'#':>2}  {'fused':>6}  {'dense':>5} {'cos':>5}  {'bm25':>4} {'score':>6}  citation")
    for i, cand in enumerate(result.candidates, start=1):
        chunk = result.chunks[cand.chunk_id]
        part = f" (part {chunk.part})" if chunk.part else ""
        print(
            f"{i:>2}  {cand.fused_score:6.4f}  {_fmt(cand.dense_rank, '>5')} {_fmt(cand.dense_score, '5.3f')}  "
            f"{_fmt(cand.bm25_rank, '>4')} {_fmt(cand.bm25_score, '6.2f')}  {chunk.citation}{part} — {chunk.title}"
        )
        snippet = chunk.text.replace("\n", " ")[:150]
        print(f"    {snippet}…")


if __name__ == "__main__":
    asyncio.run(main())
