"""End-to-end evaluation on data/evaluation/gold.jsonl. Reports only measured numbers.

Usage (from backend/):
    LLM_MODEL=openai/gpt-oss-20b python scripts/run_eval.py [--sleep 3] [--fresh] [--limit N]

- Runs the real /chat pipeline (Call 1 → retrieval → gates → Call 2 → validation) for every row, with a
  fresh in-memory cache (no cached answers) and DB logging off. Throttled for the Groq free tier;
  progress is checkpointed so an interrupted run resumes (use --fresh to start over).
- Retrieval ablation (dense-only / BM25-only / hybrid) and the RETRIEVAL_MIN_SCORE trade-off use the
  retriever directly (no LLM calls).
- Metrics needing labels (Recall@5, MRR, must_include …) only use rows a human has filled in.
Results: data/evaluation/results.json (timestamp, model, sample counts).
"""

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import DATA_DIR, settings  # noqa: E402
from app.evaluation.answer_metrics import includes_all, percentile, violates  # noqa: E402
from app.evaluation.retrieval_metrics import recall_at_k, reciprocal_rank, section_level  # noqa: E402
from app.models.llm_client import LLMClient, LLMError, LLMRateLimited  # noqa: E402
from app.schemas.chat import ChatRequest  # noqa: E402
from app.services.answer_cache import MemoryCache  # noqa: E402
from app.services.orchestrator import Orchestrator  # noqa: E402
from app.services.retrieval_service import get_retriever  # noqa: E402

EVAL_DIR = DATA_DIR / "evaluation"
K = 5
THRESHOLDS = [0.70, 0.72, 0.74, 0.76, 0.78, 0.80, 0.82, 0.84, 0.86]


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def should_refuse(row: dict) -> bool:
    return row.get("variant") == "off_topic" or bool(row.get("should_refuse"))


def _match_ids(ranked_chunks: list[str], expected: set[str], index_ids: set[str]) -> list[str]:
    sections = set(section_level(list(index_ids)))
    return section_level(ranked_chunks) if expected & sections else ranked_chunks


async def run_pipeline(rows: list[dict], checkpoint: Path, sleep_s: float) -> dict[str, dict]:
    done: dict[str, dict] = {}
    if checkpoint.exists():
        for line in checkpoint.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["id"]] = rec
    orch = Orchestrator(get_retriever(), LLMClient(), MemoryCache())
    todo = [r for r in rows if r["id"] not in done]
    print(f"pipeline: {len(done)} already done (checkpoint), {len(todo)} to run, sleeping {sleep_s}s between rows")
    with checkpoint.open("a", encoding="utf-8") as ck:
        for i, row in enumerate(todo, start=1):
            for attempt in range(3):
                try:
                    resp = await orch.run(ChatRequest(message=row["question"], debug=True))
                    rec = {"id": row["id"], "ok": True, **resp.model_dump(exclude={"request_id"})}
                    break
                except LLMRateLimited:
                    wait = 20 * (attempt + 1)
                    print(f"  rate limited on {row['id']}; waiting {wait}s")
                    await asyncio.sleep(wait)
                except LLMError as exc:
                    rec = {"id": row["id"], "ok": False, "error": type(exc).__name__}
                    break
            else:
                rec = {"id": row["id"], "ok": False, "error": "rate_limited"}
            done[row["id"]] = rec
            ck.write(json.dumps(rec, ensure_ascii=False) + "\n")
            ck.flush()
            status = rec.get("status", rec.get("error"))
            print(f"  [{len(done)}/{len(rows)}] {row['id']:<18} {status:<9} {rec.get('latency_ms', '-')} ms")
            if i < len(todo):
                await asyncio.sleep(sleep_s)
    return done


async def run_retrieval(rows: list[dict]) -> dict:
    retriever = get_retriever()
    index_ids = set(retriever.chunks)
    ablation: dict[str, dict[str, float | int]] = {}
    gate_inputs: list[dict] = []
    for mode in ("dense", "bm25", "hybrid"):
        recalls, rrs = [], []
        for row in rows:
            res = await retriever.retrieve(row["question"], area=None, mode=mode, top_n=10)
            if mode == "hybrid":
                gate_inputs.append(
                    {
                        "id": row["id"],
                        "refuse": should_refuse(row),
                        "labelled": bool(row.get("expected_chunk_ids")),
                        "best_dense": res.best_dense_score,
                        "bm25_top3": res.bm25_hit_in_top(3),
                        "exact": any(c.exact_section for c in res.candidates),
                    }
                )
            expected = set(row.get("expected_chunk_ids") or [])
            if not expected:
                continue
            ranked = _match_ids([c.chunk_id for c in res.candidates], expected, index_ids)
            recalls.append(recall_at_k(ranked, expected, K))
            rrs.append(reciprocal_rank(ranked, expected))
        n = len(recalls)
        ablation[mode] = {
            "n": n,
            "recall@5": round(sum(recalls) / n, 4) if n else None,
            "mrr": round(sum(rrs) / n, 4) if n else None,
        }

    tradeoff = []
    answerable = [g for g in gate_inputs if g["labelled"] and not g["refuse"]]
    refusable = [g for g in gate_inputs if g["refuse"]]
    for t in THRESHOLDS:

        def gate_refuses(g: dict, t: float = t) -> bool:
            return not g["exact"] and g["best_dense"] < t and not g["bm25_top3"]

        tradeoff.append(
            {
                "threshold": t,
                "answerable_blocked": sum(gate_refuses(g) for g in answerable),
                "n_answerable": len(answerable),
                "off_topic_blocked": sum(gate_refuses(g) for g in refusable),
                "n_off_topic": len(refusable),
            }
        )
    return {"ablation": ablation, "threshold_tradeoff": tradeoff}


def summarize(rows: list[dict], results: dict[str, dict]) -> dict:
    by_id = {r["id"]: r for r in rows}
    ok = [results[r["id"]] for r in rows if results.get(r["id"], {}).get("ok")]
    statuses = Counter(r["status"] for r in ok)
    latencies = [r["latency_ms"] for r in ok]

    refuse_rows = [r for r in rows if should_refuse(r) and results.get(r["id"], {}).get("ok")]
    correct_refusals = sum(results[r["id"]]["status"] == "refused" for r in refuse_rows)
    false_answers = sum(results[r["id"]]["status"] in ("answered", "partial") for r in refuse_rows)

    labelled = [r for r in rows if r.get("expected_chunk_ids") and results.get(r["id"], {}).get("ok")]
    retriever = get_retriever()
    index_ids = set(retriever.chunks)
    recalls, rrs = [], []
    for r in labelled:
        trace = results[r["id"]].get("trace") or {}
        ranked = _match_ids(
            [c["chunk_id"] for c in trace.get("candidates", [])], set(r["expected_chunk_ids"]), index_ids
        )
        recalls.append(recall_at_k(ranked, set(r["expected_chunk_ids"]), K))
        rrs.append(reciprocal_rank(ranked, set(r["expected_chunk_ids"])))

    cited = [c for r in ok for c in r.get("citations", [])]
    valid = 0
    for r in ok:
        retrieved = {c["chunk_id"] for c in (r.get("trace") or {}).get("candidates", [])}
        valid += sum(c["chunk_id"] in index_ids and c["chunk_id"] in retrieved for c in r.get("citations", []))

    inc_rows = [r for r in rows if r.get("must_include") and results.get(r["id"], {}).get("ok")]
    coverage = [includes_all(results[r["id"]]["answer"], r["must_include"]) for r in inc_rows]
    forb_rows = [r for r in rows if r.get("must_not_include") and results.get(r["id"], {}).get("ok")]
    violations = sum(violates(results[r["id"]]["answer"], r["must_not_include"]) for r in forb_rows)

    per_variant = {}
    for variant in sorted({r.get("variant", "?") for r in rows}):
        vr = [results[r["id"]] for r in rows if r.get("variant") == variant and results.get(r["id"], {}).get("ok")]
        per_variant[variant] = dict(Counter(x["status"] for x in vr)) | {"n": len(vr)}

    area_hits = [
        results[r["id"]]["area"] == r["area"] for r in rows if r.get("area") and results.get(r["id"], {}).get("ok")
    ]

    def ratio(a: int | float, b: int) -> float | None:
        return round(a / b, 4) if b else None

    return {
        "n_rows": len(rows),
        "n_completed": len(ok),
        "n_errors": len(rows) - len(ok),
        "status_counts": dict(statuses),
        "per_variant": per_variant,
        "area_detection_accuracy": {"value": ratio(sum(area_hits), len(area_hits)), "n": len(area_hits)},
        "correct_refusal_rate": {"value": ratio(correct_refusals, len(refuse_rows)), "n": len(refuse_rows)},
        "false_answer_rate": {"value": ratio(false_answers, len(refuse_rows)), "n": len(refuse_rows)},
        "citation_validity_rate": {"value": ratio(valid, len(cited)), "n": len(cited)},
        "recall@5": {"value": ratio(sum(recalls), len(recalls)), "n": len(recalls)},
        "mrr": {"value": ratio(sum(rrs), len(rrs)), "n": len(rrs)},
        "must_include_coverage": {"value": ratio(sum(coverage), len(coverage)), "n": len(coverage)},
        "must_not_include_violations": {"value": violations, "n": len(forb_rows)},
        "latency_ms": {"p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95), "n": len(latencies)},
        "unlabelled_rows": sum(1 for r in by_id.values() if not r.get("expected_chunk_ids") and not should_refuse(r)),
    }


def fmt(v: dict) -> str:
    return "n/a (n=0)" if v.get("value") is None else f"{v['value']:.3f} (n={v['n']})"


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", type=Path, default=EVAL_DIR / "gold.jsonl")
    ap.add_argument("--sleep", type=float, default=3.0, help="seconds between pipeline rows (free-tier limits)")
    ap.add_argument("--fresh", action="store_true", help="ignore the checkpoint")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    settings.database_url = None  # no query_logs / Postgres cache writes from evaluation runs
    if not settings.llm_model:
        print("FAIL  LLM_MODEL is not set (e.g. LLM_MODEL=openai/gpt-oss-20b python scripts/run_eval.py)")
        return 1
    rows = load_rows(args.file)[: args.limit]
    checkpoint = EVAL_DIR / f"checkpoint_{args.file.stem}_{settings.llm_model.replace('/', '_')}.jsonl"
    if args.fresh and checkpoint.exists():
        checkpoint.unlink()

    t0 = time.perf_counter()
    results = await run_pipeline(rows, checkpoint, args.sleep)
    retrieval = await run_retrieval(rows)
    summary = summarize(rows, results)

    print(f"\n== {args.file.name}: {summary['n_completed']}/{summary['n_rows']} completed, model {settings.llm_model}")
    print(f"status counts            {summary['status_counts']}")
    for key in ("area_detection_accuracy", "correct_refusal_rate", "false_answer_rate", "citation_validity_rate",
                "recall@5", "mrr", "must_include_coverage"):  # fmt: skip
        print(f"{key:<25} {fmt(summary[key])}")
    lat = summary["latency_ms"]
    if lat["p50"] is not None:
        print(f"{'latency p50 / p95':<25} {lat['p50']:.0f} / {lat['p95']:.0f} ms (n={lat['n']})")
    print(f"unlabelled rows          {summary['unlabelled_rows']} (fill expected_chunk_ids / must_include)")

    print("\nretrieval ablation (labelled rows only)")
    for mode, m in retrieval["ablation"].items():
        val = "n/a" if m["recall@5"] is None else f"Recall@5 {m['recall@5']:.3f}  MRR {m['mrr']:.3f}"
        print(f"  {mode:<7} {val}  (n={m['n']})")

    print("\nRETRIEVAL_MIN_SCORE trade-off (score gate only; Call 1 also refuses off-topic)")
    print(f"  {'thr':>5}  {'answerable blocked':>18}  {'off-topic blocked':>17}")
    for t in retrieval["threshold_tradeoff"]:
        blocked = f"{t['answerable_blocked']:>10}/{t['n_answerable']:<7}"
        print(f"  {t['threshold']:>5.2f}  {blocked}  {t['off_topic_blocked']:>9}/{t['n_off_topic']}")
    print(f"  current RETRIEVAL_MIN_SCORE = {settings.retrieval_min_score} (not changed automatically)")

    out = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "gold_file": args.file.name,
        "model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "retrieval_min_score": settings.retrieval_min_score,
        "corpus_chunks": len(get_retriever().chunks),
        "areas_indexed": sorted({c.area for c in get_retriever().chunks.values()}),
        "summary": summary,
        **retrieval,
        "duration_s": round(time.perf_counter() - t0, 1),
    }
    (EVAL_DIR / "results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved data/evaluation/results.json ({out['duration_s']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
