"""Web fallback (Tavily) with the network mocked. All text is synthetic placeholder text."""

import asyncio
import json

import httpx
import pytest

from app.core.config import settings
from app.schemas.chat import ChatRequest
from app.schemas.llm import AnswerOutput, NormalizeOutput
from app.services.answer_cache import MemoryCache
from app.services.orchestrator import WEB_WARNING, Orchestrator
from app.services.web_search import WebPassageSource, WebSearchClient, is_allowed
from tests.unit.test_orchestrator import CHUNKS, FakeEmbedder, FakeLLM, FakeQdrant

LONG = "নমুনা সরকারি ওয়েবসাইটের লেখা যেখানে পরীক্ষার জন্য যথেষ্ট শব্দ আছে এবং আরও কিছু বাক্য রয়েছে। " * 2


def _client(handler) -> WebSearchClient:  # noqa: ANN001
    return WebSearchClient("test-key", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), retries=1)


def test_is_allowed_matches_host_and_subdomains_only() -> None:
    domains = ["land.gov.bd"]
    assert is_allowed("https://land.gov.bd/x", domains)
    assert is_allowed("https://mutation.land.gov.bd/x", domains)
    assert not is_allowed("https://teachers.gov.bd/blog", domains)
    assert not is_allowed("https://land.gov.bd.evil.example/x", domains)


def test_search_keeps_allowed_results_with_enough_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "web_allowed_domains", "land.gov.bd")
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json={"results": [
            {"url": "https://land.gov.bd/page", "title": "নমুনা পাতা", "content": LONG},
            {"url": "https://teachers.gov.bd/blog/1", "title": "ব্লগ", "content": LONG},
            {"url": "https://land.gov.bd/short", "title": "ছোট", "content": "খুব ছোট"},
        ]})  # fmt: skip

    passages = asyncio.run(_client(handler).search("নমুনা প্রশ্ন"))
    assert [p.source_url for p in passages] == ["https://land.gov.bd/page"]
    assert passages[0].kind == "web" and passages[0].citation == "নমুনা পাতা (land.gov.bd)"
    assert seen["body"]["include_domains"] == ["land.gov.bd"] and seen["auth"] == "Bearer test-key"


def test_search_retries_rate_limit_then_gives_up_quietly(monkeypatch: pytest.MonkeyPatch) -> None:
    real_sleep = asyncio.sleep
    monkeypatch.setattr("app.services.web_search.asyncio.sleep", lambda s: real_sleep(0))
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={})

    assert asyncio.run(_client(handler).search("প্রশ্ন")) == []  # never raises into the answer pipeline
    assert calls["n"] == 2  # first try + 1 retry


class FakeWeb:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str) -> list[WebPassageSource]:
        self.queries.append(query)
        return [WebPassageSource(id="web:1", title="নমুনা পাতা", citation="নমুনা পাতা (land.gov.bd)", text=LONG,
                                 source_url="https://land.gov.bd/page")]  # fmt: skip


def _orch(score: float, answer: AnswerOutput, web: FakeWeb) -> tuple[Orchestrator, FakeLLM]:
    from app.repositories.bm25_repository import BM25Index
    from app.services.retrieval_service import Retriever

    norm = NormalizeOutput(standard_bangla="নমুনা প্রশ্ন?", search_query="নমুনা খোঁজ", area="land", in_scope=True)
    llm = FakeLLM(norm, answer)
    retriever = Retriever(BM25Index.build(CHUNKS), FakeQdrant(score), FakeEmbedder())  # type: ignore[arg-type]
    return Orchestrator(retriever, llm, MemoryCache(), web=web), llm  # type: ignore[arg-type]


def test_weak_retrieval_uses_web_and_labels_it() -> None:
    web = FakeWeb()
    orch, llm = _orch(0.5, AnswerOutput(answer="নমুনা উত্তর [W1]", used_chunk_ids=["W1"], found=True), web)
    resp = asyncio.run(orch.run(ChatRequest(message="নমুনা প্রশ্ন?")))
    assert web.queries == ["নমুনা খোঁজ"]  # Call 1's search_query, not the raw message
    assert resp.status == "answered" and resp.citations[0].kind == "web"
    assert resp.citations[0].source_url == "https://land.gov.bd/page"
    assert WEB_WARNING in resp.warnings
    assert len(llm.calls) == 2  # still two LLM calls


def test_strong_retrieval_does_not_search_the_web() -> None:
    web = FakeWeb()
    orch, _ = _orch(0.95, AnswerOutput(answer="আলফা [C1]", used_chunk_ids=["C1"], found=True), web)
    resp = asyncio.run(orch.run(ChatRequest(message="নমুনা প্রশ্ন?")))
    assert web.queries == [] and resp.citations[0].kind == "official" and WEB_WARNING not in resp.warnings


def test_web_off_keeps_old_refusal() -> None:
    from app.core.constants import REFUSAL_TEXT

    orch, _ = _orch(0.5, AnswerOutput(answer="", used_chunk_ids=[], found=False), FakeWeb())
    orch.web = None
    resp = asyncio.run(orch.run(ChatRequest(message="নমুনা প্রশ্ন?")))
    assert resp.status == "refused" and resp.answer == REFUSAL_TEXT
