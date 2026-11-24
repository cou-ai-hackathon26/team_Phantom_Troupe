"""Conflict detection around Call 2: the brief it receives, the judgements it returns, and the final guarantee.

prepare()  (before Call 2): profiles + claims + rule-based pairs → a <conflict_check> brief
           (prompts/conflict_answer.md).
finalize() (after validation):
  1. Call 2's `conflict_judgments` may change an unresolved pair only with evidence: same_context=true turns
     POSSIBLE into DIRECT (more disclosure, never less); same_context=false turns a pair into a context
     difference only with a `difference_quote` found word-for-word in one of the two passages.
  2. Call 2's `document_claims` (required papers) are kept only if their quote is in the passage; they are
     compared by the same rules.
  3. Disclosure guard: if the answer states a value from an unresolved disagreement, it must state both values
     and cite both passages; otherwise a fixed notice with both values (verbatim from the sources) and both
     citations is appended. If it states a repealed/amended value without the controlling one, a notice gives
     the controlling value. So a model that ignores the instructions still cannot present one side as certain.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ValidationError

from app.ingestion.text_normalizer import ascii_to_bn_digits, normalize_for_search
from app.schemas.chat import Citation
from app.schemas.conflict import Claim, ConflictAnalysis, ConflictItem, ConflictSource, Requirement
from app.schemas.llm import AnswerOutput
from app.services.citation_validator import citation_for, numbers_in
from app.services.claim_extractor import context_cues, extract_claims
from app.services.conflict_detector import ConflictPair, detect, question_focus, resolve
from app.services.retrieval_service import programmes_named
from app.services.source_profile import SourceProfile, profile_for, web_profile

logger = logging.getLogger(__name__)

TOPICS = {
    "application_fee": "ফি",
    "allowance_amount": "ভাতা বা সহায়তার পরিমাণ",
    "tax": "কর",
    "fine": "জরিমানা",
    "income_limit": "আয়সীমা",
    "age_limit": "বয়সসীমা",
    "deadline": "সময়সীমা",
    "validity": "মেয়াদ",
    "document": "প্রয়োজনীয় কাগজ",
}
REQUIREMENT_TEXT = {
    "required": "প্রয়োজন",
    "optional": "ঐচ্ছিক",
    "conditional": "শর্তসাপেক্ষে প্রয়োজন",
    "not_required": "প্রয়োজন নেই",
}
CONFIRM = "আবেদনের আগে সংশ্লিষ্ট অফিস থেকে নিশ্চিত হোন।"
NOTICE_UNRESOLVED = (
    "সতর্কতা — সরকারি নথিগুলোতে {topic} নিয়ে ভিন্ন তথ্য আছে: {sides}। কোনটি এখন প্রযোজ্য, তা নথি থেকে নিশ্চিত করা যায়নি; " + CONFIRM
)
NOTICE_POSSIBLE = (
    "সতর্কতা — {topic} নিয়ে নথিগুলোতে ভিন্ন তথ্য পাওয়া গেছে, যা একই ক্ষেত্রে প্রযোজ্য কি না নথি থেকে নিশ্চিত নয়: {sides}। " + CONFIRM
)
NOTICE_RESOLVED = "দ্রষ্টব্য — {topic} নিয়ে {old} পাওয়া গেছে, কিন্তু {why}; প্রযোজ্য তথ্য: {new}।"
WHY = {
    "RESOLVED_BY_SOURCE_STATUS": "সেটি একটি রহিত আইনের",
    "RESOLVED_BY_EXPLICIT_SUPERSESSION": "পরের সংশোধনী আইন সেটি সংশোধন করেছে",
}
CONFLICT_WARNING = "সরকারি নথিগুলোতে ভিন্ন তথ্য পাওয়া গেছে; উত্তরের শেষে দুই পক্ষের তথ্য ও সূত্র দেখানো হয়েছে।"
MAX_DOCUMENT_CLAIMS = 20


class ConflictJudgment(BaseModel):
    id: str
    same_context: bool | None = None
    difference_quote: str | None = None


class DocumentClaimIn(BaseModel):
    label: str
    document: str = Field(min_length=2, max_length=80)
    requirement: Requirement
    quote: str = Field(min_length=4, max_length=400)


@dataclass
class ConflictRun:
    labelled: Mapping[str, object]
    profiles: dict[str, SourceProfile]
    claims: list[Claim]
    pairs: list[ConflictPair]
    focus: set[str]
    programmes: Mapping[str, str] = field(default_factory=dict)

    @property
    def wants_documents(self) -> bool:
        return "document" in self.focus

    @property
    def brief(self) -> str | None:
        return conflict_brief(self) if (self.pairs or self.wants_documents) else None


def _profile(label: str, chunk: object) -> SourceProfile:
    if getattr(chunk, "kind", "official") == "web":
        return web_profile(getattr(chunk, "id", label), getattr(chunk, "title", ""))
    return profile_for(getattr(chunk, "document_id", label), getattr(chunk, "act", ""))


def prepare(labelled: Mapping[str, object], question: str, programmes: Mapping[str, str] | None = None) -> ConflictRun:
    official = {lb: c for lb, c in labelled.items() if getattr(c, "kind", "official") != "user"}
    profiles = {lb: _profile(lb, c) for lb, c in official.items()}
    claims = extract_claims(official, programmes)
    focus = question_focus(question)
    pairs = detect(claims, profiles, focus)
    return ConflictRun(official, profiles, claims, pairs, focus, programmes or {})


def _year(profile: SourceProfile) -> str:
    return f", শিরোনামে সাল {ascii_to_bn_digits(str(profile.title_year))}" if profile.title_year else ""


def conflict_brief(run: ConflictRun) -> str:
    lines = ["<conflict_check>"]
    for pair in run.pairs:
        verdict = pair.resolution or "-"
        if pair.controlling is not None and pair.superseded is not None:
            verdict += f" (প্রযোজ্য: [{pair.controlling.label}], বাদ: [{pair.superseded.label}])"
        lines.append(
            f"[{pair.id}] বিষয়: {TOPICS.get(pair.a.category, pair.a.category)} | অবস্থা: {pair.status}"
            f" | সিদ্ধান্ত: {verdict}"
        )
        for claim in (pair.a, pair.b):
            profile = run.profiles[claim.label]
            lines.append(
                f'  [{claim.label}] «{claim.original_text}» — "{claim.quote}" ({profile.type_label}{_year(profile)})'
            )
    if run.wants_documents:
        lines.append("DOCUMENT_CLAIMS_REQUESTED")
    lines.append("</conflict_check>")
    return "\n".join(lines)


def _in_passage(quote: str, chunk: object) -> bool:
    q = normalize_for_search(quote).strip(" .…\"'")
    return len(q) >= 4 and q in normalize_for_search(getattr(chunk, "text", ""))


def apply_judgments(run: ConflictRun, judgments: list[dict]) -> None:
    by_id = {p.id: p for p in run.pairs}
    for raw in judgments[: len(by_id) + 2]:
        try:
            j = ConflictJudgment.model_validate(raw)
        except ValidationError:
            continue
        pair = by_id.get(j.id.strip().strip("[]").upper())
        if pair is None or not pair.unresolved:
            continue
        if j.same_context is True and pair.status == "POSSIBLE_CONFLICT":
            pair.status, pair.judged_by = "DIRECT_CONFLICT", "rules+llm"
            pair.reasons.append("llm_same_context")
            resolve(pair, run.profiles[pair.a.label], run.profiles[pair.b.label])
        elif (
            j.same_context is False
            and j.difference_quote
            and any(_in_passage(j.difference_quote, run.labelled[c.label]) for c in (pair.a, pair.b))
        ):
            pair.status, pair.resolution, pair.judged_by = (
                "CONTEXT_DIFFERENCE",
                "RESOLVED_BY_APPLICABILITY",
                "rules+llm",
            )
            pair.controlling = None
            pair.reasons.append("llm_context_difference_quote_verified")


def document_claims(run: ConflictRun, items: list[dict]) -> list[Claim]:
    claims: list[Claim] = []
    for n, raw in enumerate(items[:MAX_DOCUMENT_CLAIMS]):
        try:
            item = DocumentClaimIn.model_validate(raw)
        except ValidationError:
            continue
        label = item.label.strip().strip("[]").upper()
        chunk = run.labelled.get(label)
        if chunk is None or not _in_passage(item.quote, chunk):
            continue  # unsupported: the quote is not in that passage
        document_id = getattr(chunk, "document_id", None) or getattr(chunk, "id", label)
        context = context_cues(item.quote)
        programme = programmes_named(item.quote) or (
            {run.programmes[document_id]} if document_id in run.programmes else set()
        )
        if programme:
            context["programme"] = sorted(programme)
        claims.append(
            Claim(
                id=f"{label}:doc{n}",
                kind="required_document",
                category="document",
                requirement=item.requirement,
                document_name=item.document.strip(),
                original_text=f"{item.document.strip()}: {REQUIREMENT_TEXT[item.requirement]}",
                quote=" ".join(item.quote.split()),
                label=label,
                chunk_id=getattr(chunk, "id", label),
                document_id=document_id,
                section=getattr(chunk, "section", None),
                context=context,
                method="llm_quote_verified",
            )
        )
    return claims


def _num(value: float | None) -> str:
    if value is None:
        return ""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _mentioned(claim: Claim, answer: str, answer_numbers: set[str]) -> bool:
    if claim.kind == "required_document":
        key = normalize_for_search(claim.document_name or "")
        return bool(key) and key in normalize_for_search(answer)
    return _num(claim.value) in answer_numbers


@dataclass
class Disclosure:
    answer: str
    citations: list[Citation]
    warnings: list[str]
    analysis: ConflictAnalysis


def _marker(citations: list[Citation], run: ConflictRun, claim: Claim) -> int:
    for c in citations:
        if c.chunk_id == claim.chunk_id:
            return c.marker
    marker = max((c.marker for c in citations), default=0) + 1
    citations.append(citation_for(run.labelled[claim.label], marker))  # type: ignore[arg-type]
    return marker


def _side(run: ConflictRun, claim: Claim, marker: int) -> str:
    profile = run.profiles[claim.label]
    title = profile.title if len(profile.title) <= 60 else profile.title[:57] + "…"
    return f"{profile.type_label} «{title}»{_year(profile)}: {claim.original_text} [{ascii_to_bn_digits(str(marker))}]"


def _cited(citations: list[Citation], claim: Claim) -> bool:
    return any(c.chunk_id == claim.chunk_id for c in citations)


def guard(run: ConflictRun, answer: str, citations: list[Citation]) -> tuple[str, list[str]]:
    notices: list[str] = []
    numbers = numbers_in(answer)
    for pair in run.pairs:
        topic = TOPICS.get(pair.a.category, pair.a.category)
        ma, mb = _mentioned(pair.a, answer, numbers), _mentioned(pair.b, answer, numbers)
        if pair.unresolved:
            if not (ma or mb):
                continue
            pair.disclosed = True
            if ma and mb and _cited(citations, pair.a) and _cited(citations, pair.b):
                continue  # the model disclosed both sides itself
            sides = "; ".join(_side(run, c, _marker(citations, run, c)) for c in (pair.a, pair.b))
            template = NOTICE_UNRESOLVED if pair.status == "DIRECT_CONFLICT" else NOTICE_POSSIBLE
            notices.append(template.format(topic=topic, sides=sides))
        elif pair.controlling is not None and pair.superseded is not None and pair.resolution in WHY:
            old, new = pair.superseded, pair.controlling
            if not (ma or mb):
                continue
            pair.disclosed = True
            if _mentioned(old, answer, numbers) and not _mentioned(new, answer, numbers):
                notices.append(
                    NOTICE_RESOLVED.format(
                        topic=topic,
                        old=_side(run, old, _marker(citations, run, old)),
                        why=WHY[pair.resolution],
                        new=_side(run, new, _marker(citations, run, new)),
                    )
                )
    if not notices:
        return answer, []
    return answer.rstrip() + "\n\n" + "\n".join(notices), [CONFLICT_WARNING]


def _public(run: ConflictRun, citations: list[Citation]) -> ConflictAnalysis:
    markers = {c.chunk_id: c.marker for c in citations}
    items: list[ConflictItem] = []
    for pair in run.pairs:
        sources = []
        for claim in (pair.a, pair.b):
            profile = run.profiles[claim.label]
            sources.append(
                ConflictSource(
                    value=claim.original_text,
                    marker=markers.get(claim.chunk_id),
                    chunk_id=claim.chunk_id,
                    document_id=claim.document_id,
                    title=profile.title,
                    source_type=profile.source_type,
                    source_type_label=profile.type_label,
                    title_year=profile.title_year,
                    status=profile.status,
                    quote=claim.quote,
                )
            )
        items.append(
            ConflictItem(
                id=pair.id,
                claim_type=pair.a.kind,
                category=pair.a.category,
                topic=TOPICS.get(pair.a.category, pair.a.category),
                status=pair.status,
                resolution=pair.resolution,
                reason=",".join(dict.fromkeys(pair.reasons)),
                controlling_chunk_id=pair.controlling.chunk_id if pair.controlling else None,
                judged_by=pair.judged_by,  # type: ignore[arg-type]
                disclosed=pair.disclosed,
                sources=sources,
            )
        )
    shown = [i for i in items if i.disclosed]
    if any(i.resolution in ("UNRESOLVED_OFFICIAL_DISAGREEMENT", "UNRESOLVED_INSUFFICIENT_METADATA") for i in shown):
        status = "unresolved"
    elif any(i.status == "RESOLVED" for i in shown):
        status = "resolved"
    else:
        status = "none"
    return ConflictAnalysis(status=status, claims_checked=len(run.claims), items=items)  # type: ignore[arg-type]


def finalize(run: ConflictRun, output: AnswerOutput, answer: str, citations: list[Citation]) -> Disclosure:
    apply_judgments(run, output.conflict_judgments)
    if run.wants_documents and output.document_claims:
        doc_claims = document_claims(run, output.document_claims)
        run.claims.extend(doc_claims)
        run.pairs.extend(detect(doc_claims, run.profiles, run.focus, start=len(run.pairs) + 1))
    citations = list(citations)
    answer, warnings = guard(run, answer, citations)
    return Disclosure(answer, citations, warnings, _public(run, citations))


def failed_analysis() -> ConflictAnalysis:
    return ConflictAnalysis(status="insufficient_evidence")
