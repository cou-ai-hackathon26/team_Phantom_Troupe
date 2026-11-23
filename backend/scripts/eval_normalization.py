"""Test Call 1 (dialect / Banglish / English -> standard Bangla + area) on data/evaluation/dialect_normalization.jsonl.

Usage (from backend/):
    python scripts/eval_normalization.py                      # LLM_MODEL from .env, prompts/normalize.md
    python scripts/eval_normalization.py --model openai/gpt-oss-20b --sleep 8
    python scripts/eval_normalization.py --prompt-file /tmp/old_normalize.md --tag baseline
    python scripts/eval_normalization.py --only sylhet        # one dialect
    python scripts/eval_normalization.py --fresh              # ignore earlier results of this model+tag

One Groq call per case (Call 1 only; no retrieval, no answer). Results are appended to
data/evaluation/results/normalization_<model>_<tag>.jsonl as they arrive, so an interrupted run resumes.

Automatic checks (labels are properties of the question, not expected answers):
  area       classified area == labelled area
  scope      in_scope == labelled in_scope
  polarity   the rewrite has a negative exactly when the question has one (meaning not reversed)
  person     "I/my" stays first person, "you" stays second person
  dialect    no dialect-only words left in the rewrite
  terms      the labelled key terms are kept
  meaning    the standard words the meaning depends on are there (e.g. অইছে → হয়েছে, not আছে; কেমনে → কীভাবে)
Read every rewrite too: the checks catch dangerous failures, not awkward wording.
"""

import argparse
import asyncio
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import DATA_DIR, settings  # noqa: E402
from app.evaluation.normalization_metrics import (  # noqa: E402
    dialect_leftovers,
    has_negation,
    missing_terms,
    person_ok,
)
from app.models.llm_client import LLMClient, LLMError  # noqa: E402
from app.services import query_normalizer  # noqa: E402

CASES = DATA_DIR / "evaluation" / "dialect_normalization.jsonl"
CHECKS = ("area", "scope", "polarity", "person", "dialect", "terms", "meaning")


def load_cases(only: str | None) -> list[dict]:
    rows = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if not only or r["dialect"] == only or r["id"] == only]


def check(case: dict, out: dict) -> dict[str, bool]:
    text = out["standard_bangla"]
    if not case["in_scope"]:  # off-topic: only area/scope matter
        return {"area": out["area"] == "unknown", "scope": not out["in_scope"]}
    return {
        "area": out["area"] == case["area"],
        "scope": out["in_scope"],
        "polarity": has_negation(text) == case["negated"],
        "person": person_ok(case["person"], text),
        "dialect": not dialect_leftovers(text),
        "terms": not missing_terms(case["must_keep"], text),
        "meaning": not missing_terms(case.get("must_mean", []), text),
    }


async def run(args: argparse.Namespace) -> int:
    model = args.model or settings.llm_model
    if not model:
        print("FAIL  set LLM_MODEL in .env or pass --model")
        return 1
    if args.prompt_file:  # compare another prompt version without touching prompts/normalize.md
        text = Path(args.prompt_file).read_text(encoding="utf-8").strip()
        query_normalizer.load_prompt = lambda _name: text  # type: ignore[assignment]

    safe_model = re.sub(r"[^A-Za-z0-9.-]+", "_", model)
    out_path = DATA_DIR / "evaluation" / "results" / f"normalization_{safe_model}_{args.tag}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if args.fresh and out_path.exists():
        out_path.unlink()
    done = (
        {json.loads(line)["id"]: json.loads(line) for line in out_path.read_text("utf-8").splitlines()}
        if (out_path.exists())
        else {}
    )

    cases = load_cases(args.only)
    todo = [c for c in cases if c["id"] not in done]
    print(f"model {model} · prompt {'file ' + args.prompt_file if args.prompt_file else 'prompts/normalize.md'}")
    print(f"{len(cases)} cases, {len(cases) - len(todo)} already done, {len(todo)} to run")
    if todo:
        print(f"ETA about {len(todo) * (args.sleep + 2) / 60:.0f} min ({args.sleep}s apart for the Groq free tier)\n")

    llm = LLMClient(model=model)
    start = time.perf_counter()
    with out_path.open("a", encoding="utf-8") as fh:
        for n, case in enumerate(todo, start=1):
            try:
                t0 = time.perf_counter()
                q = await query_normalizer.normalize_query(llm, case["question"])
                ms = int((time.perf_counter() - t0) * 1000)
            except LLMError as exc:
                print(f"[{n}/{len(todo)}] {case['id']}: ERROR {type(exc).__name__} (re-run to resume)")
                return 1
            out = {
                "standard_bangla": q.standard_bangla,
                "search_query": q.search_query,
                "area": q.area or "unknown",
                "in_scope": q.in_scope,
                "clarify": q.needs_clarification,
                "json_ok": q.llm_ok,
                "ms": ms,
            }
            row = {"id": case["id"], **out}
            done[case["id"]] = row
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            fails = [k for k, ok in check(case, out).items() if not ok]
            left = (len(todo) - n) * (time.perf_counter() - start) / n / 60
            print(
                f"[{n}/{len(todo)} · ~{left:.0f} min left] {case['id']:<13} {'OK ' if not fails else 'BAD'} "
                f"{','.join(fails)}"
            )
            if n < len(todo):
                await asyncio.sleep(args.sleep)

    # ---- report over all cases of this run (including resumed ones)
    totals: dict[str, list[bool]] = defaultdict(list)
    by_dialect: dict[str, list[bool]] = defaultdict(list)
    print(f"\n{'=' * 110}")
    for case in cases:
        row = done.get(case["id"])
        if row is None:
            continue
        result = check(case, row)
        for k, ok in result.items():
            totals[k].append(ok)
        all_ok = all(result.values())
        by_dialect[case["dialect"]].append(all_ok)
        fails = [k for k, ok in result.items() if not ok]
        extra = []
        if "dialect" in fails:
            extra.append("left: " + " ".join(dialect_leftovers(row["standard_bangla"])))
        if "terms" in fails:
            extra.append("missing: " + " ".join(missing_terms(case["must_keep"], row["standard_bangla"])))
        if "meaning" in fails:
            extra.append("meaning lacks: " + " ".join(missing_terms(case["must_mean"], row["standard_bangla"])))
        if "area" in fails:
            extra.append(f"area {row['area']} (want {case['area']})")
        print(f"{'OK ' if all_ok else 'BAD'} {case['id']:<13} {case['question']}")
        print(f"    → {row['standard_bangla']}")
        if fails:
            print(f"    ✗ {', '.join(fails)}{'  · ' + ' · '.join(extra) if extra else ''}")
    print(f"{'=' * 110}\nchecks passed:")
    for k in CHECKS:
        if totals[k]:
            print(f"  {k:<9} {sum(totals[k]):>3}/{len(totals[k])}")
    print("cases fully OK by dialect:")
    for d, oks in sorted(by_dialect.items()):
        print(f"  {d:<11} {sum(oks)}/{len(oks)}")
    allok = sum(sum(v) for v in by_dialect.values())
    print(f"TOTAL fully OK: {allok}/{sum(len(v) for v in by_dialect.values())}   results: {out_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--prompt-file")
    ap.add_argument("--tag", default="current", help="name for this run's result file")
    ap.add_argument("--only", help="a dialect name or a case id")
    ap.add_argument("--sleep", type=float, default=6.0)
    ap.add_argument("--fresh", action="store_true")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
