"""Compare Groq chat models on fixed Bangla prompts, side by side, to choose LLM_MODEL.

Usage (from backend/):
    python scripts/test_llm_models.py openai/gpt-oss-120b qwen/qwen3.8-27b
    python scripts/test_llm_models.py openai/gpt-oss-120b --with-answer   # also run retrieval + Call 2

Prints Call 1 output (normalized question, area, in_scope) and latency per model. With --with-answer,
also prints the grounded answer, its status and citations from the real index.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.llm_client import LLMClient, LLMError  # noqa: E402
from app.services.citation_validator import validate_answer  # noqa: E402
from app.services.generation_service import generate_answer, label_chunks  # noqa: E402
from app.services.query_normalizer import normalize_query  # noqa: E402

PROMPTS: list[tuple[str, str]] = [
    ("standard", "শিক্ষানবিশ শ্রমিকের শিক্ষানবিশীকাল কত দিন হয়?"),
    ("dialect", "লে-অফ অইলে শ্রমিকে কিছু টেকা পাইবো নি? মালিকে কিছু দিবো?"),
    ("banglish", "chakri theke chhatai korle ki ki paona pabo?"),
    ("english", "Does an employer have to give a worker a service book?"),
    ("off_topic", "আজকে ঢাকার আবহাওয়া কেমন থাকবে?"),
]


async def run_model(model: str, with_answer: bool) -> None:
    llm = LLMClient(model=model)
    retriever = None
    if with_answer:
        from app.services.retrieval_service import get_retriever

        retriever = get_retriever()
    print(f"\n{'=' * 100}\nMODEL {model}\n{'=' * 100}")
    for kind, prompt in PROMPTS:
        print(f"\n[{kind}] {prompt}")
        try:
            t0 = time.perf_counter()
            q = await normalize_query(llm, prompt)
            t1 = time.perf_counter()
            print(
                f"  call1 {int((t1 - t0) * 1000):>5} ms  area={q.area or 'unknown':<9} in_scope={q.in_scope!s:<5} "
                f"clarify={q.needs_clarification!s:<5} json_ok={q.llm_ok}"
            )
            print(f"        → {q.standard_bangla}")
            if not (with_answer and retriever and q.in_scope):
                continue
            result = await retriever.retrieve(q.standard_bangla, area=q.area)
            labelled = label_chunks(result.top_chunks())
            t2 = time.perf_counter()
            answer = await generate_answer(llm, q.standard_bangla, labelled)
            t3 = time.perf_counter()
            v = validate_answer(answer.data, labelled)
            cites = ", ".join(f"[{c.marker}] ধারা {c.section}" for c in v.citations)
            tokens = f"{answer.prompt_tokens}+{answer.completion_tokens}"
            print(f"  call2 {int((t3 - t2) * 1000):>5} ms  status={v.status}  tokens={tokens}  {cites}")
            for line in (v.answer or "(refused)").splitlines():
                print(f"        {line}")
            for w in v.warnings:
                print(f"        ⚠ {w}")
        except LLMError as exc:
            print(f"  ERROR {type(exc).__name__}: {exc}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+")
    parser.add_argument("--with-answer", action="store_true")
    args = parser.parse_args()
    for model in args.models:
        await run_model(model, args.with_answer)


if __name__ == "__main__":
    asyncio.run(main())
