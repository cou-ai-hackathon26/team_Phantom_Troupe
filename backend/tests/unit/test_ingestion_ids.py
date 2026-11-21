import json
from pathlib import Path

import pytest

from app.ingestion.area_map import UnknownSource, spec_for_folder, spec_for_source_file
from app.ingestion.bdlaws_parser import section_slug, section_sort_key
from app.ingestion.jsonl_loader import read_jsonl
from app.repositories.bm25_repository import BM25Index
from app.repositories.qdrant_repository import point_id_for
from app.schemas.ingestion import ChunkRecord


def test_point_ids_are_deterministic_and_distinct() -> None:
    assert point_id_for("labour-act-2006-s2-p1") == point_id_for("labour-act-2006-s2-p1")
    assert point_id_for("labour-act-2006-s2-p1") != point_id_for("labour-act-2006-s2-p2")


def test_section_slug_and_sort() -> None:
    assert section_slug("২") == "2"
    assert section_slug("৩ক") == "3a"
    ordered = sorted(["১০", "৩ক", "প্রস্তাবনা", "২", "৩"], key=section_sort_key)
    assert ordered == ["প্রস্তাবনা", "২", "৩", "৩ক", "১০"]


def test_unknown_sources_fail_loudly() -> None:
    with pytest.raises(UnknownSource):
        spec_for_folder("Random folder")
    with pytest.raises(UnknownSource):
        spec_for_source_file("unknown.jsonl")
    with pytest.raises(UnknownSource):  # built-in PDFs now come from data/DataSet (dataset_sources.py)
        spec_for_folder("Workers — Bangladesh Labour Act 2006")


def test_read_jsonl_rejects_duplicate_ids(tmp_path: Path) -> None:
    row = {
        "id": "x-s1",
        "document_id": "x",
        "area": "land",
        "act": "পরীক্ষা",
        "section": "১",
        "title": "শিরোনাম",
        "citation": "পরীক্ষা, ধারা ১",
        "text": "শব্দ",
        "source_file": "f.pdf",
    }
    path = tmp_path / "dup.jsonl"
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n" + json.dumps(row, ensure_ascii=False) + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        read_jsonl(path)


def _chunk(cid: str, text: str, area: str = "labour") -> ChunkRecord:
    return ChunkRecord(
        id=cid,
        document_id="t",
        area=area,  # type: ignore[arg-type]
        act="পরীক্ষা আইন",
        chapter=None,
        section="১",
        title="শিরোনাম",
        citation="পরীক্ষা আইন, ধারা ১",
        part=None,
        text=text,
        normalized_text=text,
        token_count=1,
        source_url=None,
    )


def test_bm25_round_trip_and_area_filter(tmp_path: Path) -> None:
    chunks = [
        _chunk("a", "আলফা বিটা গামা"),
        _chunk("b", "ডেল্টা এপসাইলন"),
        _chunk("c", "আলফা জেটা", area="land"),
    ]
    path = tmp_path / "bm25.pkl"
    BM25Index.build(chunks).save(path)
    index = BM25Index.load(path)
    assert len(index) == 3
    assert {h.chunk_id for h in index.search("আলফা", 5)} == {"a", "c"}
    assert [h.chunk_id for h in index.search("আলফা", 5, area="land")] == ["c"]
    assert index.search("।।", 5) == []
