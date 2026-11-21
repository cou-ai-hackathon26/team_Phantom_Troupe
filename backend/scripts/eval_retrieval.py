"""Compare dense-only, BM25-only and hybrid retrieval: Recall@5, Hit@5 and MRR.

Usage (from backend/):  python scripts/eval_retrieval.py [--file data/evaluation/retrieval_seed.jsonl]

Rows with an empty expected_chunk_ids list are skipped (fill them in by hand; ids can be section ids
like "labour-act-2006-s4" or chunk ids like "labour-act-2006-s2-p3"). Results are saved to
data/evaluation/retrieval_results.json. Only measured numbers are reported.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import DATA_DIR, settings  # noqa: E402
from app.evaluation.retrieval_metrics import hit_at_k, recall_at_k, reciprocal_rank, section_level  # noqa: E402
from app.services.retrieval_service import get_retriever  # noqa: E402

MODES = ("dense", "bm25", "hybrid")
K = 5


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=DATA_DIR / "evaluation" / "retrieval_seed.jsonl")
    parser.add_argument("--use-area", action="store_true", help="filter retrieval by each row's area")
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.file.read_text(encoding="utf-8").splitlines() if line.strip()]
    labelled = [r for r in rows if r.get("expected_chunk_ids")]
    print(f"{len(rows)} rows, {len(labelled)} labelled ({len(rows) - len(labelled)} skipped: expected ids empty)")
    if not labelled:
        print("Nothing to score yet: fill in expected_chunk_ids, then re-run.")

    retriever = get_retriever()
    available = set(retriever.chunks)
    available_sections = set(section_level(list(available)))
    per_mode: dict[str, dict[str, float]] = {}
    details: list[dict] = []
    for mode in MODES:
        recalls, hits, rrs = [], [], []
        for row in labelled:
            expected = set(row["expected_chunk_ids"])
            unknown = expected - available - available_sections
            if unknown:
                print(f"WARN  {row['id']}: ids not in index: {sorted(unknown)}")
            area = row.get("area") if args.use_area else None
            result = await retriever.retrieve(row["question"], area=area, mode=mode, top_n=max(K, 10))
            ranked_chunks = [c.chunk_id for c in result.candidates]
            # compare at section level when a gold id is a section id
            ranked = section_level(ranked_chunks) if expected & available_sections else ranked_chunks
            recalls.append(recall_at_k(ranked, expected, K))
            hits.append(hit_at_k(ranked, expected, K))
            rrs.append(reciprocal_rank(ranked, expected))
            details.append({"id": row["id"], "mode": mode, "top5": ranked[:K], "expected": sorted(expected)})
        n = len(labelled)
        per_mode[mode] = {
            "recall@5": sum(recalls) / n if n else 0.0,
            "hit@5": sum(hits) / n if n else 0.0,
            "mrr": sum(rrs) / n if n else 0.0,
        }

    print(f"\n{'mode':<8} {'Recall@5':>9} {'Hit@5':>7} {'MRR':>7}   (n={len(labelled)})")
    for mode, m in per_mode.items():
        print(f"{mode:<8} {m['recall@5']:9.3f} {m['hit@5']:7.3f} {m['mrr']:7.3f}")

    out = DATA_DIR / "evaluation" / "retrieval_results.json"
    out.write_text(
        json.dumps(
            {
                "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "file": args.file.name,
                "n_rows": len(rows),
                "n_labelled": len(labelled),
                "area_filter": args.use_area,
                "embedding_model": settings.embedding_model,
                "rrf_k": settings.rrf_k,
                "metrics": per_mode,
                "details": details,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nsaved {out.relative_to(DATA_DIR.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
