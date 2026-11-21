"""Call 2: grounded answer from the top retrieved chunks, cited with short labels [C1]…[C5]."""

from app.models.llm_client import LLMClient, LLMResult
from app.prompts import load_prompt
from app.schemas.ingestion import ChunkRecord
from app.schemas.llm import AnswerOutput


def label_chunks(chunks: list[ChunkRecord]) -> dict[str, ChunkRecord]:
    """Short labels keep the prompt small and stop the model from inventing long chunk ids."""
    return {f"C{i}": chunk for i, chunk in enumerate(chunks, start=1)}


def build_user_message(question: str, labelled: dict[str, ChunkRecord]) -> str:
    passages = []
    for label, chunk in labelled.items():
        part = f" (অংশ {chunk.part})" if chunk.part else ""
        passages.append(f"[{label}] {chunk.citation}{part} — {chunk.title}\n{chunk.text}")
    sources = "\n\n".join(passages)
    return f"প্রশ্ন: {question}\n\n<sources>\n{sources}\n</sources>"


async def generate_answer(llm: LLMClient, question: str, labelled: dict[str, ChunkRecord]) -> LLMResult[AnswerOutput]:
    return await llm.complete_json(
        load_prompt("answer_bn"),
        build_user_message(question, labelled),
        AnswerOutput,
        temperature=0.1,
        max_tokens=1200,
        purpose="answer",
    )
