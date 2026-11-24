"""Official-source conflict detection. Fixture text is synthetic ("নমুনা সেবা"); no real fees, dates or rules."""

import asyncio
import re
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from app.core.config import settings
from app.models.llm_client import LLMResult
from app.repositories.bm25_repository import BM25Index
from app.repositories.qdrant_repository import DenseHit
from app.schemas.chat import ChatRequest
from app.schemas.conflict import Claim
from app.schemas.llm import AnswerOutput, NormalizeOutput
from app.services import orchestrator as orchestrator_module
from app.services.answer_cache import MemoryCache
from app.services.claim_extractor import extract_claims
from app.services.conflict_detector import ConflictPair, classify, detect, question_focus, resolve
from app.services.conflict_disclosure import apply_judgments, document_claims, prepare
from app.services.orchestrator import Orchestrator
from app.services.retrieval_service import Retriever
from app.services.source_profile import profile_for
from app.services.user_docs import UserDocStore

# ---------------------------------------------------------------------------- helpers


def claim(label: str = "C1", doc: str = "doc-a", **kw: Any) -> Claim:
    base: dict[str, Any] = dict(
        id=f"{label}:0",
        kind="fee",
        category="application_fee",
        value=500.0,
        unit="BDT",
        original_text="৫০০ টাকা",
        quote="নমুনা সেবার আবেদন ফি ৫০০ টাকা।",
        label=label,
        chunk_id=f"{doc}-s1",
        document_id=doc,
    )
    return Claim(**(base | kw))


def profile(doc: str, title: str):
    return profile_for(doc, title)


def pair_of(a: Claim, b: Claim, pa_title: str = "নমুনা নীতিমালা", pb_title: str = "নমুনা নির্দেশিকা") -> ConflictPair:
    status, reasons = classify(a, b)
    pair = ConflictPair(id="K1", a=a, b=b, status=status, reasons=reasons)
    resolve(pair, profile(a.document_id, pa_title), profile(b.document_id, pb_title))
    return pair


def passage(cid: str, text: str, doc: str, act: str = "নমুনা নীতিমালা", kind: str = "official") -> SimpleNamespace:
    return SimpleNamespace(
        id=cid, document_id=doc, act=act, title=act, citation=f"{act}, অংশ ১", section="১", part=None,
        text=text, page_start=None, source_url=None, notes=[], kind=kind,
    )  # fmt: skip


# ---------------------------------------------------------------------------- spec §14.1 unit cases


def test_01_same_fee_is_no_conflict() -> None:
    assert classify(claim(), claim("C2", "doc-b"))[0] == "NO_CONFLICT"


def test_02_same_context_different_fee_is_direct_and_unresolved() -> None:
    pair = pair_of(claim(), claim("C2", "doc-b", value=700.0, original_text="৭০০ টাকা"))
    assert pair.status == "DIRECT_CONFLICT" and pair.resolution == "UNRESOLVED_OFFICIAL_DISAGREEMENT"
    assert pair.controlling is None


def test_03_same_context_different_duration_is_direct() -> None:
    a = claim(kind="processing_time", category="deadline", value=7.0, unit="working_day", original_text="৭ কার্যদিবস")
    b = claim("C2", "doc-b", kind="processing_time", category="deadline", value=15.0, unit="working_day")
    assert classify(a, b)[0] == "DIRECT_CONFLICT"


def test_04_working_days_and_calendar_days_are_not_equivalent() -> None:
    a = claim(kind="processing_time", category="deadline", value=7.0, unit="working_day")
    b = claim("C2", "doc-b", kind="processing_time", category="deadline", value=7.0, unit="day")
    assert classify(a, b) == ("POSSIBLE_CONFLICT", ["day_type_differs"])


def test_05_urgent_and_regular_are_a_context_difference() -> None:
    pair = pair_of(
        claim(context={"variant": ["urgent"]}), claim("C2", "doc-b", value=700.0, context={"variant": ["regular"]})
    )
    assert pair.status == "CONTEXT_DIFFERENCE" and pair.resolution == "RESOLVED_BY_APPLICABILITY"


def test_06_different_applicants_are_a_context_difference() -> None:
    a = claim(kind="eligibility", category="age_limit", value=65.0, unit="year", context={"applicant": ["male"]})
    b = claim(
        "C2",
        "doc-b",
        kind="eligibility",
        category="age_limit",
        value=62.0,
        unit="year",
        context={"applicant": ["female"]},
    )
    assert classify(a, b) == ("CONTEXT_DIFFERENCE", ["applicant_differs"])


def test_07_explicitly_different_periods_are_temporal() -> None:
    a = claim(category="allowance_amount", context={"period": ["FY2001-02"]})
    b = claim("C2", "doc-b", category="allowance_amount", value=700.0, context={"period": ["FY2024-25"]})
    assert classify(a, b)[0] == "TEMPORAL_DIFFERENCE"


def _doc_claim(label: str, doc: str, name: str, requirement: str) -> Claim:
    return claim(
        label, doc, kind="required_document", category="document", value=None, unit=None,
        document_name=name, requirement=requirement, original_text=name,
    )  # fmt: skip


def test_08_a_document_missing_from_one_source_is_not_a_conflict() -> None:
    claims = [_doc_claim("C1", "doc-a", "নমুনা সনদ", "required"), _doc_claim("C2", "doc-b", "অন্য নমুনা কাগজ", "required")]
    profiles = {"C1": profile("doc-a", "নমুনা নীতিমালা"), "C2": profile("doc-b", "নমুনা নির্দেশিকা")}
    assert detect(claims, profiles, {"document"}) == []


def test_09_required_versus_explicitly_not_required_is_a_conflict() -> None:
    pair = pair_of(
        _doc_claim("C1", "doc-a", "নমুনা সনদ", "required"), _doc_claim("C2", "doc-b", "নমুনা সনদ", "not_required")
    )
    assert pair.status == "DIRECT_CONFLICT" and pair.unresolved


def test_10_missing_dates_never_make_a_source_current() -> None:
    p = profile("doc-x", "নমুনা সেবা নির্দেশিকা")
    assert p.title_year is None and p.status == "unknown"
    pair = pair_of(claim(), claim("C2", "doc-b", value=700.0), "নমুনা সেবা নির্দেশিকা", "নমুনা নোটিশ")
    assert pair.status == "DIRECT_CONFLICT" and pair.controlling is None


def test_11_a_later_title_year_alone_does_not_resolve() -> None:
    pair = pair_of(claim(), claim("C2", "doc-b", value=700.0), "নমুনা নীতিমালা, ২০১০", "নমুনা নীতিমালা, ২০২০")
    assert pair.resolution == "UNRESOLVED_OFFICIAL_DISAGREEMENT"
    assert "later_title_year_is_not_proof_of_supersession" in pair.reasons


def test_12_explicit_amendment_resolves_only_when_applicability_matches() -> None:
    old, new = "নমুনা সেবা আইন, ২০১০", "নমুনা সেবা (সংশোধন) আইন, ২০২০"
    pair = pair_of(claim(), claim("C2", "doc-b", value=700.0), old, new)
    assert pair.status == "RESOLVED" and pair.resolution == "RESOLVED_BY_EXPLICIT_SUPERSESSION"
    assert pair.controlling is not None and pair.controlling.label == "C2"
    # applicability not established (applicant stated in one source only): stays unresolved
    possible = pair_of(claim(context={"applicant": ["worker"]}), claim("C2", "doc-b", value=700.0), old, new)
    assert possible.status == "POSSIBLE_CONFLICT" and possible.resolution == "UNRESOLVED_INSUFFICIENT_METADATA"


def test_13_repealed_source_is_resolved_by_status() -> None:
    pair = pair_of(claim(), claim("C2", "doc-b", value=700.0), "নমুনা আইন, ২০১০", "পুরাতন নমুনা আইন, ১৯৯০ [রহিত]")
    assert pair.resolution == "RESOLVED_BY_SOURCE_STATUS" and pair.controlling and pair.controlling.label == "C1"


def test_14_invalid_structured_output_is_rejected_safely() -> None:
    assert (
        AnswerOutput.model_validate(
            {"answer": "x", "conflict_judgments": "garbage", "document_claims": [1]}
        ).document_claims
        == []
    )
    run = prepare({"C1": passage("a-1", "নমুনা সনদ প্রয়োজন হইবে।", "doc-a")}, "কী কী কাগজ লাগবে?")
    items = [
        {"label": "C1", "document": "নমুনা সনদ", "requirement": "required", "quote": "নমুনা সনদ প্রয়োজন হইবে"},
        {
            "label": "C1",
            "document": "বানানো কাগজ",
            "requirement": "required",
            "quote": "এই কথা নথিতে নেই",
        },  # not in passage
        {"label": "C9", "document": "নমুনা সনদ", "requirement": "required", "quote": "নমুনা সনদ প্রয়োজন হইবে"},  # bad label
        {"label": "C1", "document": "নমুনা সনদ", "requirement": "maybe", "quote": "নমুনা সনদ প্রয়োজন হইবে"},  # bad enum
    ]
    kept = document_claims(run, items)
    assert [(c.document_name, c.method) for c in kept] == [("নমুনা সনদ", "llm_quote_verified")]


def test_15_claims_point_to_their_original_passage() -> None:
    labelled = {
        "C1": passage("a-1", "নমুনা সেবার আবেদন ফি ৫০০ টাকা।", "doc-a"),
        "C2": passage("b-1", "নমুনা সেবার আবেদন ফি ৭০০ টাকা।", "doc-b"),
    }
    claims = extract_claims(labelled)
    assert [(c.label, c.chunk_id, c.document_id, c.value) for c in claims] == [
        ("C1", "a-1", "doc-a", 500.0),
        ("C2", "b-1", "doc-b", 700.0),
    ]
    assert claims[0].quote == "নমুনা সেবার আবেদন ফি ৫০০ টাকা।" and claims[0].original_text == "৫০০ টাকা"


# ---------------------------------------------------------------------------- extraction and profiles


def test_extraction_skips_budgets_prison_terms_and_garbled_numbers() -> None:
    text = (
        "নমুনা কর্মসূচির বাজেট ৫২৩৯.২৫ কোটি টাকা। এই অপরাধে অনধিক তিন মাস কারাদণ্ড হইবে। "
        "নমুনা ভাতার হার ৭০ ৫ টাকা। আবেদন প্রাপ্তির সাত কার্যদিবসের মধ্যে নিষ্পত্তি করিতে হইবে।"
    )
    claims = extract_claims({"C1": passage("a-1", text, "doc-a")})
    assert [(c.category, c.value, c.unit, c.confidence) for c in claims] == [
        ("allowance_amount", 5.0, "BDT", "low"),  # "৭০ ৫": digits split by a space, never compared
        ("deadline", 7.0, "working_day", "high"),
    ]


def test_extraction_reads_applicants_bounds_and_periods() -> None:
    text = "নমুনা বয়স: পুরুষের ক্ষেত্রে ন্যূনতম ৬৫ বছর, মহিলার ক্ষেত্রে ন্যূনতম ৬২ বছর। ২০২৪-২৫ অর্থবছরে নমুনা ভাতার হার ৭০০ টাকা।"
    claims = extract_claims({"C1": passage("a-1", text, "doc-a")})
    assert [(c.value, c.bound, c.context) for c in claims] == [
        (65.0, "min", {"applicant": ["male"]}),
        (62.0, "min", {"applicant": ["female"]}),
        (700.0, None, {"period": ["FY2024-25"]}),
    ]


def test_source_profiles_use_only_evidence() -> None:
    assert profile("md-x", "নমুনা আইন, ২০২০ (সংকলিত নির্দেশিকা)").source_type == "compiled_guide"
    assert profile("md-x", "নমুনা আইন, ২০২০ (সংকলিত নির্দেশিকা)").title_year is None  # the law's year, not the guide's
    assert profile("x-1", "নমুনা হোমপেজ (ওয়েবপেজ) ২০২৫").title_year is None
    assert profile("x-2", "নমুনা দুর্নীতি দমন আইন, ২০০৪").source_type == "act"  # "দুর্নীতি" is not "নীতি"
    assert profile("x-3", "নমুনা নীতিমালা, ২০১৫").source_type == "policy"
    assert profile("x-4", "পুরাতন নমুনা আইন, ১৯৯০ [রহিত]").status == "repealed"


def test_question_focus() -> None:
    assert question_focus("নমুনা সেবার ফি কত?") == {"application_fee"}
    assert "document" in question_focus("এর জন্য কী কী কাগজ লাগবে?")
    assert question_focus("নমুনা প্রশ্ন") == set()


def test_unfocused_question_compares_only_the_same_named_programme() -> None:
    a = claim(category="allowance_amount", context={"programme": ["old_age"]})
    b = claim("C2", "doc-b", category="allowance_amount", value=700.0, context={"programme": ["old_age"]})
    c = claim("C3", "doc-c", category="allowance_amount", value=900.0, context={"programme": ["widow"]})
    d = claim("C4", "doc-d", category="application_fee", value=900.0)
    profiles = {lb: profile(f"doc-{lb}", "নমুনা নির্দেশিকা") for lb in ("C1", "C2", "C3", "C4")}
    pairs = detect([a, b, c, d], profiles, focus=set())
    assert [(p.a.label, p.b.label) for p in pairs] == [("C1", "C2")]


def test_llm_judgements_need_evidence() -> None:
    labelled = {
        "C1": passage("a-1", "নমুনা সেবার আবেদন ফি ৫০০ টাকা।", "doc-a"),
        "C2": passage("b-1", "শ্রমিকদের জন্য নমুনা সেবার আবেদন ফি ৭০০ টাকা।", "doc-b"),
        "C3": passage("c-1", "নমুনা সেবার আবেদন ফি ৯০০ টাকা।", "doc-c"),
    }
    run = prepare(labelled, "নমুনা সেবার ফি কত?")
    by_docs = {frozenset({p.a.document_id, p.b.document_id}): p for p in run.pairs}
    k_ab, k_ac = by_docs[frozenset({"doc-a", "doc-b"})], by_docs[frozenset({"doc-a", "doc-c"})]
    assert k_ab.status == "POSSIBLE_CONFLICT" and k_ac.status == "DIRECT_CONFLICT"
    apply_judgments(
        run,
        [
            {"id": k_ab.id, "same_context": False, "difference_quote": "শ্রমিকদের জন্য"},  # verified in C2
            {"id": k_ac.id, "same_context": False, "difference_quote": "বানানো পার্থক্য"},  # not in either passage
        ],
    )
    assert k_ab.status == "CONTEXT_DIFFERENCE" and k_ab.judged_by == "rules+llm"
    assert k_ac.status == "DIRECT_CONFLICT" and k_ac.unresolved


# ---------------------------------------------------------------------------- integration through the orchestrator


def _chunk(cid: str, doc: str, act: str, text: str):
    from app.schemas.ingestion import ChunkRecord

    return ChunkRecord(
        id=cid, document_id=doc, area="general", act=act, chapter=None, section="১", title=f"শিরোনাম {cid}",
        citation=f"{act}, ধারা ১", part=None, text=text, normalized_text=text, token_count=10, source_url=None,
    )  # fmt: skip


FEE_A = _chunk("fee-a", "doc-fee-a", "নমুনা সেবা নীতিমালা", "নমুনাসেবার আবেদন ফি ৫০০ টাকা।")
FEE_B = _chunk("fee-b", "doc-fee-b", "নমুনা সেবা নির্দেশিকা", "নমুনাসেবার আবেদন ফি ৭০০ টাকা।")
OTHER = _chunk("other", "doc-other", "অন্য নমুনা নির্দেশিকা", "পূরকসেবার আবেদন সরাসরি জমা দিতে হইবে।")
# unrelated passages: a 3-document BM25 corpus gives zero or negative IDF and retrieves nothing
FILLERS = [_chunk(f"fill-{i}", f"doc-fill-{i}", "পূরক নথি", f"পূরকশব্দ{i} সাধারণ লেখা।") for i in range(10)]


class NoDense:
    async def search(self, vector: Any, top_k: int, area: str | None = None) -> list[DenseHit]:
        return []


class Emb:
    def embed_query(self, text: str) -> list[float]:
        return [0.0]


class LLM:
    """Call 1 returns `normalize`; Call 2 is computed from the prompt by `answer(system, user)`."""

    model = "fake-model"

    def __init__(self, normalize: NormalizeOutput, answer: Callable[[str, str], AnswerOutput]) -> None:
        self.normalize, self.answer = normalize, answer
        self.calls: list[tuple[str, str, str]] = []

    async def complete_json(self, system: str, user: str, schema: type[BaseModel], **kw: Any) -> LLMResult:
        self.calls.append((kw.get("purpose", "?"), system, user))
        data = self.normalize if schema is NormalizeOutput else self.answer(system, user)
        return LLMResult(data=data, model=self.model, latency_ms=1, prompt_tokens=1, completion_tokens=1)


def label_of(user: str, snippet: str) -> str:
    for block in user.split("\n\n"):
        if snippet in block and (m := re.search(r"^\[(C\d+)\]", block, re.MULTILINE)):
            return m.group(1)
    raise AssertionError(f"{snippet} not in prompt")


def ask(chunks: list, question: str, answer: Callable[[str, str], AnswerOutput], **req: Any):
    llm = LLM(NormalizeOutput(standard_bangla=question, area="general"), answer)
    retriever = Retriever(BM25Index.build([*chunks, *FILLERS]), NoDense(), Emb())  # type: ignore[arg-type]
    orch = Orchestrator(retriever, llm, MemoryCache(), user_docs=req.pop("user_docs", UserDocStore()))  # type: ignore[arg-type]
    resp = asyncio.run(orch.run(ChatRequest(message=question, **req)))
    return resp, llm


def one_sided(system: str, user: str) -> AnswerOutput:
    lb = label_of(user, "৭০০ টাকা")
    return AnswerOutput(answer=f"আবেদন ফি ৭০০ টাকা [{lb}]।", used_chunk_ids=[lb], found=True)


def test_integration_unresolved_conflict_is_disclosed_even_if_call_2_picks_one_side() -> None:
    resp, llm = ask([FEE_A, FEE_B, OTHER], "নমুনাসেবার ফি কত?", one_sided)
    _, system, user = llm.calls[1]
    assert "CONFLICT CHECK" in system and "<conflict_check>" in user and "UNRESOLVED_OFFICIAL_DISAGREEMENT" in user
    assert "৫০০ টাকা" in resp.answer and "৭০০ টাকা" in resp.answer and "নিশ্চিত করা যায়নি" in resp.answer
    assert {c.chunk_id for c in resp.citations} == {"fee-a", "fee-b"}  # both sides cited
    analysis = resp.conflict_analysis
    assert analysis and analysis.status == "unresolved"
    (item,) = analysis.items
    assert item.disclosed and {s.chunk_id for s in item.sources} == {"fee-a", "fee-b"}
    markers = {c.chunk_id: c.marker for c in resp.citations}
    assert {s.chunk_id: s.marker for s in item.sources} == markers
    assert resp.warnings and llm.calls[0][0] == "normalize" and len(llm.calls) == 2  # still 2 LLM calls


def test_integration_model_that_discloses_both_sides_gets_no_extra_notice() -> None:
    def both(system: str, user: str) -> AnswerOutput:
        a, b = label_of(user, "৫০০ টাকা"), label_of(user, "৭০০ টাকা")
        text = f"নথিগুলোতে ভিন্ন তথ্য আছে: ৫০০ টাকা [{a}] এবং ৭০০ টাকা [{b}]।"
        return AnswerOutput(answer=text, used_chunk_ids=[a, b], found=True)

    resp, _ = ask([FEE_A, FEE_B, OTHER], "নমুনাসেবার ফি কত?", both)
    assert "সতর্কতা" not in resp.answer and resp.conflict_analysis and resp.conflict_analysis.status == "unresolved"


def test_integration_repealed_side_gives_the_controlling_value() -> None:
    old = _chunk("fee-b", "doc-fee-b", "পুরাতন নমুনা সেবা আইন, ১৯৯০ [রহিত]", "নমুনাসেবার আবেদন ফি ৭০০ টাকা।")
    resp, _ = ask([FEE_A, old, OTHER], "নমুনাসেবার ফি কত?", one_sided)
    assert resp.conflict_analysis and resp.conflict_analysis.status == "resolved"
    (item,) = resp.conflict_analysis.items
    assert item.resolution == "RESOLVED_BY_SOURCE_STATUS" and item.controlling_chunk_id == "fee-a"
    assert "রহিত আইনের" in resp.answer and "৫০০ টাকা" in resp.answer


def test_integration_question_without_conflict_is_unchanged() -> None:
    def plain(system: str, user: str) -> AnswerOutput:
        lb = label_of(user, "পূরকসেবার")
        return AnswerOutput(answer=f"আবেদন সরাসরি জমা দিতে হবে [{lb}]।", used_chunk_ids=[lb], found=True)

    resp, llm = ask([OTHER, _chunk("o2", "doc-o2", "নমুনা", "পূরকসেবার নিয়ম।")], "পূরকসেবার আবেদন কোথায়?", plain)
    assert "CONFLICT CHECK" not in llm.calls[1][1] and "<conflict_check>" not in llm.calls[1][2]
    assert resp.answer == "আবেদন সরাসরি জমা দিতে হবে [১]।"
    assert resp.conflict_analysis and resp.conflict_analysis.status == "none" and resp.conflict_analysis.items == []


def test_integration_personal_document_is_never_compared() -> None:
    store = UserDocStore()
    doc = store.add("mine.pdf", [(1, "আমার নমুনাসেবার আবেদন ফি ৯০০ টাকা লেখা আছে।")], ["text"], False)

    def answer(system: str, user: str) -> AnswerOutput:
        lb = label_of(user, "৫০০ টাকা")
        return AnswerOutput(answer=f"আবেদন ফি ৫০০ টাকা [{lb}]।", used_chunk_ids=[lb], found=True)

    resp, llm = ask([FEE_A, OTHER], "নমুনাসেবার ফি কত?", answer, user_doc_id=doc.id, user_docs=store)
    assert "<conflict_check>" not in llm.calls[1][2]
    assert resp.conflict_analysis and resp.conflict_analysis.items == []


def test_integration_switch_off_and_failure_fall_back_safely(monkeypatch) -> None:
    monkeypatch.setattr(settings, "conflict_detection", False)
    resp, llm = ask([FEE_A, FEE_B, OTHER], "নমুনাসেবার ফি কত?", one_sided)
    assert resp.conflict_analysis is None and "<conflict_check>" not in llm.calls[1][2]
    assert resp.answer == "আবেদন ফি ৭০০ টাকা [১]।"

    monkeypatch.setattr(settings, "conflict_detection", True)

    def boom(*a: Any, **k: Any):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(orchestrator_module, "prepare", boom)
    resp, _ = ask([FEE_A, FEE_B, OTHER], "নমুনাসেবার ফি কত?", one_sided)
    assert (
        resp.status == "answered"
        and resp.conflict_analysis
        and resp.conflict_analysis.status == "insufficient_evidence"
    )


def test_integration_document_claims_with_verified_quotes() -> None:
    doc_a = _chunk("doc-a1", "doc-docs-a", "নমুনা সেবা নীতিমালা", "নমুনাসেবার জন্য নমুনা সনদ প্রয়োজন হইবে।")
    doc_b = _chunk("doc-b1", "doc-docs-b", "নমুনা সেবা নির্দেশিকা", "নমুনাসেবার জন্য নমুনা সনদ প্রয়োজন নাই।")

    def answer(system: str, user: str) -> AnswerOutput:
        assert "DOCUMENT_CLAIMS_REQUESTED" in user
        a, b = label_of(user, "প্রয়োজন হইবে"), label_of(user, "প্রয়োজন নাই")
        return AnswerOutput(
            answer=f"নমুনা সনদ লাগবে [{a}]।",
            used_chunk_ids=[a],
            found=True,
            document_claims=[
                {"label": a, "document": "নমুনা সনদ", "requirement": "required", "quote": "নমুনা সনদ প্রয়োজন হইবে"},
                {"label": b, "document": "নমুনা সনদ", "requirement": "not_required", "quote": "নমুনা সনদ প্রয়োজন নাই"},
            ],
        )

    resp, _ = ask([doc_a, doc_b, OTHER], "নমুনাসেবার জন্য কী কী কাগজ লাগবে?", answer)
    assert resp.conflict_analysis and resp.conflict_analysis.status == "unresolved"
    (item,) = resp.conflict_analysis.items
    assert item.claim_type == "required_document" and item.status == "DIRECT_CONFLICT"
    assert "নমুনা সনদ: প্রয়োজন নেই" in resp.answer and {c.chunk_id for c in resp.citations} == {"doc-a1", "doc-b1"}


@pytest.mark.parametrize("text", ["নমুনা সেবার আবেদন ফি ৫০০ টাকা।"])
def test_web_passage_profile_never_resolves(text: str) -> None:
    labelled = {
        "C1": passage("a-1", text, "doc-a"),
        "W1": passage("web:1", "নমুনা সেবার আবেদন ফি ৭০০ টাকা।", "web:1", act="সরকারি ওয়েবসাইট", kind="web"),
    }
    run = prepare(labelled, "নমুনা সেবার ফি কত?")
    (pair,) = run.pairs
    assert pair.unresolved and "web_source_involved" in pair.reasons


def test_historical_figures_are_a_temporal_difference_not_a_conflict() -> None:
    labelled = {
        "C1": passage("a-1", "শুরুতে নমুনা ভাতার পরিমাণ ছিল ৩০০ টাকা।", "doc-a"),
        "C2": passage("b-1", "নমুনা ভাতার মাসিক হার ৭০০ টাকা।", "doc-b"),
    }
    run = prepare(labelled, "নমুনা ভাতার পরিমাণ কত?")
    (pair,) = run.pairs
    assert pair.status == "TEMPORAL_DIFFERENCE" and pair.reasons == ["historical_statement"]


def test_a_year_just_before_a_line_break_is_the_period_of_the_next_line() -> None:
    (c,) = extract_claims({"C1": passage("a-1", "২০২৪-২৫\nঅর্থবছরে জনপ্রতি নমুনা ভাতার হার ৭০০ টাকা।", "doc-a")})
    assert c.context["period"] == ["FY2024-25"]
