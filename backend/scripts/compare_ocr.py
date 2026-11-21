"""Run every installed local OCR engine on a few pages and write side-by-side text files,
so the team can pick OCR_SECOND_ENGINE from real scanned pages.

Usage (from backend/):  python scripts/compare_ocr.py scan.pdf --pages 1-3
Output: data/ocr/compare/<pdf stem>/<engine>_p<N>.txt and a confidence/timing table.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402

from app.core.config import DATA_DIR  # noqa: E402
from app.ingestion.ocr_service import OcrUnavailable, free_gpu, make_engine, render_page  # noqa: E402

ENGINES = ("tesseract", "easyocr", "surya", "paddleocr")


def parse_pages(spec: str, count: int) -> list[int]:
    pages: set[int] = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            pages.update(range(int(a), int(b) + 1))
        else:
            pages.add(int(part))
    return sorted(p for p in pages if 1 <= p <= count)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--pages", default="1-3")
    args = ap.parse_args()

    out_dir = DATA_DIR / "ocr" / "compare" / args.pdf.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(args.pdf) as doc:
        pages = parse_pages(args.pages, doc.page_count)
        images = {p: render_page(doc[p - 1]) for p in pages}

    print(f"{'engine':<10} {'page':>4} {'conf':>6} {'chars':>6} {'sec':>6}")
    for name in ENGINES:
        try:
            engine = make_engine(name)
        except OcrUnavailable as exc:
            print(f"{name:<10} skipped: {exc}")
            continue
        for p, image in images.items():
            t0 = time.perf_counter()
            res = engine.ocr(image)
            (out_dir / f"{name}_p{p}.txt").write_text(res.text, encoding="utf-8")
            print(f"{name:<10} {p:>4} {res.confidence:6.1f} {len(res.text):>6} {time.perf_counter() - t0:6.1f}")
        engine.release()  # one model on the GPU at a time
        free_gpu()
    print(f"\ntext files: {out_dir.relative_to(DATA_DIR.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
