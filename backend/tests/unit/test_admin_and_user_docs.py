"""Admin knowledge management and personal documents. External services are faked; inputs are synthetic."""

import asyncio
from pathlib import Path
from typing import Any

import numpy as np
import pymupdf
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import settings
from app.ingestion import source_registry
from app.main import app
from app.models.llm_client import LLMResult
from app.repositories.bm25_repository import BM25Index
from app.schemas.chat import ChatRequest
from app.schemas.ingestion import ChunkRecord
from app.schemas.llm import AnswerOutput, NormalizeOutput
from app.services import knowledge_admin as ka
from app.services.answer_cache import MemoryCache
from app.services.orchestrator import Orchestrator
from app.services.retrieval_service import Retriever
from app.services.user_docs import UserDocExpired, UserDocStore, split_passages


def _chunk(cid: str, doc: str, text: str) -> ChunkRecord:
    return ChunkRecord(
        id=cid, document_id=doc, area="labour", act="পরীক্ষা আইন", chapter=None, section="১", title="শিরোনাম",
        citation="পরীক্ষা আইন, ধারা ১", part=None, text=text, normalized_text=text, token_count=5, source_url=None,
    )  # fmt: skip


def _pdf_bytes(text: str = "Synthetic placeholder page one with enough characters for the parser.") -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()


class FakeQdrant:
    instances: list["FakeQdrant"] = []

    def __init__(self, *a: Any, **k: Any) -> None:
        self.upserted: list[str] = []
        self.deleted_docs: list[str] = []
        self.client = self
        self.collection = "test"
        FakeQdrant.instances.append(self)

    async def ensure_collection(self, dim: int) -> None: ...
    async def delete_document(self, document_id: str) -> None:
        self.deleted_docs.append(document_id)

    async def create_payload_index(self, *a: Any, **k: Any) -> None: ...
    async def upsert(self, ids, vectors, payloads) -> None:  # noqa: ANN001
        self.upserted += list(ids)

    async def count(self) -> int:
        return len(self.upserted)

    async def search(self, vector, top_k, area=None):  # noqa: ANN001
        return []


class FakeEmbedder:
    device = "cpu"

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return np.zeros((len(texts), 4), dtype=np.float32)

    def embed_query(self, text: str) -> list[float]:
        return [0.0] * 4

    def unload(self) -> None: ...


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect every path and service the admin pipeline touches."""
    retriever = Retriever(BM25Index.build([_chunk("base-s1", "base", "আলফা বিটা")]), FakeQdrant(), FakeEmbedder())  # type: ignore[arg-type]
    monkeypatch.setattr(ka, "get_retriever", lambda: retriever)
    monkeypatch.setattr(ka, "QdrantRepository", FakeQdrant)
    monkeypatch.setattr(ka, "get_embedding_client", lambda: FakeEmbedder())
    monkeypatch.setattr(ka, "model_token_counter", lambda name: lambda t: len(t.split()))
    monkeypatch.setattr(ka, "PROCESSED", tmp_path / "processed")
    monkeypatch.setattr(ka, "UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(source_registry, "REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(source_registry, "SOURCES_LOG", tmp_path / "sources_log.csv")
    monkeypatch.setattr(source_registry, "ORIGINALS_DIR", tmp_path / "originals")
    monkeypatch.setattr(settings, "bm25_path", tmp_path / "bm25.pkl")
    monkeypatch.setattr(ka, "get_answer_cache", lambda: MemoryCache())
    monkeypatch.setattr("app.ingestion.indexer.document_specs", lambda: source_registry.load_registry())
    (tmp_path / "processed").mkdir()
    FakeQdrant.instances.clear()
    return retriever, tmp_path


# ---------------------------------------------------------------- admin auth
def test_admin_disabled_without_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "admin_token", None)
    assert TestClient(app).get("/api/v1/admin/check").status_code == 503


def test_admin_requires_correct_token(monkeypatch) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "admin_token", SecretStr("right-token"))
    client = TestClient(app)
    assert client.get("/api/v1/admin/check").status_code == 401
    assert client.get("/api/v1/admin/check", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/v1/admin/check", headers={"Authorization": "Bearer right-token"}).status_code == 200


# ---------------------------------------------------------------- admin upload / delete
async def _wait(job: ka.Job) -> ka.Job:
    for _ in range(200):
        if job.status in ("done", "failed"):
            return job
        await asyncio.sleep(0.02)
    raise AssertionError(f"job stuck: {job.steps}")


async def test_upload_indexes_incrementally_then_delete_removes(sandbox) -> None:
    retriever, tmp = sandbox
    job = ka.start_upload(
        _pdf_bytes(), "notice.pdf", "application/pdf", area="gd", title="পরীক্ষা নোটিশ", issuer="পরীক্ষা অফিস",
        source_url=None, document_id="gd-test-notice", parser="auto",
    )  # fmt: skip
    job = await _wait(job)
    assert job.status == "done", job.steps
    assert job.sections == 1 and job.chunks == 1
    # live index swapped in place: old document kept, new one searchable
    ids = set(retriever.chunks)
    assert "base-s1" in ids and "gd-test-notice-p1" in ids
    assert (tmp / "processed" / "gd-test-notice.jsonl").exists()
    assert "gd-test-notice" in source_registry.load_registry()
    assert [f.name for f in (tmp / "originals" / "gd").glob("*.pdf")] == ["notice.pdf"]  # original name kept
    assert not list((tmp / "uploads").glob("*"))  # temp upload removed
    assert FakeQdrant.instances[-1].upserted == ["gd-test-notice-p1"]  # only the new document embedded

    total = await ka.delete_document("gd-test-notice")
    assert total == 1 and set(retriever.chunks) == {"base-s1"}
    assert not (tmp / "processed" / "gd-test-notice.jsonl").exists()
    assert "gd-test-notice" not in source_registry.load_registry()


async def test_upload_rejects_unsupported_and_builtin(sandbox) -> None:
    with pytest.raises(ka.UnsupportedFile):
        ka.start_upload(b"x", "a.docx", "application/msword", area="gd", title="t", issuer="", source_url=None,
                        document_id=None, parser="auto")  # fmt: skip
    with pytest.raises(ka.UnsupportedFile):
        ka.start_upload(_pdf_bytes(), "a.pdf", "application/pdf", area="labour", title="t", issuer="",
                        source_url=None, document_id="labour-act-2006", parser="auto")  # fmt: skip
    with pytest.raises(ka.UnsupportedFile):
        await ka.delete_document("labour-act-2006")


# ---------------------------------------------------------------- personal documents
def test_split_and_select_passages() -> None:
    store = UserDocStore()
    pages = [(1, "আলফা শব্দ " * 120), (2, "জমির দলিল নম্বর ৫৫৫ এবং মালিকের নাম পরীক্ষা")]
    doc = store.add("deed.pdf", pages, ["pymupdf"], False)
    assert doc.pages == 2 and len(doc.passages) >= 2
    chosen = doc.select("দলিল নম্বর কত?", k=1)
    assert chosen[0].page == 2
    assert split_passages([(1, "")]) == []


def test_user_doc_expiry(monkeypatch) -> None:
    store = UserDocStore()
    monkeypatch.setattr(settings, "user_doc_ttl_minutes", -1)
    doc = store.add("x.pdf", [(1, "লেখা")], [], False)
    with pytest.raises(UserDocExpired):
        store.get(doc.id)


def test_user_doc_upload_endpoint_text_pdf() -> None:
    client = TestClient(app)
    resp = client.post("/api/v1/user-docs", files={"file": ("letter.pdf", _pdf_bytes(), "application/pdf")})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pages"] == 1 and "Synthetic" in body["preview"] and body["methods"] == ["pymupdf"]
    assert client.get(f"/api/v1/user-docs/{body['doc_id']}").status_code == 200
    assert client.delete(f"/api/v1/user-docs/{body['doc_id']}").json() == {"deleted": True}
    assert client.get(f"/api/v1/user-docs/{body['doc_id']}").status_code == 404


def test_user_doc_upload_rejects_other_types() -> None:
    resp = TestClient(app).post("/api/v1/user-docs", files={"file": ("a.txt", b"hello", "text/plain")})
    assert resp.status_code == 422


class RecordingLLM:
    model = "fake"

    def __init__(self) -> None:
        self.answer_prompt = ""

    async def complete_json(self, system: str, user: str, schema: type[BaseModel], **kw: Any) -> LLMResult:
        if schema is NormalizeOutput:
            # off-topic by the normalizer's judgement: must NOT be refused when a personal doc is attached
            data: BaseModel = NormalizeOutput(standard_bangla="দলিলে মালিকের নাম কী?", area="unknown", in_scope=False)
        else:
            self.answer_prompt = system + "\n" + user
            data = AnswerOutput(answer="মালিকের নাম পরীক্ষা [U1]।", used_chunk_ids=["U1"], found=True)
        return LLMResult(data=data, model="fake", latency_ms=1, prompt_tokens=1, completion_tokens=1)


def test_chat_with_personal_document_is_private_and_cites_user_doc() -> None:
    store = UserDocStore()
    doc = store.add("deed.pdf", [(1, "দলিল: মালিকের নাম পরীক্ষা, দাগ নম্বর ১২")], ["tesseract"], False)
    retriever = Retriever(BM25Index.build([_chunk("base-s1", "base", "আলফা বিটা")]), FakeQdrant(), FakeEmbedder())  # type: ignore[arg-type]
    cache = MemoryCache()
    llm = RecordingLLM()
    orch = Orchestrator(retriever, llm, cache, user_docs=store)  # type: ignore[arg-type]
    resp = asyncio.run(orch.run(ChatRequest(message="আমার দলিলে মালিকের নাম কী?", user_doc_id=doc.id)))
    assert resp.status == "answered"
    assert resp.answer == "মালিকের নাম পরীক্ষা [১]।"
    assert resp.citations[0].kind == "user" and resp.citations[0].source_url is None
    assert "<user_document>" in llm.answer_prompt and "[U1]" in llm.answer_prompt
    assert cache._data == {}  # nothing cached for private questions


def test_chat_with_expired_document_is_404() -> None:
    from app.api import dependencies

    store = UserDocStore()
    retriever = Retriever(BM25Index.build([_chunk("base-s1", "base", "আলফা")]), FakeQdrant(), FakeEmbedder())  # type: ignore[arg-type]
    orch = Orchestrator(retriever, RecordingLLM(), MemoryCache(), user_docs=store)  # type: ignore[arg-type]
    app.dependency_overrides[dependencies.orchestrator_dep] = lambda: orch
    try:
        resp = TestClient(app).post("/api/v1/chat", json={"message": "প্রশ্ন আছে", "user_doc_id": "gone"})
        assert resp.status_code == 404 and resp.json()["detail"]["code"] == "user_doc_expired"
    finally:
        app.dependency_overrides.clear()
