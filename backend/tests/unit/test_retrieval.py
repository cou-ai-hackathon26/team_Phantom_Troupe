import asyncio
from dataclasses import dataclass

from app.evaluation.retrieval_metrics import hit_at_k, recall_at_k, reciprocal_rank, section_level
from app.repositories.bm25_repository import BM25Index
from app.repositories.qdrant_repository import DenseHit
from app.schemas.ingestion import ChunkRecord
from app.services.fusion_service import reciprocal_rank_fusion
from app.services.retrieval_service import Retriever, section_refs


@dataclass
class Hit:
    chunk_id: str
    score: float
    rank: int


def test_rrf_scores_and_order() -> None:
    dense = [Hit("a", 0.9, 1), Hit("b", 0.8, 2)]
    sparse = [Hit("b", 12.0, 1), Hit("c", 5.0, 2)]
    fused = reciprocal_rank_fusion(dense, sparse, k=60, top_n=5)
    assert [c.chunk_id for c in fused] == ["b", "a", "c"]
    b = fused[0]
    assert abs(b.fused_score - (1 / 62 + 1 / 61)) < 1e-12
    assert (b.dense_rank, b.bm25_rank, b.dense_score, b.bm25_score) == (2, 1, 0.8, 12.0)


def test_rrf_top_n() -> None:
    dense = [Hit(str(i), 1.0, i) for i in range(1, 20)]
    assert len(reciprocal_rank_fusion(dense, [], top_n=5)) == 5


def test_section_refs_bangla_ascii_and_suffix() -> None:
    assert section_refs("ধারা ১২৩ অনুযায়ী") == ["123"]
    assert section_refs("Section 18 of labour act") == ["18"]
    assert section_refs("৩ক ধারায় কী আছে") == ["3ক"]
    assert section_refs("ধারা ৪ ও ধারা 20") == ["4", "20"]
    assert section_refs("বেতন কবে দিবে") == []


def test_section_refs_constitution_articles() -> None:
    assert section_refs("অনুচ্ছেদ ২৭ কী বলে") == ["27"]
    assert section_refs("সংবিধানের ৭০ অনুচ্ছেদ") == ["70"]
    assert section_refs("Article 102 of the constitution") == ["102"]


def test_article_reference_prefers_article_chunks() -> None:
    article = _chunk("c27", "২৭", "আলফা").model_copy(
        update={"document_id": "const", "act": "পরীক্ষা সংবিধান", "citation": "পরীক্ষা সংবিধান, অনুচ্ছেদ ২৭"}
    )
    section = _chunk("s27", "২৭", "আলফা").model_copy(update={"document_id": "other"})
    r = Retriever(BM25Index.build([section, article]), FakeQdrant([]), FakeEmbedder())  # type: ignore[arg-type]
    assert r.exact_section_ids("অনুচ্ছেদ ২৭", area=None) == ["c27"]
    assert r.exact_section_ids("ধারা ২৭", area=None, hint_ids=["s27"]) == ["s27"]


def _chunk(cid: str, section: str, text: str, area: str = "labour", part: int | None = None) -> ChunkRecord:
    return ChunkRecord(
        id=cid,
        document_id="t",
        area=area,  # type: ignore[arg-type]
        act="পরীক্ষা আইন",
        chapter=None,
        section=section,
        title="শিরোনাম",
        citation=f"পরীক্ষা আইন, ধারা {section}",
        part=part,
        text=text,
        normalized_text=text,
        token_count=1,
        source_url=None,
    )


class FakeQdrant:
    def __init__(self, hits: list[DenseHit]) -> None:
        self.hits = hits

    async def search(self, vector, top_k, area=None):  # noqa: ANN001
        return self.hits[:top_k]


class FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [0.0]


def _retriever(dense_hits: list[DenseHit] | None = None) -> Retriever:
    chunks = [
        _chunk("s18", "১৮", "আলফা বিটা শব্দ"),
        _chunk("s12", "১২", "গামা ডেল্টা শব্দ"),
        _chunk("s2-p1", "২", "এপসাইলন শব্দ", part=1),
        _chunk("s2-p2", "২", "জেটা শব্দ", part=2),
        _chunk("land1", "১৮", "আলফা", area="land"),
    ]
    return Retriever(BM25Index.build(chunks), FakeQdrant(dense_hits or []), FakeEmbedder())  # type: ignore[arg-type]


def test_exact_section_reference_is_hit_first() -> None:
    r = _retriever()
    hits = r.sparse("ধারা ১৮ কী বলে", area="labour", top_k=5)
    assert hits[0].chunk_id == "s18"
    assert [h.rank for h in hits] == list(range(1, len(hits) + 1))


def test_exact_section_reference_with_ascii_digits_keeps_part_order() -> None:
    hits = _retriever().sparse("section 2", area=None, top_k=5)
    assert [h.chunk_id for h in hits[:2]] == ["s2-p1", "s2-p2"]


def test_hybrid_retrieve_combines_and_reports_best_dense() -> None:
    r = _retriever([DenseHit("s12", 0.87, 1), DenseHit("s18", 0.80, 2)])
    result = asyncio.run(r.retrieve("আলফা", area="labour"))
    ids = [c.chunk_id for c in result.candidates]
    assert ids[0] == "s18"  # dense rank 2 + bm25 rank 1 beats dense rank 1 alone
    assert result.best_dense_score == 0.87
    assert result.bm25_hit_in_top(3)


def test_metrics() -> None:
    ranked = ["x", "a", "y", "b"]
    assert recall_at_k(ranked, {"a", "b"}, 2) == 0.5
    assert hit_at_k(ranked, {"b"}, 3) == 0.0
    assert reciprocal_rank(ranked, {"a"}) == 0.5
    assert section_level(["d-s2-p1", "d-s2-p3", "d-s4", "d-s3a"]) == ["d-s2", "d-s4", "d-s3a"]


def test_exact_section_wins_fusion_over_dense_neighbour() -> None:
    r = _retriever([DenseHit("s12", 0.80, 1), DenseHit("s18", 0.79, 4)])
    result = asyncio.run(r.retrieve("ধারা ১৮", area="labour"))
    assert result.candidates[0].chunk_id == "s18"
    assert result.candidates[0].exact_section


def test_rrf_exact_list_adds_score() -> None:
    fused = reciprocal_rank_fusion([Hit("a", 0.9, 1)], [Hit("b", 1.0, 1)], exact=["b"])
    assert fused[0].chunk_id == "b" and fused[0].exact_section


def test_answer_metrics() -> None:
    from app.evaluation.answer_metrics import includes_all, percentile, violates

    assert includes_all("মোট ৩০ দিনের মজুরি", ["30 দিনের", "মজুরি"]) == 1.0
    assert includes_all("কিছু", ["অন্য"]) == 0.0
    assert violates("ফি ৫০০ টাকা", ["500 টাকা"])
    assert percentile([1, 2, 3, 4], 0.5) == 2.5 and percentile([], 0.5) is None


def test_eval_latest_route(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.api.routes import evaluation
    from app.main import app

    monkeypatch.setattr(evaluation, "RESULTS", tmp_path / "missing.json")
    assert TestClient(app).get("/api/v1/eval/latest").status_code == 404
    path = tmp_path / "results.json"
    path.write_text('{"model": "m", "summary": {}, "details": [1]}', encoding="utf-8")
    monkeypatch.setattr(evaluation, "RESULTS", path)
    body = TestClient(app).get("/api/v1/eval/latest").json()
    assert body["model"] == "m" and "details" not in body


# ---- scope rules (plan 12.1, 12.3, 12.4). Synthetic placeholder text only.


def _doc_chunk(cid: str, doc: str, act: str, text: str, area: str = "labour", section: str = "১") -> ChunkRecord:
    return _chunk(cid, section, text, area=area).model_copy(update={"document_id": doc, "act": act, "title": cid})


def _cands(*ids: str):  # noqa: ANN202
    from app.services.fusion_service import FusedCandidate

    return [FusedCandidate(chunk_id=i, fused_score=1.0 / n) for n, i in enumerate(ids, start=1)]


def test_document_programmes_title_wins_then_majority_of_mentions() -> None:
    from app.services.retrieval_service import document_programmes

    chunks = {
        c.id: c
        for c in [
            _doc_chunk("t1", "titled", "বয়স্ক ভাতা নির্দেশিকা", "বিধবা বিধবা বিধবা বিধবা বিধবা বিধবা", "allowance"),
            _doc_chunk("n1", "noisy", "গণপ্রজাতন্ত্রী", "বিধবা " * 6 + "বয়স্ক", "allowance"),
            _doc_chunk("m1", "mixed", "গণপ্রজাতন্ত্রী", "বিধবা " * 3 + "প্রতিবন্ধী " * 3, "allowance"),
            _doc_chunk("f1", "few", "গণপ্রজাতন্ত্রী", "প্রতিবন্ধী", "allowance"),
        ]
    }
    assert document_programmes(chunks) == {"titled": "old_age", "noisy": "widow"}


def test_query_naming_one_programme_drops_other_programme_documents() -> None:
    from app.services.retrieval_service import diversify

    chunks = {
        "w": _doc_chunk("w", "widow-doc", "অ", "ক", "allowance"),
        "o": _doc_chunk("o", "old-doc", "আ", "খ", "allowance"),
        "g": _doc_chunk("g", "general-doc", "ই", "গ", "allowance"),
    }
    progs = {"widow-doc": "widow", "old-doc": "old_age"}
    picked = diversify(_cands("w", "o", "g"), chunks, 5, query="বয়স্ক ভাতার যোগ্যতা", programmes=progs)
    assert [c.chunk_id for c in picked] == ["o", "g"]
    both = diversify(_cands("w", "o"), chunks, 5, query="বয়স্ক ও বিধবা ভাতা", programmes=progs)
    assert [c.chunk_id for c in both] == ["w", "o"]  # two programmes named: no filter


def test_epz_act_ranks_after_general_law_unless_named() -> None:
    from app.services.retrieval_service import diversify

    chunks = {
        "epz": _doc_chunk("epz", "epz", "বাংলাদেশ ইপিজেড শ্রম আইন", "ক"),
        "gen": _doc_chunk("gen", "gen", "বাংলাদেশ শ্রম আইন", "খ"),
    }
    assert [c.chunk_id for c in diversify(_cands("epz", "gen"), chunks, 5, query="ছাঁটাই")] == ["gen", "epz"]
    named = diversify(_cands("epz", "gen"), chunks, 5, query="ইপিজেড শ্রমিকের ছাঁটাই")
    assert [c.chunk_id for c in named] == ["epz", "gen"]


def test_bare_section_goes_to_primary_act_not_an_amendment_in_the_hits() -> None:
    main = _doc_chunk("main19", "labour-act-2006", "বাংলাদেশ শ্রম আইন, ২০০৬", "ক", section="১৯")
    amend = _doc_chunk("amend19", "amend", "বাংলাদেশ শ্রম (সংশোধন) আইন, ২০২৬", "খ", section="১৯")
    other = _doc_chunk("svc19", "svc", "সরকারি চাকরি আইন, ২০১৮", "গ", area="general", section="১৯")
    r = Retriever(BM25Index.build([main, amend, other]), FakeQdrant([]), FakeEmbedder())  # type: ignore[arg-type]
    assert r.exact_section_ids("শ্রম আইনের ধারা ১৯", area="labour", hint_ids=["amend19"]) == ["main19"]
    assert r.exact_section_ids("শ্রম আইনের ধারা ১৯", area=None, hint_ids=["amend19", "svc19"]) == ["main19"]
    assert r.exact_section_ids("শ্রম সংশোধন আইন ২০২৬ ধারা ১৯", area=None) == ["amend19"]
    assert r.exact_section_ids("চাকরি আইন ধারা ১৯", area=None, hint_ids=["amend19", "svc19"]) == ["svc19"]


def test_land_acquisition_rules_rank_last_unless_asked_but_tenancy_act_does_not() -> None:
    from app.services.retrieval_service import special_scope

    assert special_scope("স্থাবর সম্পত্তি অধিগ্রহণ ও হুকুমদখল বিধিমালা, ২০২৬", "নামজারি করতে কী কাগজ লাগে")
    assert special_scope("পদ্মা বহুমুখী সেতু প্রকল্প (ভূমি অধিগ্রহণ) আইন, ২০০৯", "নামজারি")
    assert not special_scope("স্থাবর সম্পত্তি অধিগ্রহণ ও হুকুমদখল আইন, ২০১৭", "জমি অধিগ্রহণের ক্ষতিপূরণ")
    assert not special_scope("রাষ্ট্রীয় অধিগ্রহণ প্রজাস্বত্ব আইন, ১৯৫০", "নামজারি করতে কী কাগজ লাগে")


def test_section_title_contained_in_query_is_boosted() -> None:
    long_sec = _doc_chunk("long", "d", "পরীক্ষা আইন", "ক", section="৩০").model_copy(update={"title": "চূড়ান্ত পাওনা"})
    titled = _doc_chunk("titled", "d", "পরীক্ষা আইন", "খ", section="২০").model_copy(update={"title": "ছাঁটাই"})
    r = Retriever(BM25Index.build([long_sec, titled]), FakeQdrant([]), FakeEmbedder())  # type: ignore[arg-type]
    assert r.title_match_ids("ছাঁটাই হলে শ্রমিক কী পায়", ["long", "titled"]) == ["titled"]
    assert r.title_match_ids("মজুরি কত", ["long", "titled"]) == []
