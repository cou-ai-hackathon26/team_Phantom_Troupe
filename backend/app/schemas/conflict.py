"""Official-source conflict detection: extracted claims (internal) and the analysis shown in API responses."""

from typing import Literal

from pydantic import BaseModel, Field

ClaimKind = Literal["fee", "processing_time", "eligibility", "validity_period", "required_document"]
Requirement = Literal["required", "optional", "conditional", "not_required"]
ConflictStatus = Literal[
    "NO_CONFLICT",
    "DIRECT_CONFLICT",
    "TEMPORAL_DIFFERENCE",
    "CONTEXT_DIFFERENCE",
    "POSSIBLE_CONFLICT",
    "INSUFFICIENT_EVIDENCE",
    "RESOLVED",
]
Resolution = Literal[
    "RESOLVED_BY_EXPLICIT_SUPERSESSION",  # an amendment act names the other act and is later
    "RESOLVED_BY_SOURCE_STATUS",  # one side is from a repealed act
    "RESOLVED_BY_APPLICABILITY",  # the two claims apply to different contexts
    "UNRESOLVED_OFFICIAL_DISAGREEMENT",
    "UNRESOLVED_INSUFFICIENT_METADATA",
]


class Claim(BaseModel):
    """One comparable statement found in a passage, with its exact provenance. Never an LLM summary."""

    id: str
    kind: ClaimKind
    # application_fee | allowance_amount | tax | fine | income_limit | age_limit | deadline | validity | document
    category: str
    value: float | None = None  # normalized number (None for documents)
    unit: str | None = None  # BDT | day | working_day | month | year | hour
    bound: Literal["min", "max"] | None = None
    requirement: Requirement | None = None  # documents only
    document_name: str | None = None  # documents only
    original_text: str  # as written in the source, e.g. "৭০০ টাকা"
    quote: str  # the source sentence containing it
    label: str  # passage label in this answer's prompt, e.g. "C2"
    chunk_id: str
    document_id: str
    section: str | None = None
    page: int | None = None
    context: dict[str, list[str]] = Field(default_factory=dict)  # applicant, variant, location, period, programme
    conditional: bool = False  # the sentence attaches a condition (যদি, তবে, শর্ত …)
    confidence: Literal["high", "low"] = "high"  # low = garbled text: never compared
    method: Literal["pattern", "llm_quote_verified"] = "pattern"


class ConflictSource(BaseModel):
    value: str  # original text of the claim, e.g. "৭০০ টাকা"
    marker: int | None = None  # citation marker in this answer ([১] = 1), None if not cited
    chunk_id: str
    document_id: str
    title: str
    source_type: str
    source_type_label: str
    title_year: int | None = None  # year printed in the document title, when there is one (not an effective date)
    status: Literal["repealed", "unknown"] = "unknown"
    quote: str


class ConflictItem(BaseModel):
    id: str
    claim_type: ClaimKind
    category: str
    topic: str  # Bangla name of what is compared, e.g. "ফি"
    status: ConflictStatus
    resolution: Resolution | None = None
    reason: str  # machine-readable reason code(s)
    controlling_chunk_id: str | None = None  # resolved conflicts: the source that applies
    judged_by: Literal["rules", "rules+llm"] = "rules"
    disclosed: bool = False  # the answer (or the added notice) shows this disagreement
    sources: list[ConflictSource]


class ConflictAnalysis(BaseModel):
    status: Literal["none", "resolved", "unresolved", "insufficient_evidence"]
    claims_checked: int = 0
    items: list[ConflictItem] = Field(default_factory=list)
