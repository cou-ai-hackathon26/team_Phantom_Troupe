"""Section-aware chunking.

- A section that fits in MAX_TOKENS (heading included) stays one chunk.
- Longer sections are packed from whole clause units (one per line; the parser starts a new line at
  each "(১)", "(ক)" …), so a numbered sub-clause is never split when avoidable.
- A single clause longer than the budget is split on sentence ends ("।", "?", ";").
- Consecutive parts overlap by ~OVERLAP_TOKENS of trailing units. Every part keeps the parent
  citation and gets a part number.

Tokens are counted with the embedding model's tokenizer (e5 truncates at 512), injectable for tests.
"""

import re
from collections.abc import Callable
from functools import lru_cache

from app.ingestion.text_normalizer import normalize_for_search
from app.schemas.ingestion import ChunkRecord, SectionRecord

MAX_TOKENS = 450
OVERLAP_TOKENS = 60

TokenCounter = Callable[[str], int]

_SENTENCE_END = re.compile(r"(?<=[।?;])\s+")


@lru_cache
def model_token_counter(model_name: str) -> TokenCounter:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name)

    def count(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False))

    return count


def whitespace_token_counter(text: str) -> int:
    return len(text.split())


def _split_long_unit(unit: str, budget: int, count: TokenCounter) -> list[str]:
    sentences = [s for s in _SENTENCE_END.split(unit) if s.strip()]
    pieces: list[str] = []
    buf = ""
    for sentence in sentences:
        candidate = f"{buf} {sentence}".strip()
        if buf and count(candidate) > budget:
            pieces.append(buf)
            buf = sentence
        else:
            buf = candidate
    if buf:
        pieces.append(buf)
    # a single sentence can still exceed the budget: hard-split on words as a last resort
    out: list[str] = []
    for piece in pieces:
        if count(piece) <= budget:
            out.append(piece)
            continue
        words, cur = piece.split(), []
        for word in words:
            if cur and count(" ".join([*cur, word])) > budget:
                out.append(" ".join(cur))
                cur = []
            cur.append(word)
        if cur:
            out.append(" ".join(cur))
    return out


def split_text(
    text: str,
    heading: str,
    count: TokenCounter,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    budget = max(50, max_tokens - count(heading) - 2)
    if count(text) <= budget:
        return [text]

    units: list[str] = []
    for line in (ln.strip() for ln in text.split("\n")):
        if not line:
            continue
        units.extend(_split_long_unit(line, budget, count) if count(line) > budget else [line])

    parts: list[list[str]] = []
    current: list[str] = []
    for unit in units:
        if current and count("\n".join([*current, unit])) > budget:
            parts.append(current)
            # overlap: carry trailing units that fit in overlap_tokens (and leave room for `unit`)
            carry: list[str] = []
            for prev in reversed(current):
                trial = [prev, *carry]
                if count("\n".join(trial)) > overlap_tokens or count("\n".join([*trial, unit])) > budget:
                    break
                carry = trial
            current = carry
        current.append(unit)
    if current:
        parts.append(current)
    return ["\n".join(p) for p in parts]


def chunk_section(
    record: SectionRecord,
    count: TokenCounter,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[ChunkRecord]:
    heading = f"{record.citation} — {record.title}"
    texts = split_text(record.text, heading, count, max_tokens, overlap_tokens)
    split = len(texts) > 1
    chunks: list[ChunkRecord] = []
    for i, text in enumerate(texts, start=1):
        chunk = ChunkRecord(
            id=f"{record.id}-p{i}" if split else record.id,
            document_id=record.document_id,
            area=record.area,
            act=record.act,
            chapter=record.chapter,
            section=record.section,
            title=record.title,
            citation=record.citation,
            part=i if split else None,
            text=text,
            normalized_text="",
            token_count=0,
            notes=record.notes,
            source_url=record.source_url,
            page_start=record.page_start,
            page_end=record.page_end,
        )
        chunk.normalized_text = normalize_for_search(chunk.embedding_text())
        chunk.token_count = count(chunk.embedding_text())
        chunks.append(chunk)
    return chunks
