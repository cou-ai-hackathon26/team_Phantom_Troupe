"""DataSet ingestion: manifest, titles, dedupe, markdown + SQLite parsers, OCR filter, step registry.
All text is synthetic placeholder text."""

import asyncio
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from app.ingestion import dataset_indexer, sqlite_laws
from app.ingestion.area_map import DocumentSpec
from app.ingestion.dataset_sources import STEP_BY_NAME, STEPS, area_for_path, clean_filename, step_files
from app.ingestion.generic_parser import ocr_quality
from app.ingestion.markdown_parser import parse_markdown, to_section_records
from app.repositories.bm25_repository import BM25Index
from app.schemas.ingestion import ChunkRecord, SectionRecord
from app.services.retrieval_service import Retriever

# ---------------------------------------------------------------------------- manifest


def test_every_step_name_is_unique_and_areas_are_known() -> None:
    assert len({s.name for s in STEPS}) == len(STEPS)
    assert {s.area for s in STEPS} <= {"land", "gd", "allowance", "labour", "general"}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("03_ভূমি সংস্কার আইন, ২০২৩.pdf", "ভূমি সংস্কার আইন, ২০২৩"),
        ("05_পিতা-মাতার_ভরণ-পোষণ_আইন,_২০১৩_5431ba7bc5e743768eb8770340eff007.pdf", "পিতা-মাতার ভরণ-পোষণ আইন, ২০১৩"),
        ("00_old_age_allowance_Page_Print.pdf", "old age allowance (ওয়েবপেজ)"),
        ("03_=_files-0_title='ফাইল_১'_ফাইল_১_div_style=_height_700px_82f6cbcd-5e12-4cb3-bd7b-be3328f74214.pdf", ""),
        ("09_ডাউনলোড_23e53ed9f71c4b7faf3bfbf350e2c7f2.pdf", ""),
        ("01_বদলি_সংক্রান্ত_বিজ্ঞপ্তি,_স্মার_Die9XaeyZLL7iVJdoeQdvy58.pdf", "বদলি সংক্রান্ত বিজ্ঞপ্তি, স্মার"),
    ],
)
def test_clean_filename(name: str, expected: str) -> None:
    assert clean_filename(name) == expected


def test_area_for_path_routes_dss_allowance_files() -> None:
    dss = "Department of Social Services (DSS)"
    assert area_for_path(Path(dss, "05_Allowances_and_Social_Safety_Net", "x.pdf"), "general") == "allowance"
    assert area_for_path(Path(dss, "01_Laws_and_Acts", "প্রতিবন্ধী_ভাতা_নীতিমালা.pdf"), "general") == "allowance"
    assert area_for_path(Path(dss, "01_Laws_and_Acts", "শিশু_আইন.pdf"), "general") == "general"
    assert area_for_path(Path("Land Law", "README.md"), "general") == "land"


def test_step_files_skip_byte_identical_copies(tmp_path: Path) -> None:
    a = tmp_path / "Land Law" / "01_Ministry_Policies" / "a.pdf"
    b = tmp_path / "Land Law" / "02_Ministry_Laws_and_Rules" / "b.pdf"
    c = tmp_path / "Land Law" / "02_Ministry_Laws_and_Rules" / "c.pdf"
    for p, data in ((a, b"same"), (b, b"same"), (c, b"other")):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    files = {f.path.name: f for f in step_files(STEP_BY_NAME["land-laws"], root=tmp_path)}
    assert files["b.pdf"].duplicate_of == a  # first copy in manifest order wins
    assert files["c.pdf"].duplicate_of is None
    assert step_files(STEP_BY_NAME["land-policies"], root=tmp_path)[0].duplicate_of is None


def test_markdown_files_skip_root_readme_and_chronological_index(tmp_path: Path) -> None:
    for rel in ("README.md", "NHRC x/README.md", "Laws of Bangladesh (Chronological Index)/era/a.md"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("# t\n", encoding="utf-8")
    names = [str(f.rel) for f in step_files(STEP_BY_NAME["md-guides"], root=tmp_path)]
    assert names == ["NHRC x/README.md"]


# ---------------------------------------------------------------------------- markdown

MD = """# পরীক্ষামূলক নির্দেশিকা

**উৎস:** https://example.gov.bd/page

## ১. নথিপত্র

| ক্রম | শিরোনাম | ফাইল | সাইজ |
|---|---|---|---|
| 1 | নমুনা | [a.pdf](./a.pdf) | 1,000 bytes |
- [b.pdf](./b.pdf) - নমুনা ফাইল (2,000 bytes)

## ২. বিস্তারিত তথ্য

```text
নমুনা লাইন এক: এই অংশে পরীক্ষার জন্য লেখা কিছু বাক্য আছে যা যথেষ্ট লম্বা।
নমুনা লাইন দুই: আরও কিছু [লিংক লেখা](https://example.gov.bd/x) ও **গাঢ়** শব্দ।
```

## ৩. ছোট
এক লাইন
"""


def test_markdown_drops_inventory_keeps_text_and_source() -> None:
    parsed = parse_markdown(MD)
    assert parsed.title == "পরীক্ষামূলক নির্দেশিকা"
    assert parsed.source_url == "https://example.gov.bd/page"
    joined = "\n".join(s.text for s in parsed.sections)
    assert ".pdf" not in joined and "bytes" not in joined and "**" not in joined
    assert "লিংক লেখা" in joined and "https://example.gov.bd/x" not in joined
    assert "এক লাইন" in joined  # the tiny last section is merged, not lost
    spec = DocumentSpec("md-x", "general", "নির্দেশিকা (সংকলিত নির্দেশিকা)", "i", "markdown")
    recs = to_section_records(parsed, spec, "a.md")
    assert [r.id for r in recs] == [f"md-x-h{i}" for i in range(1, len(recs) + 1)]
    assert recs[0].citation.startswith("নির্দেশিকা (সংকলিত নির্দেশিকা), অংশ ")


# ---------------------------------------------------------------------------- sqlite


def _laws_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table acts (id integer primary key, volume_id integer, slug text, title text, year integer,
            act_number text, language text, source_url text, status text, date_of_publication text, raw_text text);
        create table sections (id integer primary key, act_id integer, section_number text, heading text,
            body text, ordinal integer);
        insert into acts values (1, 1, 'act-952', 'বাংলাদেশ শ্রম আইন, ২০০৬', 2006, '৪২', 'bn', '', 'Active', '', '');
        insert into acts values (2, 1, 'act-7', 'নমুনা ভূমি আইন, ২০০৭', 2007, '১', 'bn', '', 'Active', '', '');
        insert into acts values (3, 1, 'act-8', 'The Sample Act, 1900', 1900, 'I', 'en', '', 'Repealed', '', '');
        insert into sections values (1, 2, null, null, '**Status:** Active\n\nনমুনা প্রস্তাবনা', -1);
        insert into sections values (2, 2, null, 'নমুনা শিরোনাম', '১। নমুনা [অন্য আইন](/laws/act-9 "Act 9") ধারা।', 0);
        insert into sections values (3, 2, null, null, 'সংখ্যাবিহীন নমুনা লেখা', 1);
        insert into sections values (4, 3, null, 'Sample', '2. Sample text of a section.', 0);
        insert into sections values (5, 1, null, 'x', '১। skipped', 0);
        """
    )
    conn.commit()
    conn.close()
    return path


def test_sqlite_acts_sections_areas_and_skips(tmp_path: Path) -> None:
    conn = sqlite_laws.connect(_laws_db(tmp_path / "laws.sqlite"))
    acts = list(sqlite_laws.iter_acts(conn))
    assert [a.slug for a in acts] == ["act-8", "act-7"]  # act-952 comes from its PDFs; ordered by year
    eng, land = acts
    eng_spec = sqlite_laws.document_spec(eng, "issuer")
    assert eng_spec.title == "The Sample Act, 1900 [রহিত]" and eng_spec.language == "en"
    assert eng_spec.source_url == "http://bdlaws.minlaw.gov.bd/act-8.html"
    land_spec = sqlite_laws.document_spec(land, "issuer")
    assert land_spec.area == "land" and land_spec.document_id == "bdlaws-act-7"
    recs = sqlite_laws.act_records(conn, land, land_spec, "laws.sqlite")
    assert [r.section for r in recs] == ["প্রস্তাবনা", "১", "অংশ ৩"]
    assert recs[1].citation == "নমুনা ভূমি আইন, ২০০৭, ধারা ১" and recs[1].title == "নমুনা শিরোনাম"
    assert "অন্য আইন" in recs[1].text and "/laws/" not in recs[1].text and "**" not in recs[0].text
    eng_recs = sqlite_laws.act_records(conn, eng, eng_spec, "laws.sqlite")
    assert eng_recs[0].section == "২"
    assert list(sqlite_laws.iter_acts(conn, (2000, 2010)))[0].slug == "act-7"


@pytest.mark.parametrize(
    ("title", "area"),
    [
        ("বাংলাদেশ ইপিজেড শ্রম আইন, ২০১৯", "labour"),
        ("The Non-Agricultural Tenancy Act, 1949", "land"),
        ("The Police Act, 1861", "gd"),
        ("প্রতিবন্ধী ব্যক্তির অধিকার ও সুরক্ষা আইন, ২০১৩", "allowance"),
        ("তথ্য অধিকার আইন, ২০০৯", "general"),
    ],
)
def test_area_for_title(title: str, area: str) -> None:
    assert sqlite_laws.area_for_title(title) == area


# ---------------------------------------------------------------------------- OCR filter


def test_ocr_quality_separates_prose_from_noise() -> None:
    assert ocr_quality("নমুনা বাক্য যেখানে অনেকগুলো সাধারণ বাংলা শব্দ আছে ২০২৪") > 0.8
    assert ocr_quality("Sample sentence with several ordinary English words, 1972") > 0.8
    assert ocr_quality("esi em SS dou} a shee = aaa i Hb gS al Sp eS eS ane SDE aa u") < 0.5
    assert ocr_quality("১২৩ ৪৫৬") == 0.0


# ---------------------------------------------------------------------------- exact sections, many acts


def _chunk(doc: str, act: str, section: str, area: str = "labour") -> ChunkRecord:
    return ChunkRecord(
        id=f"{doc}-s{section}", document_id=doc, area=area, act=act, chapter=None, section=section,  # type: ignore[arg-type]
        title="t", citation=f"{act}, ধারা {section}", part=None, text="নমুনা", normalized_text=f"নমুনা {doc}",
        token_count=1, source_url=None,
    )  # fmt: skip


def _many_acts() -> Retriever:
    chunks = [
        _chunk("labour-act-2006", "বাংলাদেশ শ্রম আইন, ২০০৬", "৪"),
        _chunk("labour-amendment-2026", "বাংলাদেশ শ্রম (সংশোধন) আইন, ২০২৬", "৪"),
        _chunk("bdlaws-act-1", "বাংলাদেশ ইপিজেড শ্রম আইন, ২০১৯", "৪"),
        _chunk("bdlaws-act-2", "নমুনা আইন", "৪", area="general"),
    ]
    return Retriever(BM25Index.build(chunks), None, None)  # type: ignore[arg-type]


def test_exact_section_prefers_named_act() -> None:
    r = _many_acts()
    assert r.exact_section_ids("ইপিজেড শ্রম আইন ২০১৯ এর ধারা ৪", "labour") == ["bdlaws-act-1-s৪"]
    assert r.exact_section_ids("শ্রম (সংশোধন) আইন ২০২৬ ধারা ৪", "labour") == ["labour-amendment-2026-s৪"]


def test_exact_section_uses_hits_then_primary_act() -> None:
    r = _many_acts()
    assert r.exact_section_ids("ধারা ৪", "labour", hint_ids=["labour-amendment-2026-s৪"]) == ["labour-amendment-2026-s৪"]
    assert r.exact_section_ids("ধারা ৪", "labour") == ["labour-act-2006-s৪"]
    assert r.exact_section_ids("ধারা ৪", "general") == ["bdlaws-act-2-s৪"]  # one act in the area: no filtering


# ---------------------------------------------------------------------------- step registry and stores


def _record(doc: str, i: int) -> SectionRecord:
    return SectionRecord(
        id=f"{doc}-p{i}", document_id=doc, area="general", act="নমুনা", section=str(i), title="t",
        citation=f"নমুনা, পৃষ্ঠা {i}", text="নমুনা লেখা", source_file="x.pdf",
    )  # fmt: skip


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(dataset_indexer, "PROCESSED", tmp_path / "processed")
    monkeypatch.setattr(dataset_indexer, "CHUNKS_DIR", tmp_path / "processed" / "chunks")
    monkeypatch.setattr(dataset_indexer, "DATASET_REGISTRY", tmp_path / "dataset_registry.json")
    return tmp_path


def test_save_step_replaces_previous_documents_of_that_step(isolated_paths: Path) -> None:
    a, b = (DocumentSpec(d, "general", "নমুনা", "i", "generic") for d in ("doc-a", "doc-b"))
    assert dataset_indexer.save_step("s1", [a], [_record("doc-a", 1)]) == ["doc-a"]
    assert dataset_indexer.save_step("s1", [b], [_record("doc-b", 1)]) == ["doc-a", "doc-b"]  # old one is deleted
    assert set(dataset_indexer.load_dataset_registry(isolated_paths / "dataset_registry.json")) == {"s1"}
    assert set(dataset_indexer.dataset_specs(isolated_paths / "dataset_registry.json")) == {"doc-b"}
    assert (isolated_paths / "processed" / "all_documents.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_chunk_cache_round_trip(isolated_paths: Path) -> None:
    chunk = _chunk("doc-a", "নমুনা", "১")
    dataset_indexer.write_chunk_cache("s1", [chunk])
    dataset_indexer.write_chunk_cache("s2", [_chunk("doc-b", "নমুনা", "২")])
    loaded = dataset_indexer.load_cached_chunks()
    assert [c.id for c in loaded] == ["doc-a-s১", "doc-b-s২"] and loaded[0] == chunk


class _FakeClient:
    def __init__(self) -> None:
        self.deleted: list[object] = []
        self.points: list[object] = []

    async def delete(self, collection: str, points_selector: object, wait: bool = True) -> None:
        self.deleted.append(points_selector)

    async def upsert(self, collection: str, points: list, wait: bool = True) -> None:
        self.points += points


def test_replace_in_qdrant_deletes_step_documents_then_upserts_in_batches() -> None:
    from app.repositories.qdrant_repository import QdrantRepository

    client = _FakeClient()
    repo = QdrantRepository(client=client, collection="c")  # type: ignore[arg-type]
    chunks = [_chunk("doc-a", "নমুনা", str(i)) for i in range(dataset_indexer.QDRANT_BATCH + 5)]
    vectors = np.zeros((len(chunks), 3), dtype=np.float32)
    asyncio.run(dataset_indexer.replace_in_qdrant(repo, ["doc-a", "doc-old"], chunks, vectors))
    assert len(client.deleted) == 1
    match = client.deleted[0].filter.must[0].match  # type: ignore[attr-defined]
    assert match.any == ["doc-a", "doc-old"]
    assert len(client.points) == len(chunks)


def test_section_refs_ignore_years_next_to_dhara() -> None:
    from app.services.retrieval_service import section_refs

    assert section_refs("শ্রম আইন ২০০৬ ধারা ৪") == ["4"]
    assert section_refs("২৬ ধারা ও ধারা ২৭") == ["26", "27"]


# ---------------------------------------------------------------------------- bdlaws 2026 print layout


def _stream(rows: list[tuple[float, float, str, bool]]) -> list:
    from app.ingestion.bdlaws_parser import _Line

    return [(_Line(1, y, x0, text), margin) for y, x0, text, margin in rows]


def test_bdlaws_left_aligned_title_block_without_chapter() -> None:
    from app.ingestion.bdlaws_parser import ParsedBdlaws, _assemble

    out = ParsedBdlaws()
    _assemble(out, _stream([
        (26.7, 20.2, "21/11/2026", True),
        (40.2, 20.2, "Laws of Bangladesh", True),
        (102.7, 27.8, "নমুনা (সংশোধন) আইন, ২০২৬", False),
        (136.7, 27.8, "( ২০২৬ সনের ১ নং আইন )", False),
        (169.0, 27.8, "[ ১ জানুয়ারি, ২০২৬ ]", True),
        (196.5, 27.8, "নমুনা শিরোনাম", True),
        (213.0, 120.5, "১১। নমুনা সংশোধনী লেখা", False),
        (230.0, 156.5, "১। সন্নিবেশিত নমুনা লেখা", False),
        (230.4, 27.8, "এর সংশোধন", True),
    ]))  # fmt: skip
    assert out.act == "নমুনা (সংশোধন) আইন, ২০২৬"
    assert [s.number for s in out.sections] == ["১১"]  # the inserted "১।" stays in the body
    assert out.sections[0].title_parts == ["নমুনা শিরোনাম", "এর সংশোধন"]
    assert len(out.sections[0].lines) == 2 and not out.preamble


def test_bdlaws_glued_margin_title_is_split() -> None:
    from app.ingestion.bdlaws_parser import _GLUED_TITLE

    m = _GLUED_TITLE.match("নমুনা শিরোনাম, ইত্যাদি1[ ৯৩। (১) নমুনা লেখা")
    assert m and m.group("title") == "নমুনা শিরোনাম, ইত্যাদি" and m.group("body").startswith("1[ ৯৩।")
    assert _GLUED_TITLE.match("নমুনা লেখা যেখানে ২০০৬ সনের আইন আছে।") is None  # digits in the prefix: not a title
