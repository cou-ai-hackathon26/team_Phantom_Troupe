"""Demo warm-up: wake the free-tier databases, load the embedding model, pre-cache demo answers.

Usage (from backend/):  python scripts/warmup.py [--skip-cache] [--sleep 15] [--tts]

- Supabase and Qdrant free projects pause after inactivity; a query wakes them.
- Pre-caching runs the REAL pipeline for every "- Q…:" line in docs/demo_script.md and stores the
  responses in the answer cache (Postgres when configured), so the running API serves them instantly.
  Only answers the system actually produced are cached — nothing is hand-written.
- --tts also pre-generates the 🔊 audio of each demo answer into data/tts_cache/, so the button plays
  instantly in the demo. It spends ElevenLabs characters (free tier ~10k/month), once per answer.
"""

import argparse
import asyncio
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import REPO_ROOT, settings  # noqa: E402
from app.services.health_service import check_groq, check_postgres, check_qdrant  # noqa: E402

DEMO_SCRIPT = REPO_ROOT / "docs" / "demo_script.md"
_QUESTION = re.compile(r"^-\s*Q\d+:\s*(.+?)\s*$")


def demo_questions(path: Path = DEMO_SCRIPT) -> list[str]:
    return [m.group(1) for line in path.read_text(encoding="utf-8").splitlines() if (m := _QUESTION.match(line))]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-cache", action="store_true")
    ap.add_argument("--sleep", type=float, default=15.0, help="seconds between questions (Groq free-tier TPM)")
    ap.add_argument("--tts", action="store_true", help="also pre-generate answer audio (spends ElevenLabs credits)")
    args = ap.parse_args()

    ok = True
    for name, check in (("postgres", check_postgres), ("qdrant", check_qdrant), ("groq", check_groq)):
        try:
            detail = await asyncio.wait_for(check(), timeout=60)
            print(f"OK    {name:<9} {detail}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"FAIL  {name:<9} {type(exc).__name__}")

    from app.models.embedding_client import get_embedding_client
    from app.services.retrieval_service import get_retriever

    t0 = time.perf_counter()
    retriever = get_retriever()
    await retriever.retrieve("warm up")
    device = get_embedding_client().device
    print(f"OK    embedding {settings.embedding_model} on {device} ({time.perf_counter() - t0:.1f}s)")

    if args.skip_cache:
        return 0 if ok else 1
    if not settings.llm_model:
        print("FAIL  LLM_MODEL is not set in .env; cannot pre-cache answers")
        return 1

    from app.models.llm_client import get_llm_client
    from app.schemas.chat import ChatRequest
    from app.services import tts_service
    from app.services.answer_cache import get_answer_cache
    from app.services.orchestrator import Orchestrator

    if args.tts and not tts_service.is_enabled():
        print("FAIL  --tts: ELEVENLABS_API_KEY is not set or TTS_ENABLED=false")
        return 1

    cache = get_answer_cache()
    orchestrator = Orchestrator(retriever, get_llm_client(), cache)
    questions = demo_questions()
    print(f"\npre-caching {len(questions)} demo questions ({type(cache).__name__}), {args.sleep}s apart")
    for i, q in enumerate(questions, start=1):
        try:
            resp = await orchestrator.run(ChatRequest(message=q))
            print(f"  {'cached ' if resp.cached else 'new    '} {resp.status:<9} {resp.latency_ms:>6} ms  {q}")
            if args.tts:
                spoken = tts_service.clean_for_speech(resp.answer)
                was_cached = tts_service.cached_path(tts_service.audio_key(spoken)) is not None
                path = await tts_service.synthesize_to_cache(resp.answer)
                state = "FAIL   " if path is None else "cached " if was_cached else "new    "
                ok = ok and path is not None
                print(f"    tts {state} {len(spoken):>5} chars")
            if not resp.cached and i < len(questions):
                await asyncio.sleep(args.sleep)
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"  FAIL    {type(exc).__name__}  {q}")
    if type(cache).__name__ == "MemoryCache":
        print("NOTE  DATABASE_URL not set: the cache lived only in this process; the API will not see it")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
