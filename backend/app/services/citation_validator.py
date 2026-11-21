"""Validate Call 2 output in code: chunk ids, citation markers and numbers.

- found=false, or no valid used chunk  -> refused
- labels/ids not among the retrieved chunks are dropped
- every number in the answer must appear in a used chunk, otherwise status "partial" + warning
- "[C2]" markers are rewritten to "[১]" … in order of first use; citations are built from stored metadata
"""

import re
from dataclasses import dataclass, field

from app.ingestion.text_normalizer import ascii_to_bn_digits, bn_to_ascii_digits, normalize_for_search
from app.schemas.chat import Citation
from app.schemas.ingestion import ChunkRecord
from app.schemas.llm import AnswerOutput

_MARKER_GROUP = re.compile(r"\[\s*(C\d+(?:\s*[,，、]\s*C\d+)*)\s*\]", re.IGNORECASE)
_LIST_NUMBER = re.compile(r"(?m)^\s*[0-9০-৯]{1,2}\s*[.।)]\s+")
_NUMBER = re.compile(r"[0-9০-৯]+(?:[.,][0-9০-৯]+)*")
_BARE_MARKER = re.compile(r"\[\s*[0-9০-৯]{1,2}\s*\]")  # "[৫]" written by the model itself: not ours, drop
_REPEATED_MARKER = re.compile(r"(\[[০-৯]+\])(?:\s*\1)+")
EXCERPT_CHARS = 320

# Number words common in Bangladeshi legal text ("আট কিলোমিটার", "তিন মাস"). Evidence side only: a
# correct digit in the answer ("৮") then matches a number written in words in the source.
BN_NUMBER_WORDS = {
    "এক": 1, "দুই": 2, "তিন": 3, "চার": 4, "পাঁচ": 5, "ছয়": 6, "সাত": 7, "আট": 8, "নয়": 9, "দশ": 10,
    "এগার": 11, "এগারো": 11, "বার": 12, "বারো": 12, "তের": 13, "তেরো": 13, "চৌদ্দ": 14, "পনের": 15, "পনেরো": 15,
    "ষোল": 16, "সতের": 17, "আঠার": 18, "আঠারো": 18, "উনিশ": 19, "বিশ": 20, "কুড়ি": 20, "পঁচিশ": 25,
    "ত্রিশ": 30, "চল্লিশ": 40, "পঁয়তাল্লিশ": 45, "পঞ্চাশ": 50, "ষাট": 60, "সত্তর": 70, "আশি": 80, "নব্বই": 90,
    "একশ": 100, "একশত": 100,
}  # fmt: skip
_WORD = re.compile(r"[\u0980-\u09ff]+")

NUMERIC_WARNING = "উত্তরের কিছু সংখ্যা ({numbers}) সূত্রে হুবহু পাওয়া যায়নি — মূল সূত্র দেখে নিশ্চিত হোন।"


@dataclass
class Validation:
    status: str  # answered | partial | refused
    answer: str
    citations: list[Citation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    used_chunk_ids: list[str] = field(default_factory=list)
    dropped_ids: list[str] = field(default_factory=list)
    reason: str = ""


def _resolve(raw_id: str, labelled: dict[str, ChunkRecord]) -> str | None:
    key = raw_id.strip().strip("[]").upper()
    if key in labelled:
        return key
    for label, chunk in labelled.items():  # model returned a real chunk id instead of a label
        if chunk.id == raw_id.strip():
            return label
    return None


def numbers_in(text: str) -> set[str]:
    """Digit sequences in text, ASCII-normalized, ignoring "১." style list numbering and thousands commas."""
    text = _LIST_NUMBER.sub(" ", text)
    out: set[str] = set()
    for m in _NUMBER.finditer(text):
        n = bn_to_ascii_digits(m.group(0)).replace(",", "").rstrip(".")
        out.add(n.lstrip("0") or "0")  # compare by value: the source writes "০৬", answers write "৬"
    return out


def number_words_in(text: str) -> set[str]:
    """Values of Bangla number words, so "আট" in the source supports "৮" in the answer."""
    import unicodedata

    words = {unicodedata.normalize("NFC", k): v for k, v in BN_NUMBER_WORDS.items()}
    return {str(words[w]) for w in _WORD.findall(unicodedata.normalize("NFC", text)) if w in words}


def _excerpt(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= EXCERPT_CHARS else flat[:EXCERPT_CHARS].rsplit(" ", 1)[0] + " …"


def validate_answer(output: AnswerOutput, labelled: dict[str, ChunkRecord]) -> Validation:
    if not output.found or not output.answer.strip():
        return Validation("refused", "", reason="not_found")

    used_labels: list[str] = []
    dropped: list[str] = []
    for raw in output.used_chunk_ids:
        label = _resolve(raw, labelled)
        if label is None:
            dropped.append(raw)
        elif label not in used_labels:
            used_labels.append(label)

    # labels cited inline but missing from used_chunk_ids still count (if valid)
    inline_order: list[str] = []
    for group in _MARKER_GROUP.finditer(output.answer):
        for raw in re.split(r"\s*[,，、]\s*", group.group(1)):
            label = _resolve(raw, labelled)
            if label is not None and label not in inline_order:
                inline_order.append(label)
    for label in inline_order:
        if label not in used_labels:
            used_labels.append(label)

    if not used_labels:
        return Validation("refused", "", dropped_ids=dropped, reason="no_valid_citation")

    # marker numbers follow first appearance in the text, then any remaining used labels
    order = inline_order + [label for label in used_labels if label not in inline_order]
    marker_of = {label: i for i, label in enumerate(order, start=1)}

    def replace(group: re.Match[str]) -> str:
        labels = [_resolve(r, labelled) for r in re.split(r"\s*[,，、]\s*", group.group(1))]
        return "".join(f"[{ascii_to_bn_digits(str(marker_of[lb]))}]" for lb in labels if lb in marker_of)

    answer = _MARKER_GROUP.sub(replace, _BARE_MARKER.sub("", output.answer))
    answer = _REPEATED_MARKER.sub(r"\1", answer).strip()
    answer = re.sub(r"[ \t]+\n", "\n", answer)

    warnings: list[str] = []
    status = "answered"
    evidence = " ".join(normalize_for_search(labelled[lb].embedding_text()) for lb in order)
    evidence_numbers = numbers_in(evidence) | number_words_in(evidence)
    plain = _BARE_MARKER.sub(" ", _MARKER_GROUP.sub(" ", output.answer))
    unsupported = sorted(n for n in numbers_in(plain) if n not in evidence_numbers)
    # the rewritten "[১]" markers are not numbers in the answer
    unsupported = [n for n in unsupported if n]
    if unsupported:
        status = "partial"
        warnings.append(NUMERIC_WARNING.format(numbers=", ".join(ascii_to_bn_digits(n) for n in unsupported)))

    citations = [
        Citation(
            marker=marker_of[label],
            chunk_id=labelled[label].id,
            act=labelled[label].act,
            section=labelled[label].section,
            title=labelled[label].title,
            citation=labelled[label].citation,
            excerpt=_excerpt(labelled[label].text),
            source_url=labelled[label].source_url,
            notes=labelled[label].notes,
        )
        for label in order
    ]
    return Validation(
        status=status,
        answer=answer,
        citations=citations,
        warnings=warnings,
        used_chunk_ids=[labelled[lb].id for lb in order],
        dropped_ids=dropped,
        reason="validated",
    )
