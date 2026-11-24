"""Call 1: rewrite dialect / Banglish / English into standard Bangla and classify the area."""

import logging
from dataclasses import dataclass, field

from app.ingestion.text_normalizer import normalize_text
from app.models.llm_client import LLMBadOutput, LLMClient
from app.prompts import load_prompt
from app.schemas.llm import NormalizeOutput
from app.services.dialect_hints import with_hints

logger = logging.getLogger(__name__)


@dataclass
class NormalizedQuery:
    original: str
    standard_bangla: str
    search_query: str  # what retrieval searches (eligibility/conditions wording, official terms)
    area: str | None  # None = search all areas
    in_scope: bool
    needs_clarification: bool
    clarification_question: str | None
    llm_ok: bool  # False when Call 1 output was unusable and we fell back to the raw question
    extra_queries: list[str] = field(default_factory=list)  # other problems in a multi-issue question
    followup_intent: str | None = None  # follow-up mode only: CONTINUE | EXPAND | NEW_TOPIC | CLARIFY
    referenced_turns: list[str] = field(default_factory=list)  # history labels ("T1"), validated by the caller


MAX_EXTRA_QUERIES = 2


FOLLOWUP_MESSAGE_HEADER = "নতুন বার্তা (এটিকেই rewrite ও classify করতে হবে):"


async def normalize_query(llm: LLMClient, message: str, history: str | None = None) -> NormalizedQuery:
    """LLM errors other than bad output (rate limit, outage) propagate to the caller.

    `history` (follow-up mode) is a <conversation_history> block placed before the message; it adds the
    follow-up instructions to the prompt and the followup_intent / referenced_turns keys to the output."""
    message = normalize_text(message)
    system = load_prompt("normalize")
    user = with_hints(message)
    if history:
        system += "\n\n" + load_prompt("followup_normalize")
        user = f"{history}\n\n{FOLLOWUP_MESSAGE_HEADER}\n{user}"
    try:
        result = await llm.complete_json(
            system,
            user,
            NormalizeOutput,
            temperature=0.0,
            max_tokens=800 if history else 700,
            purpose="normalize",
        )
    except LLMBadOutput as exc:
        # Fallback (never block on Call 1): search all areas with the raw question; Call 2 + validation still guard.
        logger.warning("normalize fallback", extra={"data": {"error": str(exc)}})
        return NormalizedQuery(message, message, message, None, True, False, None, llm_ok=False)
    out = result.data
    clarify = out.needs_clarification and bool(out.clarification_question)
    standard = normalize_text(out.standard_bangla) or message
    search = normalize_text(out.search_query) or standard
    extras: list[str] = []
    for q in out.extra_queries:
        q = normalize_text(q)
        if q and q != search and q not in extras:
            extras.append(q)
    return NormalizedQuery(
        original=message,
        standard_bangla=standard,
        search_query=search,
        area=None if out.area == "unknown" else out.area,
        in_scope=out.in_scope,
        needs_clarification=clarify,
        clarification_question=out.clarification_question if clarify else None,
        llm_ok=True,
        extra_queries=extras[:MAX_EXTRA_QUERIES],
        followup_intent=out.followup_intent if history else None,
        referenced_turns=list(out.referenced_turns) if history else [],
    )
