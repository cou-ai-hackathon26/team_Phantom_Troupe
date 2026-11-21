"""Generic PDF pipeline: page classification, OCR engine selection, provenance. Synthetic inputs only."""

import csv
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from app.ingestion import generic_parser
from app.ingestion.area_map import DocumentSpec
from app.ingestion.generic_parser import classify_page, parse_generic_pdf, to_section_records
from app.ingestion.ocr_service import OcrResult, OcrUnavailable, PageOcrRunner
from app.ingestion.source_registry import load_registry, log_source, preserve_original, register

SPEC = DocumentSpec(document_id="test-doc", area="gd", title="পরীক্ষা নথি", issuer="পরীক্ষা", parser="generic")


def test_classify_page() -> None:
    assert classify_page("", has_images=True) == "scanned"
    assert classify_page("   ", has_images=False) == "scanned"
    assert classify_page("eq¯‹fvZv cÖ`vb Kiv n‡e Ges Avek¨K KvMRcÎ RgvμvšÍ Kiæb ‡h", has_images=False) == "legacy"
    assert classify_page("এটি একটি সাধারণ বাংলা পাঠ্যের পৃষ্ঠা যেখানে যথেষ্ট অক্ষর আছে।", has_images=False) == "text"


class FakeEngine:
    def __init__(self, name: str, conf: float) -> None:
        self.name, self.conf, self.calls, self.released = name, conf, 0, False

    def ocr(self, image: Image.Image) -> OcrResult:
        self.calls += 1
        return OcrResult(text=f"{self.name} text", confidence=self.conf, engine=self.name)

    def release(self) -> None:
        self.released = True


def _runner(primary_conf: float, secondary_conf: float | None):
    engines = {"tesseract": FakeEngine("tesseract", primary_conf)}
    if secondary_conf is not None:
        engines["easyocr"] = FakeEngine("easyocr", secondary_conf)

    def factory(name: str):
        if name not in engines:
            raise OcrUnavailable(name)
        return engines[name]

    return PageOcrRunner("tesseract", "easyocr", 70, factory=factory), engines


def test_good_tesseract_skips_second_engine() -> None:
    runner, engines = _runner(85, 95)
    res = runner.ocr_image(Image.new("RGB", (10, 10)), 1)
    assert res.result.engine == "tesseract" and not res.needs_review
    assert engines["easyocr"].calls == 0


def test_low_confidence_uses_better_second_engine() -> None:
    runner, _ = _runner(40, 80)
    res = runner.ocr_image(Image.new("RGB", (10, 10)), 1)
    assert res.result.engine == "easyocr" and not res.needs_review


def test_still_low_confidence_marks_needs_review_and_release_frees() -> None:
    runner, engines = _runner(40, 30)
    res = runner.ocr_image(Image.new("RGB", (10, 10)), 1)
    assert res.result.engine == "tesseract" and res.needs_review
    runner.release()
    assert engines["tesseract"].released and engines["easyocr"].released


def test_no_engine_available_raises() -> None:
    runner = PageOcrRunner("tesseract", "easyocr", 70, factory=lambda n: (_ for _ in ()).throw(OcrUnavailable(n)))
    with pytest.raises(OcrUnavailable):
        runner.ocr_image(Image.new("RGB", (10, 10)), 1)


def _pdf(tmp_path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Section 1. Placeholder text for a synthetic test page with enough characters.")
    doc.new_page()  # blank page -> "scanned", no OCR runner -> skipped + needs_review
    path = tmp_path / "synthetic.pdf"
    doc.save(path)
    return path


def test_generic_parse_records_per_page(tmp_path: Path) -> None:
    parsed = parse_generic_pdf(_pdf(tmp_path), ocr=None)
    assert [r.kind for r in parsed.reports] == ["text", "scanned"]
    assert parsed.reports[1].method == "skipped" and parsed.needs_review
    records = to_section_records(parsed, SPEC, "synthetic.pdf")
    assert len(records) == 1
    rec = records[0]
    assert rec.id == "test-doc-p1" and rec.section == "পৃষ্ঠা ১" and rec.citation == "পরীক্ষা নথি, পৃষ্ঠা ১"
    assert rec.page_start == rec.page_end == 1 and "Placeholder" in rec.text


def test_scanned_page_uses_ocr(tmp_path: Path) -> None:
    runner, _ = _runner(90, None)
    parsed = parse_generic_pdf(_pdf(tmp_path), ocr=runner)
    assert parsed.reports[1].method == "tesseract"
    assert parsed.pages[1] == (2, "tesseract text")


def test_preserve_original_never_overwrites(tmp_path: Path) -> None:
    a = tmp_path / "in" / "doc.pdf"
    a.parent.mkdir()
    a.write_bytes(b"version one")
    originals = tmp_path / "originals"
    first, sha1 = preserve_original(a, "gd", originals)
    again, _ = preserve_original(a, "gd", originals)
    assert first == again and first.read_bytes() == b"version one"
    a.write_bytes(b"version two")
    second, sha2 = preserve_original(a, "gd", originals)
    assert second != first and second.name == "doc_v1.pdf" and sha1 != sha2
    assert first.read_bytes() == b"version one"


def test_registry_and_sources_log(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(generic_parser, "logger", generic_parser.logger)
    reg = tmp_path / "registry.json"
    register(SPEC, reg)
    assert load_registry(reg)["test-doc"].title == "পরীক্ষা নথি"
    log = tmp_path / "sources_log.csv"
    log_source(SPEC, tmp_path / "doc.pdf", "abc123", "pymupdf", "unverified", log)
    log_source(SPEC, tmp_path / "doc.pdf", "abc123", "pymupdf", "unverified", log)  # duplicate ignored
    rows = list(csv.DictReader(log.open(encoding="utf-8")))
    assert len(rows) == 1 and rows[0]["sha256"] == "abc123" and rows[0]["publication_date"] == ""
