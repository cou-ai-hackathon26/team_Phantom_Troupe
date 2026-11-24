"""Compare claims from different documents and decide, by rules only, whether and how they conflict.

1. Comparable? Same claim category, different documents, both claims legible, not about different allowance
   programmes, and either the same programme is named or the question asks about that category.
2. Classify: equal values → NO_CONFLICT; explicitly different periods → TEMPORAL_DIFFERENCE; a context that
   differs in both (applicant, variant, place, programme, min/max) → CONTEXT_DIFFERENCE; a context stated in
   only one source, conditions, or units that are not equivalent (working vs calendar days) →
   POSSIBLE_CONFLICT; otherwise DIRECT_CONFLICT.
3. Resolve only with evidence the repository has: one side from a repealed act (RESOLVED_BY_SOURCE_STATUS);
   for a direct conflict, an amendment act that names the other act and is later
   (RESOLVED_BY_EXPLICIT_SUPERSESSION); a context difference (RESOLVED_BY_APPLICABILITY). A later title year,
   a higher retrieval score or source type alone never decide; everything else stays unresolved.
"""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.ingestion.text_normalizer import normalize_for_search
from app.schemas.conflict import Claim, ConflictStatus, Resolution
from app.services.source_profile import SourceProfile, amends


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(unicodedata.normalize("NFC", pattern), re.IGNORECASE)


# what the question asks about; categories outside it are compared only when the same programme is named
FOCUS: dict[str, re.Pattern[str]] = {
    "application_fee": _p(r"ফি|ফিস|খরচ|মাশুল|চার্জ|কত টাকা লাগ|টাকা লাগ|\bfees?\b|\bcost\b|\bcharges?\b"),
    "allowance_amount": _p(r"ভাতা.*(?:কত|পরিমাণ|পরিমান|হার)|(?:কত|পরিমাণ|হার).*ভাতা|কত টাকা পা|\bhow much\b"),
    "tax": _p(r"উন্নয়ন কর|খাজনা|করের হার|কত কর|\btax\b"),
    "fine": _p(r"জরিমানা|অর্থদণ্ড|শাস্তি|\bfine\b|\bpenalty\b"),
    "income_limit": _p(r"আয়|\bincome\b"),
    "age_limit": _p(r"বয়স|\bage\b"),
    "deadline": _p(r"কত দিন|কতদিন|কত সময়|সময় লাগ|কত মাস|কখন|কবে|\bhow long\b|\bdays\b"),
    "validity": _p(r"মেয়াদ|বৈধ|\bvalid"),
    "document": _p(r"কাগজ|দলিল|ডকুমেন্ট|নথিপত্র|কী কী লাগ|কি কি লাগ|\bdocuments?\b|\bpapers?\b"),
}
SERVICE_CATEGORIES = frozenset(FOCUS) - {"fine", "document"}
CONTEXT_DIMENSIONS = ("applicant", "variant", "location", "programme")
MAX_PAIRS = 6  # reported per answer (prompt budget)
STATUS_ORDER = {
    "DIRECT_CONFLICT": 0,
    "POSSIBLE_CONFLICT": 1,
    "RESOLVED": 2,
    "TEMPORAL_DIFFERENCE": 3,
    "CONTEXT_DIFFERENCE": 4,
    "NO_CONFLICT": 5,
}


@dataclass
class ConflictPair:
    id: str
    a: Claim
    b: Claim
    status: ConflictStatus
    resolution: Resolution | None = None
    reasons: list[str] = field(default_factory=list)
    controlling: Claim | None = None
    judged_by: str = "rules"
    disclosed: bool = False

    @property
    def unresolved(self) -> bool:
        return self.resolution in ("UNRESOLVED_OFFICIAL_DISAGREEMENT", "UNRESOLVED_INSUFFICIENT_METADATA")

    @property
    def superseded(self) -> Claim | None:
        if self.controlling is None:
            return None
        return self.b if self.controlling is self.a else self.a


def question_focus(question: str) -> set[str]:
    text = unicodedata.normalize("NFC", question)
    return {category for category, pattern in FOCUS.items() if pattern.search(text)}


def document_key(name: str) -> str:
    return re.sub(r"[\s\W_]+", "", normalize_for_search(name))


def _same_document_item(a: Claim, b: Claim) -> bool:
    ka, kb = document_key(a.document_name or ""), document_key(b.document_name or "")
    return bool(ka and kb) and (ka == kb or (min(len(ka), len(kb)) >= 3 and (ka in kb or kb in ka)))


def comparable(a: Claim, b: Claim, focus: set[str]) -> bool:
    if a.document_id == b.document_id or a.category != b.category:
        return False
    if a.confidence == "low" or b.confidence == "low":
        return False
    if a.category == "document" and not _same_document_item(a, b):
        return False
    pa, pb = set(a.context.get("programme", [])), set(b.context.get("programme", []))
    if pa and pb and pa != pb:
        return False  # different allowance programmes: different services
    if pa and pb:
        return True
    if not focus:
        return False  # nothing asked and no shared programme: no basis to call it the same service
    return a.category in focus


def classify(a: Claim, b: Claim) -> tuple[ConflictStatus, list[str]]:
    """Status and reason codes for two comparable claims (no resolution yet)."""
    if a.kind == "required_document":
        if a.requirement == b.requirement or {a.requirement, b.requirement} == {"optional", "not_required"}:
            return "NO_CONFLICT", ["same_requirement"]
        if "conditional" in (a.requirement, b.requirement):
            return "POSSIBLE_CONFLICT", ["conditional_requirement"]
    else:
        if a.unit != b.unit:
            if {a.unit, b.unit} == {"day", "working_day"}:
                return "POSSIBLE_CONFLICT", ["day_type_differs"]
            return "POSSIBLE_CONFLICT", ["unit_differs"]
        if a.value == b.value:
            return "NO_CONFLICT", ["same_value"]
    pa, pb = set(a.context.get("period", [])), set(b.context.get("period", []))
    if pa and pb and not pa & pb:
        return "TEMPORAL_DIFFERENCE", ["different_periods"]
    if (pa == {"historical"}) != (pb == {"historical"}) and not (pa and pb):
        return "TEMPORAL_DIFFERENCE", ["historical_statement"]  # "ছিল ৩০০ টাকা" vs a present-tense figure
    if a.bound and b.bound and a.bound != b.bound:
        return "CONTEXT_DIFFERENCE", ["bound_differs"]
    unstated: list[str] = []
    for dim in CONTEXT_DIMENSIONS:
        x, y = set(a.context.get(dim, [])), set(b.context.get(dim, []))
        if x and y and x != y:
            return "CONTEXT_DIFFERENCE", [f"{dim}_differs"]
        if bool(x) != bool(y):
            unstated.append(f"{dim}_stated_in_one_source")
    if bool(pa) != bool(pb):
        unstated.append("period_stated_in_one_source")
    if a.conditional or b.conditional:
        unstated.append("conditions_present")
    if unstated:
        return "POSSIBLE_CONFLICT", unstated
    return "DIRECT_CONFLICT", ["same_context_different_value"]


def resolve(pair: ConflictPair, pa: SourceProfile, pb: SourceProfile) -> None:
    """Sets resolution/controlling on a classified pair, from verifiable source evidence only."""
    pair.resolution, pair.controlling = None, None
    if pair.status == "CONTEXT_DIFFERENCE":
        pair.resolution = "RESOLVED_BY_APPLICABILITY"
        return
    if pair.status not in ("DIRECT_CONFLICT", "POSSIBLE_CONFLICT"):
        return
    if (pa.status == "repealed") != (pb.status == "repealed"):
        pair.controlling = pair.b if pa.status == "repealed" else pair.a
        pair.status, pair.resolution = "RESOLVED", "RESOLVED_BY_SOURCE_STATUS"
        pair.reasons.append(f"repealed_source:{(pair.a if pa.status == 'repealed' else pair.b).label}")
        return
    if pair.status == "DIRECT_CONFLICT":
        for newer, older, claim in ((pa, pb, pair.a), (pb, pa, pair.b)):
            if amends(newer, older):
                pair.controlling = claim
                pair.status, pair.resolution = "RESOLVED", "RESOLVED_BY_EXPLICIT_SUPERSESSION"
                pair.reasons.append(f"amendment_act:{claim.label}")
                return
        pair.resolution = "UNRESOLVED_OFFICIAL_DISAGREEMENT"
        if pa.title_year and pb.title_year and pa.title_year != pb.title_year:
            pair.reasons.append("later_title_year_is_not_proof_of_supersession")
    else:
        pair.resolution = "UNRESOLVED_INSUFFICIENT_METADATA"
    if "compiled_guide" in (pa.source_type, pb.source_type):
        pair.reasons.append("compiled_guide_involved")
    if "official_website" in (pa.source_type, pb.source_type):
        pair.reasons.append("web_source_involved")


def detect(
    claims: Sequence[Claim], profiles: Mapping[str, SourceProfile], focus: set[str], start: int = 1
) -> list[ConflictPair]:
    """All non-trivial pairs (NO_CONFLICT dropped), most serious first, at most MAX_PAIRS, ids K<start>…."""
    seen: set[tuple] = set()
    pairs: list[ConflictPair] = []
    for i, a in enumerate(claims):
        for b in claims[i + 1 :]:
            if not comparable(a, b, focus):
                continue
            key = (
                a.category,
                frozenset({(a.document_id, a.value, a.requirement), (b.document_id, b.value, b.requirement)}),
            )
            if key in seen:
                continue
            seen.add(key)
            status, reasons = classify(a, b)
            if status == "NO_CONFLICT":
                continue
            pair = ConflictPair(id="", a=a, b=b, status=status, reasons=reasons)
            resolve(pair, profiles[a.label], profiles[b.label])
            pairs.append(pair)
    pairs.sort(key=lambda p: STATUS_ORDER[p.status])
    pairs = pairs[:MAX_PAIRS]
    for n, pair in enumerate(pairs, start=start):
        pair.id = f"K{n}"
    return pairs
