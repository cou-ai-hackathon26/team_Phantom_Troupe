"""Regression tests on the real bdlaws PDFs (skipped when the data folder is absent)."""

from pathlib import Path

import pytest

from app.core.config import DATA_DIR
from app.ingestion.area_map import spec_for_folder
from app.ingestion.bdlaws_parser import parse_bdlaws_pdf, to_section_records

FOLDER = "Workers — Bangladesh Labour Act 2006"
PDF_DIR = DATA_DIR / FOLDER


def _pdf(section_print_id: str) -> Path:
    matches = list(PDF_DIR.glob(f"*section-print-{section_print_id}.html.pdf"))
    if not matches:
        pytest.skip("bdlaws PDFs not present")
    return matches[0]


def test_definitions_section_parses_with_title_chapter_and_notes() -> None:
    parsed = parse_bdlaws_pdf(_pdf("29070"))
    records = to_section_records(parsed, spec_for_folder(FOLDER), "x.pdf")
    assert [r.section for r in records] == ["২"]
    rec = records[0]
    assert rec.title == "সংজ্ঞাসমূহ"
    assert rec.chapter == "প্রথম অধ্যায় — প্রারম্ভিক"
    assert rec.citation == "বাংলাদেশ শ্রম আইন, ২০০৬, ধারা ২"
    assert rec.source_url == "https://bdlaws.minlaw.gov.bd/act-print-952/section-print-29070.html"
    assert rec.text.startswith("২। বিষয় বা প্রসঙ্গের পরিপন্থী")
    assert "প্রেক্ষিতে" in rec.text  # a word PyMuPDF splits across two "lines" is rebuilt
    assert "াা" not in rec.text and "ৰ" not in rec.text
    assert len(rec.notes) > 10 and all("আইন" in n for n in rec.notes)
    assert not any(ch.isascii() and ch.isdigit() for ch in rec.text)  # footnote markers stripped


def test_old_page_with_legacy_danda_and_margin_title() -> None:
    rec = to_section_records(parse_bdlaws_pdf(_pdf("29160")), spec_for_folder(FOLDER), "x.pdf")[0]
    assert rec.section == "১৮"
    assert rec.title.startswith("কতিপয় ক্ষেত্রে লে-অফকৃত শ্রমিকগণ")
    assert rec.text.startswith("১৮। (১)")
    assert "\n(খ)" in rec.text  # clauses start on their own line for the chunker


CONSTITUTION = DATA_DIR / "DataSet" / "bdlaws.minlaw.gov.bd_act-print-957.html.pdf"


@pytest.mark.skipif(not CONSTITUTION.exists(), reason="constitution PDF not present")
def test_whole_act_print_gives_one_record_per_article() -> None:
    from app.ingestion.area_map import DocumentSpec

    spec = DocumentSpec("constitution-bn", "general", "সংবিধান", "issuer", "bdlaws")
    parsed = parse_bdlaws_pdf(CONSTITUTION, whole_act=True)
    records = to_section_records(parsed, spec, CONSTITUTION.name, section_label="অনুচ্ছেদ")
    by_section = {r.section: r for r in records}
    assert records[0].section == "প্রস্তাবনা"
    assert {"১", "২ক", "২৭", "১১৮", "১৪১গ", "১৫৩"} <= by_section.keys()
    numbers = [r.section for r in records[1:]]
    assert len(numbers) == len(set(numbers))  # no article twice
    first = by_section["১"]
    assert first.citation.endswith("অনুচ্ছেদ ১") and first.chapter and first.chapter.startswith("প্রথম ভাগ")
    assert "পরিচ্ছেদ" in (by_section["৪৮"].chapter or "")
    assert len(parsed.notes) > 100 and sum(len(r.notes) for r in records) > 50
