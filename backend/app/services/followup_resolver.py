"""Follow-up resolution, folded into Call 1 (the 2-LLM-call limit allows no separate resolver call).

With conversation history, Call 1 also receives the last few exchanges (labelled [T1], [T2] …) and returns
`followup_intent` + `referenced_turns` next to its usual rewrite. This module builds those history blocks and
validates the output in code: only labels that were shown map to turn ids, an intent that cannot be acted on
safely falls back to fresh retrieval, and a CLARIFY without a question becomes fresh retrieval too.

History is context, never evidence: Call 1 sees earlier *questions* and the *titles* of cited sources (no
answer prose); Call 2 sees the referenced exchanges with a short answer excerpt, marked as non-authoritative.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from app.schemas.conversation import FollowupResolution
from app.services.conversation_store import Conversation, SourceRef
from app.services.query_normalizer import NormalizedQuery

ANSWER_EXCERPT_CHARS = 300
SOURCES_SHOWN_PER_TURN = 3
_MARKER = re.compile(r"\[[০-৯0-9]+\]")


@dataclass(frozen=True)
class PriorExchange:
    """One earlier question/answer pair of the conversation."""

    turn_id: str  # the assistant turn
    question: str  # the standalone question that turn answered (Call 1's rewrite), else the user's words
    answer: str  # "" for personal-document answers (never shown again)
    area: str | None
    status: str
    sources: tuple[SourceRef, ...]


@dataclass(frozen=True)
class TurnContext:
    """What one request knows about its conversation: the last few exchanges, oldest first."""

    exchanges: tuple[PriorExchange, ...] = ()

    @property
    def has_history(self) -> bool:
        return bool(self.exchanges)

    @property
    def labels(self) -> dict[str, str]:
        """History label ("T1") -> assistant turn id."""
        return {f"T{i}": ex.turn_id for i, ex in enumerate(self.exchanges, start=1)}

    def by_turn_id(self, turn_ids: Sequence[str]) -> list[PriorExchange]:
        wanted = set(turn_ids)
        return [ex for ex in self.exchanges if ex.turn_id in wanted]

    @classmethod
    def from_conversation(cls, conversation: Conversation, max_exchanges: int) -> "TurnContext":
        exchanges: list[PriorExchange] = []
        turns = conversation.turns
        for user, assistant in zip(turns[::2], turns[1::2], strict=False):
            if user.role != "user" or assistant.role != "assistant":
                continue  # turns are appended in pairs; anything else is ignored rather than misread
            exchanges.append(
                PriorExchange(
                    turn_id=assistant.id,
                    question=assistant.normalized or user.content,
                    answer="" if assistant.private else assistant.content,
                    area=assistant.area,
                    status=assistant.status or "",
                    sources=tuple(assistant.sources),
                )
            )
        return cls(tuple(exchanges[-max_exchanges:]) if max_exchanges > 0 else ())


def _one_line(text: str) -> str:
    return " ".join(text.split())


def normalize_history_block(context: TurnContext) -> str:
    """History for Call 1: earlier questions, their area/status and cited source titles. No answer prose."""
    lines = ["<conversation_history>"]
    for label, ex in zip(context.labels, context.exchanges, strict=True):
        lines.append(f"[{label}] প্রশ্ন: {_one_line(ex.question)}")
        lines.append(f"     বিষয়: {ex.area or 'unknown'} | উত্তরের অবস্থা: {ex.status or '-'}")
        cited = [s.citation for s in ex.sources if s.kind == "official"][:SOURCES_SHOWN_PER_TURN]
        if cited:
            lines.append("     উদ্ধৃত সূত্র: " + "; ".join(_one_line(c) for c in cited))
    lines.append("</conversation_history>")
    return "\n".join(lines)


def answer_history_block(exchanges: Sequence[PriorExchange]) -> str:
    """History for Call 2: the referenced exchanges, with a short excerpt of each earlier answer."""
    parts = ["<conversation_history>"]
    for ex in exchanges:
        parts.append(f"আগের প্রশ্ন: {_one_line(ex.question)}")
        answer = _one_line(_MARKER.sub("", ex.answer))
        if answer:
            cut = answer if len(answer) <= ANSWER_EXCERPT_CHARS else answer[:ANSWER_EXCERPT_CHARS].rsplit(" ", 1)[0]
            parts.append(f"আগের উত্তরের অংশ (প্রমাণ নয়): {cut}{'' if cut == answer else ' …'}")
    parts.append("</conversation_history>")
    return "\n".join(parts)


def resolve_followup(query: NormalizedQuery, context: TurnContext) -> FollowupResolution:
    """Turns Call 1's follow-up fields into a validated resolution (never raises)."""
    if not context.has_history:
        return FollowupResolution(
            is_follow_up=False, intent="NEW_TOPIC", resolved_query=query.standard_bangla, area=query.area
        )
    labels = context.labels
    referenced = [labels[t] for t in dict.fromkeys(query.referenced_turns) if t in labels]
    intent = query.followup_intent if query.llm_ok else None

    if intent == "CLARIFY":
        question = query.clarification_question
        if question:
            return FollowupResolution(
                is_follow_up=True,
                intent="CLARIFY",
                resolved_query=query.standard_bangla,
                area=query.area,
                referenced_turn_ids=referenced,
                needs_new_retrieval=False,
                clarification_question=question,
            )
        intent = None  # nothing to ask: search afresh instead of guessing

    if intent in ("CONTINUE", "EXPAND"):
        if not referenced:
            referenced = [context.exchanges[-1].turn_id]  # "তাহলে …" with no label: the latest exchange
        return FollowupResolution(
            is_follow_up=True,
            intent=intent,
            resolved_query=query.standard_bangla,
            area=query.area,
            referenced_turn_ids=referenced,
            reuse_previous_sources=True,
        )

    # NEW_TOPIC, a missing/unknown intent, or Call 1 fell back to the raw message: fresh retrieval only
    return FollowupResolution(
        is_follow_up=intent == "NEW_TOPIC", intent="NEW_TOPIC", resolved_query=query.standard_bangla, area=query.area
    )


def apply_resolution(query: NormalizedQuery, resolution: FollowupResolution) -> NormalizedQuery:
    """The pre-retrieval gate reads needs_clarification, so a follow-up CLARIFY stops there. Call 1's own
    clarification flag (question too vague to search) is kept for every other intent: asking beats guessing."""
    if resolution.intent == "CLARIFY":
        return replace(query, needs_clarification=True, clarification_question=resolution.clarification_question)
    return query
