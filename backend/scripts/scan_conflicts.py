"""Find candidate official-source conflicts in the real corpus (no LLM calls) and score labelled ones.

Runs the real retrieval for each question, then the rule-based conflict check (claims, context matching,
resolution) on the passages Call 2 would see, and writes one JSON line per pair for a human to label:
`human_label` is left empty (CLAUDE.md: humans fill expected answers). Fill it with one of
conflict | context_difference | temporal_difference | no_conflict | extraction_error, then run --metrics.

Usage (from backend/):
    python scripts/scan_conflicts.py                       # probe questions + gold.jsonl, BM25 only (light)
    python scripts/scan_conflicts.py --mode hybrid         # as the API retrieves (loads e5, needs Qdrant)
    python scripts/scan_conflicts.py --metrics data/evaluation/conflict_candidates.jsonl
"""

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import DATA_DIR  # noqa: E402
from app.services.conflict_disclosure import prepare  # noqa: E402
from app.services.generation_service import label_chunks  # noqa: E402
from app.services.retrieval_service import get_retriever  # noqa: E402

GOLD = DATA_DIR / "evaluation" / "gold.jsonl"
OUT = DATA_DIR / "evaluation" / "conflict_candidates.jsonl"
# questions only (no answers): topics where documents state fees, amounts, ages or time limits
PROBES = [
    "বয়স্ক ভাতার মাসিক পরিমাণ কত?",
    "বিধবা ভাতার পরিমাণ কত টাকা?",
    "প্রতিবন্ধী ভাতার পরিমাণ কত?",
    "বয়স্ক ভাতা পাওয়ার বয়স কত?",
    "বয়স্ক ভাতার জন্য আয়সীমা কত?",
    "নামজারি ফি কত টাকা?",
    "নামজারি করতে কত দিন সময় লাগে?",
    "ভূমি উন্নয়ন কর কত?",
    "জিডি করতে কত টাকা লাগে?",
    "বয়স্ক ভাতার জন্য কী কী কাগজ লাগবে?",
    "শ্রমিকের মজুরি কত দিনের মধ্যে দিতে হয়?",
]
FLAGGED = {"DIRECT_CONFLICT", "POSSIBLE_CONFLICT", "RESOLVED"}


def questions(include_gold: bool) -> list[str]:
    out = list(PROBES)
    if include_gold and GOLD.exists():
        for line in GOLD.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line)["question"])
    return list(dict.fromkeys(out))


async def scan(mode: str, include_gold: bool, out: Path) -> None:
    retriever = get_retriever()
    rows: list[dict] = []
    for q in questions(include_gold):
        result = await retriever.retrieve(q, area=None, mode=mode)
        run = prepare(label_chunks(result.top_chunks()), q, retriever.programmes())
        for pair in run.pairs:
            rows.append(
                {
                    "question": q,
                    "pair": pair.id,
                    "category": pair.a.category,
                    "status": pair.status,
                    "resolution": pair.resolution,
                    "reasons": pair.reasons,
                    "sides": [
                        {
                            "chunk_id": c.chunk_id,
                            "value": c.original_text,
                            "quote": c.quote,
                            "source_type": run.profiles[c.label].source_type,
                            "title": run.profiles[c.label].title,
                        }
                        for c in (pair.a, pair.b)
                    ],
                    "human_label": "",
                }
            )
        print(f"{len(run.claims):3} claims, {len(run.pairs)} pairs  {q}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"\n{len(rows)} pairs → {out}")
    print("by status:", dict(Counter(r["status"] for r in rows)))


def metrics(path: Path) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    labelled = [r for r in rows if r.get("human_label")]
    if not labelled:
        print("no human_label filled yet")
        return
    flagged = [r for r in labelled if r["status"] in FLAGGED]
    true_conflicts = [r for r in labelled if r["human_label"] == "conflict"]
    tp = sum(r["human_label"] == "conflict" for r in flagged)
    context_ok = sum(
        (r["status"] == "CONTEXT_DIFFERENCE") == (r["human_label"] == "context_difference") for r in labelled
    )
    print(f"labelled pairs: {len(labelled)}")
    print(f"conflict precision: {tp}/{len(flagged)}" + (f" = {tp / len(flagged):.2f}" if flagged else ""))
    print(
        f"conflict recall:    {tp}/{len(true_conflicts)}"
        + (f" = {tp / len(true_conflicts):.2f}" if true_conflicts else "")
    )
    print(f"false conflict rate: {(len(flagged) - tp)}/{len(labelled)}")
    print(f"context matching agreement: {context_ok}/{len(labelled)}")
    print("note: recall counts only pairs the scanner produced; conflicts it never paired are not visible here")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="bm25", choices=["bm25", "hybrid"])
    parser.add_argument("--no-gold", action="store_true", help="probe questions only")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--metrics", type=Path, help="score a labelled candidates file instead of scanning")
    args = parser.parse_args()
    if args.metrics:
        metrics(args.metrics)
    else:
        asyncio.run(scan(args.mode, not args.no_gold, args.out))


if __name__ == "__main__":
    main()
