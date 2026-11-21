"""Pagination helpers and the paginated public document list. Fixtures are synthetic placeholders."""

from fastapi.testclient import TestClient

from app.api.dependencies import retriever_dep
from app.main import app
from app.repositories.bm25_repository import BM25Index
from app.schemas.ingestion import ChunkRecord
from app.services.pagination import IndexCache, matches, paginate, search_key
from app.services.retrieval_service import Retriever


def test_paginate_slices_and_clamps() -> None:
    page = paginate(list(range(45)), page=2, page_size=20)
    assert (page.items[0], len(page.items), page.total, page.pages) == (20, 20, 45, 3)
    assert paginate(list(range(45)), page=99, page_size=20).items == list(range(40, 45))
    empty = paginate([], page=3, page_size=20)
    assert (empty.items, empty.page, empty.pages) == ([], 1, 1)
    assert paginate(list(range(500)), page=1, page_size=10_000).page_size == 100  # capped


def test_matches_all_words_case_and_digits() -> None:
    key = search_key("Placeholder Act ২০০৬", "Issuer")
    assert matches("placeholder 2006", key)  # ASCII digits match Bangla digits
    assert matches(None, key) and matches("  ", key)
    assert not matches("placeholder missing", key)


def test_index_cache_rebuilds_on_new_index() -> None:
    cache: IndexCache[int] = IndexCache()
    calls: list[int] = []
    a, b = object(), object()
    assert cache.get(a, lambda: calls.append(1) or 1) == 1
    assert cache.get(a, lambda: calls.append(2) or 2) == 1  # same index: cached
    assert cache.get(b, lambda: calls.append(3) or 3) == 3
    assert calls == [1, 3]


def _chunk(cid: str, doc: str, area: str, act: str) -> ChunkRecord:
    return ChunkRecord(
        id=cid, document_id=doc, area=area, act=act, chapter=None, section="১", title="শিরোনাম",  # type: ignore[arg-type]
        citation=f"{act}, ধারা ১", part=None, text="আলফা", normalized_text="আলফা", token_count=1, source_url=None,
    )  # fmt: skip


class _NoQdrant:
    async def search(self, vector, top_k, area=None):  # noqa: ANN001
        return []


def test_sources_endpoint_paginates_filters_and_counts() -> None:
    chunks = [_chunk(f"l{i}", f"land-{i:02d}", "land", f"Placeholder land doc {i:02d}") for i in range(30)]
    chunks += [_chunk(f"g{i}", f"gd-{i}", "gd", f"Placeholder gd doc {i}") for i in range(5)]
    retriever = Retriever(BM25Index.build(chunks), _NoQdrant(), None)  # type: ignore[arg-type]
    app.dependency_overrides[retriever_dep] = lambda: retriever
    try:
        client = TestClient(app)
        body = client.get("/api/v1/sources", params={"page_size": 20}).json()
        assert (body["total"], body["pages"], len(body["items"])) == (35, 2, 20)
        assert body["counts"] == {"all": 35, "land": 30, "gd": 5}
        gd = client.get("/api/v1/sources", params={"area": "gd"}).json()
        assert gd["total"] == 5 and {d["area"] for d in gd["items"]} == {"gd"}
        searched = client.get("/api/v1/sources", params={"q": "land doc 07"}).json()
        assert [d["document_id"] for d in searched["items"]] == ["land-07"]
        assert searched["counts"] == {"all": 1, "land": 1}
        detail = client.get("/api/v1/sources/documents/gd-3").json()
        assert detail["document"]["document_id"] == "gd-3" and len(detail["sections"]) == 1
    finally:
        app.dependency_overrides.pop(retriever_dep, None)
