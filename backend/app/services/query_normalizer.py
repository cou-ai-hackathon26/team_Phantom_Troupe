"""Call 1: rewrite dialect / Banglish / English into standard Bangla and classify the area."""

import logging
from dataclasses import dataclass

from app.ingestion.text_normalizer import normalize_text
from app.models.llm_client import LLMBadOutput, LLMClient
from app.prompts import load_prompt
from app.schemas.llm import NormalizeOutput

logger = logging.getLogger(__name__)


@dataclass
class NormalizedQuery:
    original: str
    standard_bangla: str
    area: str | None  # None = search all areas
    in_scope: bool
    needs_clarification: bool
    clarification_question: str | None
    llm_ok: bool  # False when Call 1 output was unusable and we fell back to the raw question


async def normalize_query(llm: LLMClient, message: str) -> NormalizedQuery:
    """LLM errors other than bad output (rate limit, outage) propagate to the caller."""
    message = normalize_text(message)
    try:
        result = await llm.complete_json(
            load_prompt("normalize"), message, NormalizeOutput, temperature=0.0, max_tokens=400, purpose="normalize"
        )
    except LLMBadOutput as exc:
        # Fallback (never block on Call 1): search all areas with the raw question; Call 2 + validation still guard.
        logger.warning("normalize fallback", extra={"data": {"error": str(exc)}})
        return NormalizedQuery(message, message, None, True, False, None, llm_ok=False)
    out = result.data
    clarify = out.needs_clarification and bool(out.clarification_question)
    return NormalizedQuery(
        original=message,
        standard_bangla=normalize_text(out.standard_bangla) or message,
        area=None if out.area == "unknown" else out.area,
        in_scope=out.in_scope,
        needs_clarification=clarify,
        clarification_question=out.clarification_question if clarify else None,
        llm_ok=True,
    )
