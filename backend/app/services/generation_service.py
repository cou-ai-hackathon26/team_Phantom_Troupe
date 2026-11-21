"""Call 2: grounded answer from the top retrieved chunks, cited with short labels [C1]…[C5]."""

from dataclasses import dataclass, field

from app.ingestion.text_normalizer import ascii_to_bn_digits
from app.models.llm_client import LLMClient, LLMResult
from app.prompts import load_prompt
from app.schemas.ingestion import ChunkRecord
from app.schemas.llm import AnswerOutput


@dataclass
class UserPassageSource:
    """A passage of the user's own document, shaped like a ChunkRecord for the prompt and validator."""

    id: str
    title: str
    citation: str
    text: str
    page: int
    act: str = "আপনার আপলোড করা নথি"
    part: int | None = None
    source_url: str | None = None
    notes: list[str] = field(default_factory=list)
    kind: str = "user"

    @property
    def section(self) -> str:
        return f"পৃষ্ঠা {ascii_to_bn_digits(str(self.page))}"

    def embedding_text(self) -> str:
        return f"{self.citation}\n{self.text}"


def label_chunks(chunks: list[ChunkRecord]) -> dict[str, ChunkRecord]:
    """Short labels keep the prompt small and stop the model from inventing long chunk ids."""
    return {f"C{i}": chunk for i, chunk in enumerate(chunks, start=1)}


def label_user_passages(doc_id: str, filename: str, passages) -> dict[str, UserPassageSource]:  # noqa: ANN001
    return {
        f"U{i}": UserPassageSource(
            id=f"user:{doc_id[:8]}:{p.index}",
            title=filename,
            citation=f"আপনার নথি ({filename}), পৃষ্ঠা {ascii_to_bn_digits(str(p.page))}",
            text=p.text,
            page=p.page,
        )
        for i, p in enumerate(passages, start=1)
    }


def build_user_message(question: str, labelled: dict) -> str:  # noqa: ANN001 - ChunkRecord | UserPassageSource
    official, personal = [], []
    for label, chunk in labelled.items():
        if getattr(chunk, "kind", "official") == "user":
            personal.append(f"[{label}] {chunk.citation}\n{chunk.text}")
        else:
            part = f" (অংশ {chunk.part})" if chunk.part else ""
            official.append(f"[{label}] {chunk.citation}{part} — {chunk.title}\n{chunk.text}")
    message = (
        f"প্রশ্ন: {question}\n\n<sources>\n" + ("\n\n".join(official) or "(কোনো সরকারি সূত্র পাওয়া যায়নি)") + "\n</sources>"
    )
    if personal:
        message += "\n\n<user_document>\n" + "\n\n".join(personal) + "\n</user_document>"
    return message


async def generate_answer(llm: LLMClient, question: str, labelled: dict) -> LLMResult[AnswerOutput]:  # noqa: ANN001
    has_user_doc = any(getattr(c, "kind", "official") == "user" for c in labelled.values())
    system = load_prompt("answer_bn") + ("\n\n" + load_prompt("answer_user_doc") if has_user_doc else "")
    return await llm.complete_json(
        system,
        build_user_message(question, labelled),
        AnswerOutput,
        temperature=0.1,
        max_tokens=1200,
        purpose="answer",
    )
