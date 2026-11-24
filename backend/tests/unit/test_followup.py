"""Follow-up conversation mode with source continuity. LLM and Qdrant mocked; fixture text is synthetic."""

import asyncio
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api import dependencies
from app.core.config import settings
from app.main import app
from app.models.llm_client import LLMRateLimited, LLMResult
from app.repositories.bm25_repository import BM25Index
from app.repositories.qdrant_repository import DenseHit
from app.schemas.chat import ChatRequest, Citation
from app.schemas.ingestion import ChunkRecord
from app.schemas.llm import AnswerOutput, NormalizeOutput
from app.services import answer_cache
from app.services.answer_cache import MemoryCache
from app.services.conversation_service import ConversationService
from app.services.conversation_store import (
    ConversationBusy,
    ConversationNotFound,
    MemoryConversationStore,
    SourceRef,
    Turn,
    new_conversation,
)
from app.services.evidence import merge_evidence, reusable_sources, source_version
from app.services.followup_resolver import PriorExchange, TurnContext, normalize_history_block, resolve_followup
from app.services.orchestrator import Orchestrator
from app.services.query_normalizer import NormalizedQuery
from app.services.retrieval_service import RetrievalResult, Retriever
from app.services.user_docs import UserDocStore


def _chunk(cid: str, text: str, area: str = "labour", act: str = "নমুনা আইন") -> ChunkRecord:
    return ChunkRecord(
        id=cid,
        document_id=f"doc-{cid}",
        area=area,  # type: ignore[arg-type]
        act=act,
        chapter=None,
        section="১",
        title=f"শিরোনাম {cid}",
        citation=f"{act}, অংশ {cid}",
        part=None,
        text=text,
        normalized_text=text,
        token_count=10,
        source_url="https://example.invalid/s",
    )


WAGE = _chunk("wage", "আলফামজুরি পরিশোধের নমুনা নিয়ম।")
COMPLAINT = _chunk("complaint", "বিটাঅভিযোগ দায়েরের নমুনা নিয়ম।")
MUTATION = _chunk("mutation", "গামানামজারি আবেদনের নমুনা নিয়ম।", area="land")
REPEALED = _chunk("old", "আলফামজুরি পুরাতন নমুনা নিয়ম।", act="পুরাতন নমুনা আইন [রহিত]")
FILLERS = [_chunk(f"f{i}", f"পূরকশব্দ{i} সাধারণ লেখা।") for i in range(10)]  # gives the IDF test realistic spread
CHUNKS = [WAGE, COMPLAINT, MUTATION, REPEALED, *FILLERS]


class NoDense:
    async def search(self, vector: Any, top_k: int, area: str | None = None) -> list[DenseHit]:
        return []  # BM25 alone decides; the score gate passes on a BM25 hit in the top 3


class FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [0.0]


class ScriptedLLM:
    """Returns the queued outputs in order and records every prompt."""

    model = "fake-model"

    def __init__(self, *outputs: BaseModel | Exception) -> None:
        self.queue = list(outputs)
        self.calls: list[tuple[str, str, str]] = []  # (purpose, system, user)

    def push(self, *outputs: BaseModel | Exception) -> None:
        self.queue.extend(outputs)

    async def complete_json(self, system: str, user: str, schema: type[BaseModel], **kw: Any) -> LLMResult:
        self.calls.append((kw.get("purpose", "?"), system, user))
        value = self.queue.pop(0)
        if isinstance(value, Exception):
            raise value
        assert isinstance(value, schema), f"expected {schema.__name__}, got {type(value).__name__}"
        return LLMResult(data=value, model=self.model, latency_ms=1, prompt_tokens=1, completion_tokens=1)

    def purposes(self) -> list[str]:
        return [p for p, _, _ in self.calls]


def make_service(llm: ScriptedLLM, chunks: list[ChunkRecord] = CHUNKS, cache: MemoryCache | None = None):
    retriever = Retriever(BM25Index.build(chunks), NoDense(), FakeEmbedder())  # type: ignore[arg-type]
    orch = Orchestrator(retriever, llm, cache or MemoryCache(), user_docs=UserDocStore())  # type: ignore[arg-type]
    store = MemoryConversationStore()
    return ConversationService(orch, store), store


def ask(service: ConversationService, message: str, conv: tuple[str, str] | None = None, **kw: Any):
    req = ChatRequest(
        message=message,
        conversation_id=conv[0] if conv else None,
        conversation_token=conv[1] if conv else None,
        debug=True,
        **kw,
    )
    return asyncio.run(service.handle(req))


def first_wage_turn(llm: ScriptedLLM, service: ConversationService):
    llm.push(
        NormalizeOutput(standard_bangla="আলফামজুরি না পেলে কী করব?", area="labour"),
        AnswerOutput(answer="নিয়ম অনুযায়ী মজুরি দিতে হবে [C1]।", used_chunk_ids=["C1"], found=True),
    )
    resp = ask(service, "আলফামজুরি দিচ্ছে না")
    assert resp.conversation_id and resp.conversation_token
    return resp, (resp.conversation_id, resp.conversation_token)


# ---------------------------------------------------------------------------- store and ownership


def test_new_conversation_is_not_stored_until_saved() -> None:
    store = MemoryConversationStore()
    conv, token = new_conversation()
    with pytest.raises(ConversationNotFound):
        asyncio.run(store.get(conv.id, token))
    asyncio.run(store.save(conv))
    assert asyncio.run(store.get(conv.id, token)) is conv


def test_wrong_token_and_unknown_id_are_indistinguishable() -> None:
    store = MemoryConversationStore()
    conv, _ = new_conversation()
    asyncio.run(store.save(conv))
    for cid, token in ((conv.id, "guessed"), (conv.id, ""), ("no-such-id", "x")):
        with pytest.raises(ConversationNotFound):
            asyncio.run(store.get(cid, token))


def test_conversation_expires(monkeypatch) -> None:
    store = MemoryConversationStore()
    conv, token = new_conversation()
    asyncio.run(store.save(conv))
    conv.expires_at = time.time() - 1
    with pytest.raises(ConversationNotFound):
        asyncio.run(store.get(conv.id, token))
    assert len(store) == 0


def test_store_evicts_least_recently_used(monkeypatch) -> None:
    monkeypatch.setattr(settings, "conversation_max_count", 2)
    store = MemoryConversationStore()
    convs = [new_conversation() for _ in range(3)]
    for conv, _ in convs:
        asyncio.run(store.save(conv))
        time.sleep(0.001)
    assert len(store) == 2
    with pytest.raises(ConversationNotFound):
        asyncio.run(store.get(convs[0][0].id, convs[0][1]))


def test_guard_rejects_a_concurrent_message() -> None:
    store = MemoryConversationStore()

    async def scenario() -> None:
        async with store.guard("c1"):
            with pytest.raises(ConversationBusy):
                async with store.guard("c1"):
                    pass
        async with store.guard("c1"):  # released after the first message
            pass

    asyncio.run(scenario())


def test_turn_numbers_increase_in_pairs() -> None:
    conv, _ = new_conversation()
    for _ in range(2):
        conv.append_exchange(
            Turn(id="u", number=0, role="user", content="q", created_at=0),
            Turn(id="a", number=0, role="assistant", content="a", created_at=0),
        )
    assert [t.number for t in conv.turns] == [1, 2, 3, 4]


# ---------------------------------------------------------------------------- Call 1 output and resolution


def test_unknown_intent_and_bad_labels_do_not_fail_call_1() -> None:
    out = NormalizeOutput.model_validate(
        {"standard_bangla": "ক", "followup_intent": "maybe", "referenced_turns": ["[t1]", 2, None]}
    )
    assert out.followup_intent is None
    assert out.referenced_turns == ["T1", "2"]
    assert NormalizeOutput.model_validate({"standard_bangla": "ক", "followup_intent": " expand "}).followup_intent == (
        "EXPAND"
    )


def _query(**kw: Any) -> NormalizedQuery:
    base: dict[str, Any] = dict(
        original="প্রশ্ন",
        standard_bangla="পূর্ণ প্রশ্ন",
        search_query="পূর্ণ প্রশ্ন",
        area="labour",
        in_scope=True,
        needs_clarification=False,
        clarification_question=None,
        llm_ok=True,
    )
    return NormalizedQuery(**(base | kw))


def _context(n: int = 2) -> TurnContext:
    return TurnContext(
        tuple(PriorExchange(f"turn-{i}", f"প্রশ্ন {i}", "উত্তর", "labour", "answered", ()) for i in range(1, n + 1))
    )


def test_resolver_validates_turn_labels_and_defaults_to_latest() -> None:
    ctx = _context()
    res = resolve_followup(_query(followup_intent="EXPAND", referenced_turns=["T1", "T9"]), ctx)
    assert res.intent == "EXPAND" and res.referenced_turn_ids == ["turn-1"] and res.reuse_previous_sources
    res = resolve_followup(_query(followup_intent="CONTINUE", referenced_turns=["T7"]), ctx)
    assert res.referenced_turn_ids == ["turn-2"]  # invented label dropped; "তাহলে" refers to the latest


def test_clarify_without_question_and_call_1_fallback_mean_fresh_retrieval() -> None:
    ctx = _context()
    res = resolve_followup(_query(followup_intent="CLARIFY"), ctx)
    assert res.intent == "NEW_TOPIC" and not res.reuse_previous_sources and res.needs_new_retrieval
    res = resolve_followup(_query(followup_intent="CONTINUE", llm_ok=False), ctx)
    assert res.intent == "NEW_TOPIC" and not res.reuse_previous_sources
    res = resolve_followup(_query(followup_intent="CLARIFY", clarification_question="কোনটি?"), ctx)
    assert res.intent == "CLARIFY" and res.clarification_question == "কোনটি?" and not res.needs_new_retrieval


def test_no_history_is_an_initial_question() -> None:
    res = resolve_followup(_query(followup_intent="EXPAND"), TurnContext())
    assert not res.is_follow_up and res.intent == "NEW_TOPIC"


def test_call_1_history_shows_questions_and_source_titles_not_answers() -> None:
    src = SourceRef(1, "official", "wage", "doc-wage", "১", "নমুনা আইন, অংশ wage", "v", "hybrid")
    ctx = TurnContext((PriorExchange("t", "আগের প্রশ্ন", "গোপন উত্তর লেখা", "labour", "answered", (src,)),))
    block = normalize_history_block(ctx)
    assert "[T1] প্রশ্ন: আগের প্রশ্ন" in block and "নমুনা আইন, অংশ wage" in block
    assert "গোপন উত্তর লেখা" not in block


# ---------------------------------------------------------------------------- evidence checks


def _ref(chunk: ChunkRecord, marker: int = 1, kind: str = "official", version: str | None = None) -> SourceRef:
    return SourceRef(
        marker, kind, chunk.id, chunk.document_id, chunk.section, chunk.citation, version or source_version(chunk), "x"
    )


def test_reuse_checks_existence_version_repeal_relevance_and_kind() -> None:
    index = BM25Index.build(CHUNKS)
    sources = [
        _ref(WAGE),
        _ref(_chunk("gone", "আলফামজুরি")),  # no longer in the index
        _ref(COMPLAINT, version="0" * 16),  # text changed since it was cited
        _ref(REPEALED),
        _ref(MUTATION),  # unrelated to the question
        SourceRef(5, "web", "web:1", None, "", "ওয়েব", None, "web"),
    ]
    report = reusable_sources(sources, index, "আলফামজুরি কোথায় পাব", fresh_ids=[], limit=3)
    assert [c.id for c in report.chunks] == ["wage"]
    assert report.dropped == {
        "gone": "missing",
        "complaint": "changed",
        "old": "repealed",
        "mutation": "not_relevant",
        "web:1": "not_official",
    }


def test_reuse_accepts_a_chunk_found_by_fresh_retrieval_and_respects_limit() -> None:
    index = BM25Index.build(CHUNKS)
    report = reusable_sources([_ref(MUTATION), _ref(WAGE)], index, "অন্য কিছু", fresh_ids=["mutation", "wage"], limit=1)
    assert [c.id for c in report.chunks] == ["mutation"] and report.dropped == {"wage": "over_limit"}


def test_merge_puts_reused_first_dedupes_and_caps() -> None:
    merged = merge_evidence([WAGE], [COMPLAINT, WAGE, MUTATION], {"complaint": "bm25", "mutation": "dense"}, limit=2)
    assert [(c.id, m) for c, m in merged] == [("wage", "reused"), ("complaint", "bm25")]


# ---------------------------------------------------------------------------- the follow-up pipeline


def test_first_question_creates_conversation_and_records_sources() -> None:
    llm = ScriptedLLM()
    service, store = make_service(llm)
    resp, (cid, token) = first_wage_turn(llm, service)
    assert resp.status == "answered" and resp.turn_id and resp.trace and resp.trace.followup_intent is None
    conv = asyncio.run(store.get(cid, token))
    user, assistant = conv.turns
    assert (user.role, user.number, user.content) == ("user", 1, "আলফামজুরি দিচ্ছে না")
    assert (assistant.id, assistant.number, assistant.status) == (resp.turn_id, 2, "answered")
    (src,) = assistant.sources
    assert (src.marker, src.chunk_id, src.document_id, src.kind) == (1, "wage", "doc-wage", "official")
    assert src.source_version == source_version(WAGE) and src.retrieval_method == "bm25" and src.rank == 1
    assert llm.purposes() == ["normalize", "answer"]


def test_expand_reuses_old_evidence_and_adds_fresh_retrieval() -> None:
    llm = ScriptedLLM()
    service, store = make_service(llm)
    _, conv = first_wage_turn(llm, service)
    llm.calls.clear()
    llm.push(
        NormalizeOutput(
            standard_bangla="আলফামজুরি না পেলে বিটাঅভিযোগ কোথায় করব?",
            area="labour",
            followup_intent="EXPAND",
            referenced_turns=["T1"],
        ),
        AnswerOutput(answer="অভিযোগ করা যায় [C2]। মজুরির নিয়ম [C1]।", used_chunk_ids=["C2", "C1"], found=True),
    )
    resp = ask(service, "তাহলে কোথায় অভিযোগ করব?", conv)

    assert llm.purposes() == ["normalize", "answer"]  # still at most 2 LLM calls
    _, call1_system, call1_user = llm.calls[0]
    assert "FOLLOW-UP MODE" in call1_system
    assert "[T1] প্রশ্ন: আলফামজুরি না পেলে কী করব?" in call1_user and "তাহলে কোথায় অভিযোগ করব?" in call1_user
    _, call2_system, call2_user = llm.calls[1]
    assert "FOLLOW-UP QUESTIONS" in call2_system
    assert "<conversation_history>" in call2_user and "নাগরিকের নতুন বার্তা: তাহলে কোথায় অভিযোগ করব?" in call2_user
    # the reused passage is reloaded from the index (its text, not the old answer) and labelled afresh
    assert "[C1] নমুনা আইন, অংশ wage" in call2_user and WAGE.text in call2_user
    assert "[C2] নমুনা আইন, অংশ complaint" in call2_user

    assert resp.trace and resp.trace.followup_intent == "EXPAND" and resp.trace.reused_chunk_ids == ["wage"]
    assert resp.normalized_question == "আলফামজুরি না পেলে বিটাঅভিযোগ কোথায় করব?"
    # current-turn citations: markers rebuilt in order of use, each mapped to its own chunk
    assert [(c.marker, c.chunk_id) for c in resp.citations] == [(1, "complaint"), (2, "wage")]
    assert resp.answer == "অভিযোগ করা যায় [১]। মজুরির নিয়ম [২]।"
    assistant = asyncio.run(store.get(*conv)).turns[-1]
    assert [(s.marker, s.chunk_id, s.retrieval_method) for s in assistant.sources] == [
        (1, "complaint", "bm25"),
        (2, "wage", "reused"),
    ]
    assert [t.number for t in asyncio.run(store.get(*conv)).turns] == [1, 2, 3, 4]


def test_continue_reuses_evidence_even_when_fresh_retrieval_finds_nothing() -> None:
    llm = ScriptedLLM()
    service, _ = make_service(llm)
    _, conv = first_wage_turn(llm, service)

    async def nothing(query: str, area: str | None = None, **kw: Any) -> RetrievalResult:
        return RetrievalResult(query=query, area=area, candidates=[], chunks=service.orchestrator.retriever.chunks)

    service.orchestrator.retriever.retrieve = nothing  # type: ignore[method-assign]
    llm.calls.clear()
    llm.push(
        NormalizeOutput(
            standard_bangla="আলফামজুরি কত দিনের মধ্যে?", area="labour", followup_intent="CONTINUE", referenced_turns=["T1"]
        ),
        AnswerOutput(answer="নিয়মে বলা আছে [C1]।", used_chunk_ids=["C1"], found=True),
    )
    resp = ask(service, "এটা কত দিনের মধ্যে?", conv)
    assert resp.status == "answered" and [c.chunk_id for c in resp.citations] == ["wage"]
    assert resp.trace and resp.trace.gate == "answered"
    assert "[C2]" not in llm.calls[1][2]  # only the verified reused passage went in


def test_new_topic_uses_no_old_sources_and_no_history_in_call_2() -> None:
    llm = ScriptedLLM()
    service, store = make_service(llm)
    _, conv = first_wage_turn(llm, service)
    llm.calls.clear()
    llm.push(
        NormalizeOutput(standard_bangla="গামানামজারি কীভাবে করব?", area="land", followup_intent="NEW_TOPIC"),
        AnswerOutput(answer="আবেদন করতে হবে [C1]।", used_chunk_ids=["C1"], found=True),
    )
    resp = ask(service, "গামানামজারি কীভাবে করব?", conv)
    call2_user = llm.calls[1][2]
    assert WAGE.text not in call2_user and "<conversation_history>" not in call2_user
    assert "FOLLOW-UP QUESTIONS" not in llm.calls[1][1]
    assert resp.trace and resp.trace.followup_intent == "NEW_TOPIC" and resp.trace.reused_chunk_ids == []
    assert [c.chunk_id for c in resp.citations] == ["mutation"]


def test_clarify_asks_instead_of_answering_and_is_saved() -> None:
    llm = ScriptedLLM()
    service, store = make_service(llm)
    _, conv = first_wage_turn(llm, service)
    llm.calls.clear()
    llm.push(
        NormalizeOutput(
            standard_bangla="ওটা কি করা যাবে?",
            area="labour",
            followup_intent="CLARIFY",
            needs_clarification=True,
            clarification_question="আপনি কোন বিষয়ের কথা বলছেন?",
        )
    )
    resp = ask(service, "ওটা কি করা যাবে?", conv)
    assert resp.status == "clarify" and resp.answer == "আপনি কোন বিষয়ের কথা বলছেন?" and resp.citations == []
    assert llm.purposes() == ["normalize"]
    assistant = asyncio.run(store.get(*conv)).turns[-1]
    assert assistant.status == "clarify" and assistant.sources == []


def test_changed_source_is_not_reused() -> None:
    llm = ScriptedLLM()
    service, _ = make_service(llm)
    _, conv = first_wage_turn(llm, service)
    # an admin edited the chunk after it was cited: same id, different text
    edited = WAGE.model_copy(update={"text": "আলফামজুরি সংশোধিত নমুনা নিয়ম।"})
    service.orchestrator.retriever.bm25.chunks["wage"] = edited
    llm.calls.clear()
    llm.push(
        NormalizeOutput(standard_bangla="আলফামজুরি আর কী?", area="labour", followup_intent="CONTINUE"),
        AnswerOutput(answer="নিয়ম [C1]।", used_chunk_ids=["C1"], found=True),
    )
    resp = ask(service, "আর কী?", conv)
    assert resp.trace and resp.trace.dropped_reuse == {"wage": "changed"} and resp.trace.reused_chunk_ids == []


def test_follow_ups_bypass_the_answer_cache() -> None:
    llm = ScriptedLLM()
    cache = MemoryCache()
    service, _ = make_service(llm, cache=cache)
    _, conv = first_wage_turn(llm, service)
    cached_before = dict(cache._data)
    assert cached_before  # the first question of a conversation is cached as before
    llm.push(
        NormalizeOutput(standard_bangla="আলফামজুরি না পেলে কী করব?", area="labour", followup_intent="CONTINUE"),
        AnswerOutput(answer="নিয়ম [C1]।", used_chunk_ids=["C1"], found=True),
    )
    resp = ask(service, "আলফামজুরি দিচ্ছে না", conv)  # same text as the cached first question
    assert not resp.cached and cache._data == cached_before


def test_failed_turn_appends_nothing_and_retry_works() -> None:
    llm = ScriptedLLM()
    service, store = make_service(llm)
    _, conv = first_wage_turn(llm, service)
    llm.push(LLMRateLimited("429"))
    with pytest.raises(LLMRateLimited):
        ask(service, "তাহলে কী করব?", conv)
    assert len(asyncio.run(store.get(*conv)).turns) == 2
    llm.push(
        NormalizeOutput(standard_bangla="আলফামজুরি না পেলে কী করব?", area="labour", followup_intent="CONTINUE"),
        AnswerOutput(answer="নিয়ম [C1]।", used_chunk_ids=["C1"], found=True),
    )
    ask(service, "তাহলে কী করব?", conv)
    assert [t.number for t in asyncio.run(store.get(*conv)).turns] == [1, 2, 3, 4]


def test_personal_document_answer_text_and_passages_are_not_kept() -> None:
    llm = ScriptedLLM()
    service, store = make_service(llm)
    doc = service.orchestrator.user_docs.add("deed.pdf", [(1, "ব্যক্তিগত নমুনা আলফামজুরি লেখা।")], ["text"], False)
    llm.push(
        NormalizeOutput(standard_bangla="আমার নথিতে আলফামজুরি কী?", area="labour"),
        AnswerOutput(answer="আপনার নথিতে লেখা আছে [U1]। নিয়ম [C1]।", used_chunk_ids=["U1", "C1"], found=True),
    )
    resp = ask(service, "আমার নথিতে কী আছে?", user_doc_id=doc.id)
    assert {c.kind for c in resp.citations} == {"user", "official"}
    assistant = asyncio.run(store.get(resp.conversation_id, resp.conversation_token)).turns[-1]
    assert assistant.private and assistant.content == ""
    assert [s.kind for s in assistant.sources] == ["official"]
    assert all("ব্যক্তিগত" not in s.citation for s in assistant.sources)


def test_source_refs_skip_user_citations() -> None:
    from app.services.conversation_service import source_refs
    from app.services.orchestrator import TurnOutcome

    citations = [
        Citation(marker=1, kind="user", chunk_id="user:x:1", act="", section="", title="", citation="", excerpt="x"),
        Citation(marker=2, chunk_id="wage", act="", section="১", title="", citation="c", excerpt="e"),
    ]
    outcome = TurnOutcome(response=None, evidence={}, resolution=None, private=True, cached=True)  # type: ignore[arg-type]
    refs = source_refs(citations, outcome, {"wage": WAGE})
    assert [(r.marker, r.chunk_id, r.retrieval_method) for r in refs] == [(2, "wage", "cache")]


def test_followup_prompts_do_not_change_the_cache_fingerprint(monkeypatch, tmp_path) -> None:
    (tmp_path / "answer_bn.md").write_text("a", encoding="utf-8")
    monkeypatch.setattr(answer_cache, "PROMPTS_DIR", tmp_path)
    answer_cache.pipeline_fingerprint.cache_clear()
    try:
        before = answer_cache.pipeline_fingerprint()
        (tmp_path / "followup_answer.md").write_text("b", encoding="utf-8")
        answer_cache.pipeline_fingerprint.cache_clear()
        assert answer_cache.pipeline_fingerprint() == before
        (tmp_path / "normalize.md").write_text("c", encoding="utf-8")
        answer_cache.pipeline_fingerprint.cache_clear()
        assert answer_cache.pipeline_fingerprint() != before
    finally:
        answer_cache.pipeline_fingerprint.cache_clear()


# ---------------------------------------------------------------------------- HTTP contract


@pytest.fixture
def api():
    llm = ScriptedLLM()
    service, _ = make_service(llm)
    app.dependency_overrides[dependencies.conversation_service_dep] = lambda: service
    yield TestClient(app), llm
    app.dependency_overrides.clear()


def test_api_returns_conversation_and_accepts_follow_up(api) -> None:
    client, llm = api
    llm.push(
        NormalizeOutput(standard_bangla="আলফামজুরি না পেলে কী করব?", area="labour"),
        AnswerOutput(answer="নিয়ম [C1]।", used_chunk_ids=["C1"], found=True),
    )
    first = client.post("/api/v1/chat", json={"message": "আলফামজুরি দিচ্ছে না"}).json()  # old client shape
    assert first["status"] == "answered" and first["conversation_id"] and first["conversation_token"]
    llm.push(
        NormalizeOutput(standard_bangla="আলফামজুরি আর কী?", area="labour", followup_intent="CONTINUE"),
        AnswerOutput(answer="নিয়ম [C1]।", used_chunk_ids=["C1"], found=True),
    )
    body = {"message": "আর কী?", "conversation_id": first["conversation_id"]}
    second = client.post("/api/v1/chat", json=body | {"conversation_token": first["conversation_token"]}).json()
    assert second["conversation_id"] == first["conversation_id"]
    assert second["conversation_token"] is None  # the secret is sent only once
    assert second["turn_id"] and second["turn_id"] != first["turn_id"]


def test_api_rejects_another_users_conversation(api) -> None:
    client, llm = api
    llm.push(
        NormalizeOutput(standard_bangla="আলফামজুরি না পেলে কী করব?", area="labour"),
        AnswerOutput(answer="নিয়ম [C1]।", used_chunk_ids=["C1"], found=True),
    )
    first = client.post("/api/v1/chat", json={"message": "আলফামজুরি দিচ্ছে না"}).json()
    for extra in ({"conversation_token": "guessed"}, {}):
        r = client.post("/api/v1/chat", json={"message": "আর কী?", "conversation_id": first["conversation_id"]} | extra)
        assert r.status_code == 404 and r.json()["detail"]["code"] == "conversation_expired"
    assert len(llm.calls) == 2  # rejected before any LLM call


def test_clarify_follow_up_is_asked_even_if_call_1_marks_it_out_of_scope() -> None:
    llm = ScriptedLLM()
    service, _ = make_service(llm)
    _, conv = first_wage_turn(llm, service)
    llm.push(
        NormalizeOutput(
            standard_bangla="ওটা কি করা যাবে?",
            area="unknown",
            in_scope=False,  # a bare reference looks out of scope on its own
            followup_intent="CLARIFY",
            needs_clarification=True,
            clarification_question="আপনি কোন বিষয়ের কথা বলছেন?",
        )
    )
    resp = ask(service, "ওটা কি করা যাবে?", conv)
    assert resp.status == "clarify" and resp.answer == "আপনি কোন বিষয়ের কথা বলছেন?"
