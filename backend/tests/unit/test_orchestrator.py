"""Pipeline tests with the LLM and Qdrant mocked. Fixture text is synthetic placeholder text."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api import dependencies
from app.core.constants import RATE_LIMIT_TEXT, REFUSAL_TEXT
from app.main import app
from app.models.llm_client import LLMBadOutput, LLMRateLimited, LLMResult
from app.repositories.bm25_repository import BM25Index
from app.repositories.qdrant_repository import DenseHit
from app.schemas.chat import ChatRequest
from app.schemas.ingestion import ChunkRecord
from app.schemas.llm import AnswerOutput, NormalizeOutput
from app.services.answer_cache import MemoryCache, cache_key
from app.services.citation_validator import numbers_in, validate_answer
from app.services.orchestrator import Orchestrator
from app.services.retrieval_service import Retriever


def _chunk(cid: str, section: str, text: str) -> ChunkRecord:
    return ChunkRecord(
        id=cid,
        document_id="t",
        area="labour",
        act="পরীক্ষা আইন",
        chapter=None,
        section=section,
        title=f"শিরোনাম {section}",
        citation=f"পরীক্ষা আইন, ধারা {section}",
        part=None,
        text=text,
        normalized_text=text,
        token_count=10,
        source_url="https://example.invalid/s",
    )


CHUNKS = [
    _chunk("t-s1", "১", "আলফা নিয়ম অনুযায়ী ৬০ দিন সময় লাগিবে।"),
    _chunk("t-s2", "২", "বিটা নিয়ম গামা শব্দ।"),
]


class FakeQdrant:
    def __init__(self, score: float = 0.9) -> None:
        self.score = score

    async def search(self, vector: Any, top_k: int, area: str | None = None) -> list[DenseHit]:
        return [DenseHit("t-s1", self.score, 1), DenseHit("t-s2", self.score - 0.05, 2)]


class FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [0.0]


class FakeLLM:
    model = "fake-model"

    def __init__(self, normalize: NormalizeOutput | Exception, answer: AnswerOutput | Exception | None = None):
        self.normalize = normalize
        self.answer = answer
        self.calls: list[str] = []

    async def complete_json(self, system: str, user: str, schema: type[BaseModel], **kw: Any) -> LLMResult:
        self.calls.append(kw.get("purpose", "?"))
        value = self.normalize if schema is NormalizeOutput else self.answer
        if isinstance(value, Exception):
            raise value
        assert value is not None
        return LLMResult(data=value, model=self.model, latency_ms=1, prompt_tokens=1, completion_tokens=1)


def make(llm: FakeLLM, score: float = 0.9, cache: MemoryCache | None = None) -> Orchestrator:
    retriever = Retriever(BM25Index.build(CHUNKS), FakeQdrant(score), FakeEmbedder())  # type: ignore[arg-type]
    return Orchestrator(retriever, llm, cache or MemoryCache())  # type: ignore[arg-type]


IN_SCOPE = NormalizeOutput(standard_bangla="আলফা নিয়মে কত দিন?", area="labour", in_scope=True)


def ask(orch: Orchestrator, message: str = "আলফা নিয়মে কতদিন লাগে?", debug: bool = False):
    return asyncio.run(orch.run(ChatRequest(message=message, debug=debug)))


def test_answered_with_citation_markers_and_two_llm_calls() -> None:
    llm = FakeLLM(IN_SCOPE, AnswerOutput(answer="১. সময় লাগিবে ৬০ দিন [C1]।", used_chunk_ids=["C1"], found=True))
    resp = ask(make(llm), debug=True)
    assert resp.status == "answered"
    assert resp.answer == "১. সময় লাগিবে ৬০ দিন [১]।"
    assert [c.chunk_id for c in resp.citations] == ["t-s1"]
    assert resp.citations[0].marker == 1 and resp.citations[0].source_url
    assert llm.calls == ["normalize", "answer"]
    assert resp.trace is not None and resp.trace.llm_calls == 2
    assert resp.request_id


def test_out_of_scope_refuses_without_second_call() -> None:
    llm = FakeLLM(NormalizeOutput(standard_bangla="আবহাওয়া কেমন?", area="unknown", in_scope=False))
    resp = ask(make(llm))
    assert resp.status == "refused"
    assert resp.answer == REFUSAL_TEXT
    assert resp.citations == []
    assert llm.calls == ["normalize"]


def test_low_score_and_no_bm25_hit_refuses_without_second_call() -> None:
    llm = FakeLLM(NormalizeOutput(standard_bangla="অজানা প্রশ্ন", area="labour", in_scope=True))
    resp = ask(make(llm, score=0.5), message="অজানা প্রশ্ন")
    assert resp.status == "refused" and resp.answer == REFUSAL_TEXT
    assert llm.calls == ["normalize"]


def test_not_found_refuses() -> None:
    llm = FakeLLM(IN_SCOPE, AnswerOutput(answer="", used_chunk_ids=[], found=False))
    resp = ask(make(llm))
    assert resp.status == "refused" and resp.answer == REFUSAL_TEXT and resp.citations == []


def test_invalid_chunk_id_dropped_and_all_invalid_refuses() -> None:
    llm = FakeLLM(IN_SCOPE, AnswerOutput(answer="উত্তর [C9]", used_chunk_ids=["C9", "made-up-id"], found=True))
    resp = ask(make(llm))
    assert resp.status == "refused"


def test_invalid_id_dropped_valid_kept() -> None:
    labelled = {"C1": CHUNKS[0], "C2": CHUNKS[1]}
    v = validate_answer(AnswerOutput(answer="উত্তর [C2]", used_chunk_ids=["C7", "C2"], found=True), labelled)
    assert v.status == "answered"
    assert v.used_chunk_ids == ["t-s2"] and v.dropped_ids == ["C7"]
    assert v.answer == "উত্তর [১]"


def test_numeric_mismatch_marks_partial_with_warning() -> None:
    llm = FakeLLM(IN_SCOPE, AnswerOutput(answer="সময় লাগিবে ৯০ দিন [C1]।", used_chunk_ids=["C1"], found=True))
    resp = ask(make(llm))
    assert resp.status == "partial"
    assert resp.warnings and "৯০" in resp.warnings[0]


def test_numbers_ignore_list_numbering_and_markers() -> None:
    assert numbers_in("১. প্রথম ধাপ\n২. দ্বিতীয় ধাপে ৬০ দিন") == {"60"}
    assert numbers_in("প্রথম ধাপ। ২. দ্বিতীয় ধাপ। ৩. তৃতীয় ধাপে ৬০ দিন") == {"60"}
    assert numbers_in("মোট ৪৫,০০০ টাকা") == {"45000"}


def test_numbers_compare_by_value() -> None:
    # real case: §19 says "০৬ (ছয়) মাসের", the answer said "৬ (ছয়) মাসের"
    assert numbers_in("উহার ০৬ (ছয়) মাসের") == numbers_in("৬ (ছয়) মাসের") == {"6"}
    assert numbers_in("১,০০০ টাকা") == {"1000"}


def test_clarification_path() -> None:
    llm = FakeLLM(
        NormalizeOutput(
            standard_bangla="ভাতা",
            area="allowance",
            in_scope=True,
            needs_clarification=True,
            clarification_question="কোন ভাতার কথা জানতে চান?",
        )
    )
    resp = ask(make(llm), message="ভাতা")
    assert resp.status == "clarify"
    assert resp.answer == "কোন ভাতার কথা জানতে চান?"
    assert llm.calls == ["normalize"]


def test_cache_hit_skips_llm() -> None:
    cache = MemoryCache()
    llm = FakeLLM(IN_SCOPE, AnswerOutput(answer="৬০ দিন [C1]", used_chunk_ids=["C1"], found=True))
    first = ask(make(llm, cache=cache))
    assert not first.cached
    llm2 = FakeLLM(LLMRateLimited("should not be called"))
    second = ask(make(llm2, cache=cache), debug=True)
    assert second.cached and second.answer == first.answer
    assert llm2.calls == []
    assert second.trace is not None  # trace survives the cache for the demo panel


def test_normalize_bad_json_falls_back_to_raw_question() -> None:
    llm = FakeLLM(LLMBadOutput("broken"), AnswerOutput(answer="৬০ দিন [C1]", used_chunk_ids=["C1"], found=True))
    resp = ask(make(llm))
    assert resp.status == "answered"
    assert resp.area == "unknown"  # searched all areas


def test_answer_bad_json_refuses() -> None:
    llm = FakeLLM(IN_SCOPE, LLMBadOutput("broken"))
    resp = ask(make(llm))
    assert resp.status == "refused" and resp.answer == REFUSAL_TEXT
    assert len(llm.calls) == 2  # never a third call


@pytest.fixture
def client_with():
    def _make(orch: Orchestrator) -> TestClient:
        app.dependency_overrides[dependencies.orchestrator_dep] = lambda: orch
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def test_chat_route_maps_rate_limit_to_503(client_with) -> None:
    client = client_with(make(FakeLLM(LLMRateLimited("429"))))
    resp = client.post("/api/v1/chat", json={"message": "আলফা নিয়ম?"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == {"code": "rate_limited", "message": RATE_LIMIT_TEXT}


def test_chat_route_validates_input(client_with) -> None:
    client = client_with(make(FakeLLM(IN_SCOPE)))
    assert client.post("/api/v1/chat", json={"message": "a"}).status_code == 422
    assert client.post("/api/v1/chat", json={"message": "প্রশ্ন", "area": "space"}).status_code == 422


def test_model_written_and_repeated_markers_are_cleaned() -> None:
    labelled = {"C1": CHUNKS[0], "C2": CHUNKS[1]}
    out = AnswerOutput(answer="এক [C1][C1] দুই [C2][৫] তিন [C1, C2]", used_chunk_ids=["C1", "C2"], found=True)
    v = validate_answer(out, labelled)
    assert v.answer == "এক [১] দুই [২] তিন [১][২]"
    assert v.status == "answered"  # "৫" inside a stray marker is not treated as a claimed number


def test_known_area_with_in_scope_false_is_not_refused_outright() -> None:
    llm = FakeLLM(
        NormalizeOutput(standard_bangla="আলফা নিয়ম কী?", area="labour", in_scope=False),
        AnswerOutput(answer="৬০ দিন [C1]", used_chunk_ids=["C1"], found=True),
    )
    resp = ask(make(llm))
    assert resp.status == "answered" and llm.calls == ["normalize", "answer"]


def test_wrong_area_with_no_documents_falls_back_to_all_areas() -> None:
    llm = FakeLLM(
        NormalizeOutput(standard_bangla="আলফা নিয়ম কী?", area="land", in_scope=True),  # misclassified
        AnswerOutput(answer="৬০ দিন [C1]", used_chunk_ids=["C1"], found=True),
    )
    resp = ask(make(llm), debug=True)
    assert resp.status == "answered"
    assert resp.trace is not None and resp.trace.candidates


def test_number_words_in_source_support_digits_in_answer() -> None:
    # real case: §18 says "আট কিলোমিটার", the answer said "৮ কিমি"
    chunk = _chunk("t-s18", "১৮", "একই শহরে বা গ্রামে অথবা আট কিলোমিটার দূরত্বের মধ্যে")
    v = validate_answer(
        AnswerOutput(answer="৮ কিমি দূরত্বের মধ্যে [C1]", used_chunk_ids=["C1"], found=True), {"C1": chunk}
    )
    assert v.status == "answered" and not v.warnings
    v2 = validate_answer(AnswerOutput(answer="৯ কিমি [C1]", used_chunk_ids=["C1"], found=True), {"C1": chunk})
    assert v2.status == "partial"


# ---------------------------------------------------------------- search_query and area fallback


class RecordingEmbedder(FakeEmbedder):
    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.0]


class AreaQdrant(FakeQdrant):
    """Returns hits only for unfiltered searches, like a document filed under another area."""

    def __init__(self) -> None:
        super().__init__()
        self.areas: list[str | None] = []

    async def search(self, vector: Any, top_k: int, area: str | None = None) -> list[DenseHit]:
        self.areas.append(area)
        return [] if area == "gd" else [DenseHit("t-s1", 0.9, 1)]


def test_retrieval_uses_search_query_and_also_searches_all_areas() -> None:
    embedder, qdrant = RecordingEmbedder(), AreaQdrant()
    retriever = Retriever(BM25Index.build(CHUNKS), qdrant, embedder)  # type: ignore[arg-type]
    norm = NormalizeOutput(
        standard_bangla="আমি কি আলফা পাব?", search_query="আলফা পাওয়ার যোগ্যতা ও শর্ত", area="gd", in_scope=True
    )
    llm = FakeLLM(norm, AnswerOutput(answer="আলফা নিয়ম [C1]", used_chunk_ids=["C1"], found=True))
    resp = asyncio.run(Orchestrator(retriever, llm, MemoryCache()).run(ChatRequest(message="ami ki alfa pabo?")))  # type: ignore[arg-type]
    assert embedder.queries == ["আলফা পাওয়ার যোগ্যতা ও শর্ত"] * 2  # area search + all-areas search
    assert qdrant.areas == ["gd", None]
    assert resp.status == "answered"  # found through the all-areas search despite the wrong area guess
    assert len(llm.calls) == 2


def test_user_chosen_area_is_not_widened() -> None:
    qdrant = AreaQdrant()
    retriever = Retriever(BM25Index.build(CHUNKS), qdrant, FakeEmbedder())  # type: ignore[arg-type]
    llm = FakeLLM(IN_SCOPE, AnswerOutput(answer="আলফা [C1]", used_chunk_ids=["C1"], found=True))
    asyncio.run(Orchestrator(retriever, llm, MemoryCache()).run(ChatRequest(message="আলফা?", area="labour")))  # type: ignore[arg-type]
    assert qdrant.areas == ["labour"]


def test_merge_results_fuses_and_prefers_area_on_ties() -> None:
    from app.services.fusion_service import FusedCandidate
    from app.services.retrieval_service import RetrievalResult, merge_results

    def result(ids: list[str]) -> RetrievalResult:
        return RetrievalResult("q", None, [FusedCandidate(i, 0.0) for i in ids], {})

    merged = merge_results(result(["a", "b"]), result(["c", "a"]), top_n=3)
    assert [c.chunk_id for c in merged.candidates] == [
        "a",
        "c",
        "b",
    ]  # a is in both lists; c (1st in wide) outranks b (2nd in area)


def test_refusals_are_not_cached() -> None:
    cache = MemoryCache()
    llm = FakeLLM(IN_SCOPE, AnswerOutput(answer="", used_chunk_ids=[], found=False))
    orch = make(llm, cache=cache)
    assert ask(orch).status == "refused"
    second = ask(orch)
    assert second.status == "refused" and not second.cached
    assert len(llm.calls) == 4  # both runs went through the pipeline again


def test_round_bracket_labels_become_markers() -> None:
    labelled = {"C1": CHUNKS[0], "C2": CHUNKS[1]}
    out = AnswerOutput(answer="এক (C1) দুই (C1, C2)।", used_chunk_ids=["C1", "C2"], found=True)
    v = validate_answer(out, labelled)
    assert v.answer == "এক [১] দুই [১][২]।"
    assert "C1" not in v.answer and v.status == "answered"


def test_answer_without_inline_markers_gets_them_at_the_end() -> None:
    labelled = {"C1": CHUNKS[0], "C2": CHUNKS[1]}
    v = validate_answer(AnswerOutput(answer="উত্তর।", used_chunk_ids=["C2", "C1"], found=True), labelled)
    assert v.answer == "উত্তর। [১][২]"
    assert [c.marker for c in v.citations] == [1, 2] and v.used_chunk_ids == ["t-s2", "t-s1"]


def test_cache_key_changes_with_pipeline_version(monkeypatch) -> None:
    from app.services import answer_cache

    before = cache_key("প্রশ্ন", None, "m", "raw")
    assert before == cache_key("প্রশ্ন", None, "m", "raw")
    monkeypatch.setattr(answer_cache, "PIPELINE_VERSION", "next")
    answer_cache.pipeline_fingerprint.cache_clear()
    try:
        assert cache_key("প্রশ্ন", None, "m", "raw") != before
    finally:
        answer_cache.pipeline_fingerprint.cache_clear()


def test_inline_list_number_after_marker_is_not_a_claimed_number() -> None:
    labelled = {"C1": CHUNKS[0]}
    out = AnswerOutput(answer="১. প্রথম ধাপ। [C1] ২. দ্বিতীয় ধাপ। [C1]", used_chunk_ids=["C1"], found=True)
    v = validate_answer(out, labelled)
    assert v.status == "answered" and not v.warnings


def test_extra_queries_are_searched_across_all_areas_with_two_llm_calls() -> None:
    embedder, qdrant = RecordingEmbedder(), AreaQdrant()
    retriever = Retriever(BM25Index.build(CHUNKS), qdrant, embedder)  # type: ignore[arg-type]
    norm = NormalizeOutput(
        standard_bangla="আলফা এবং বিটা দুই সমস্যা, এখন আমি কী করতে পারি?",
        search_query="আলফা নিয়ম",
        extra_queries=["বিটা নিয়ম", "আলফা নিয়ম", "গামা শব্দ", "ডেল্টা"],  # duplicate of search_query + one too many
        area="labour",
        in_scope=True,
    )
    llm = FakeLLM(norm, AnswerOutput(answer="আলফা [C1]", used_chunk_ids=["C1"], found=True))
    resp = asyncio.run(Orchestrator(retriever, llm, MemoryCache()).run(ChatRequest(message="আলফা বিটা", debug=True)))  # type: ignore[arg-type]
    assert embedder.queries == ["আলফা নিয়ম", "আলফা নিয়ম", "বিটা নিয়ম", "গামা শব্দ"]  # max 2 extras, no repeat
    assert qdrant.areas == ["labour", None, None, None]
    assert len(llm.calls) == 2
    assert resp.status == "answered"
