"""Run the team's 18-case regional-dialect suite (data/evaluation/dialect_suite.json) through the /chat pipeline.

Usage (from backend/):
    python scripts/run_dialect_suite.py              # resumable; ~10 min, ~36 Groq calls (2 per case)
    python scripts/run_dialect_suite.py --fresh      # start over
    python scripts/run_dialect_suite.py --only TC-06 TC-13
    python scripts/run_dialect_suite.py --report     # print the table from saved results

Same orchestrator as the API (web fallback included), fresh in-memory cache. Graded in code:
PASS = answered/partial, area in the case's areas, every expected law cited (matched by act-title keywords;
"@gd" = any gd-area citation), and answer_must words present. PARTIAL = answered with some laws cited.
The expected laws come from the team's test suite, not from us. Results: data/evaluation/results/dialect_suite.jsonl
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import DATA_DIR  # noqa: E402

CASES = DATA_DIR / "evaluation" / "dialect_suite.json"
OUT = DATA_DIR / "evaluation" / "results" / "dialect_suite.jsonl"
SLEEP = 20


def load_done() -> dict[str, dict]:
    if not OUT.exists():
        return {}
    return {r["id"]: r for r in (json.loads(x) for x in OUT.read_text(encoding="utf-8").splitlines() if x.strip())}


def law_hit(pats: list[str], cites: list[dict]) -> bool:
    for c in cites:
        hay = f"{c['act']} {c['title']} {c['citation']}".lower()
        for p in pats:
            if p == "@gd":
                if c.get("area") == "gd":
                    return True
            elif p.lower() in hay:
                return True
    return False


def grade(case: dict, rec: dict) -> dict:
    if not rec.get("ok"):
        return {"verdict": "ERROR"}
    cites = rec["citations"]
    laws = {name: law_hit(p, cites) for name, p in case["laws"].items()}
    area_ok = rec["area"] in case["areas"]
    answered = rec["status"] in ("answered", "partial")
    extra = True
    if case.get("answer_must"):
        extra = any(w in rec["answer"] for w in case["answer_must"])
    secs = [s for s in case.get("sections", []) if any(s in c["section"] or s in c["citation"] for c in cites)]
    hits = sum(laws.values())
    if answered and area_ok and extra and hits == len(laws):
        verdict = "PASS"
    elif answered and hits > 0:
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"
    return {
        "verdict": verdict,
        "area_ok": area_ok,
        "answered": answered,
        "laws": laws,
        "sections": secs,
        "extra": extra,
    }


async def run(only: list[str]) -> None:
    from app.core.config import settings
    from app.models.llm_client import LLMClient, LLMRateLimited
    from app.schemas.chat import ChatRequest
    from app.services.answer_cache import MemoryCache
    from app.services.orchestrator import Orchestrator
    from app.services.retrieval_service import get_retriever
    from app.services.web_search import get_web_search

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    done = load_done()
    todo = [c for c in cases if c["id"] not in done and (not only or c["id"] in only)]
    web = "on" if get_web_search() else "off"
    print(f"model={settings.llm_model} web={web}; {len(done)} done, {len(todo)} to run", flush=True)
    retriever = get_retriever()
    orch = Orchestrator(retriever, LLMClient(), MemoryCache(), web=get_web_search())
    t0 = time.time()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        for i, case in enumerate(todo, 1):
            rec = None
            for attempt in range(3):
                try:
                    resp = await orch.run(ChatRequest(message=case["q"], debug=True))
                    d = resp.model_dump(exclude={"request_id", "speech_token"})
                    for c in d["citations"]:
                        ch = retriever.chunks.get(c["chunk_id"])
                        c["area"] = ch.area if ch else None
                    rec = {"id": case["id"], "ok": True, **d}
                    break
                except LLMRateLimited:
                    print(f"  rate limited, waiting {30 * (attempt + 1)}s", flush=True)
                    await asyncio.sleep(30 * (attempt + 1))
                except Exception as exc:  # noqa: BLE001
                    rec = {"id": case["id"], "ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
                    break
            rec = rec or {"id": case["id"], "ok": False, "error": "rate_limited"}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            g = grade(case, rec)
            eta = (time.time() - t0) / i * (len(todo) - i)
            print(
                f"[{i}/{len(todo)}] {case['id']} {rec.get('status', rec.get('error'))} area={rec.get('area')} "
                f"-> {g['verdict']}  (ETA {eta / 60:.1f} min)",
                flush=True,
            )
            if i < len(todo):
                await asyncio.sleep(SLEEP)


def report() -> None:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    done = load_done()
    tally: dict[str, int] = {}
    for case in cases:
        rec = done.get(case["id"])
        if not rec:
            print(f"{case['id']}  (not run)")
            continue
        g = grade(case, rec)
        tally[g["verdict"]] = tally.get(g["verdict"], 0) + 1
        if not rec.get("ok"):
            print(f"{case['id']}  ERROR {rec['error']}")
            continue
        laws = ", ".join(f"{'✓' if v else '✗'} {k}" for k, v in g["laws"].items())
        print(
            f"{case['id']} {g['verdict']:<7} status={rec['status']:<8} area={rec['area']:<9}"
            f"(want {'/'.join(case['areas'])}) gate={rec['trace']['gate']}"
        )
        print(
            f"        laws: {laws}"
            + (f" | sections: {g['sections']}" if case.get("sections") else "")
            + ("" if g["extra"] else " | ✗ no এজাহার/মামলা")
        )
        print("        normalized:", rec["normalized_question"][:160])
        for c in rec["citations"]:
            print(f"        [{c['marker']}] {c['kind']:<8} {c['citation'][:90]}")
    print("\nTOTAL:", tally)


if __name__ == "__main__":
    args = sys.argv[1:]
    only = [a for a in args if a.startswith("TC-")]
    if "--fresh" in args and OUT.exists():
        OUT.unlink()
    elif only and OUT.exists():  # rerun just these cases
        lines = OUT.read_text(encoding="utf-8").splitlines()
        keep = [x for x in lines if x.strip() and json.loads(x)["id"] not in only]
        OUT.write_text("".join(k + "\n" for k in keep), encoding="utf-8")
    if "--report" not in args:
        asyncio.run(run(only))
    report()
