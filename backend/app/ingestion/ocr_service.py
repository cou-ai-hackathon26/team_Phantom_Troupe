"""Local OCR only — no page image ever leaves the machine.

Tesseract (ben+eng) first; if its mean confidence is below OCR_MIN_CONFIDENCE, run the configured
second engine (easyocr | surya | paddleocr) and keep the better result. Every page records engine +
confidence; low-confidence pages are marked needs_review. Load OCR models, finish all pages, call
release() (frees GPU memory), and only then embed — never both models on the GPU at once.
"""

import logging
import shutil
from dataclasses import dataclass
from typing import Protocol

import pymupdf
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

RENDER_DPI = 300


class OcrUnavailable(RuntimeError):
    pass


@dataclass
class OcrResult:
    text: str
    confidence: float  # 0–100
    engine: str


@dataclass
class PageOcr:
    page_number: int
    result: OcrResult
    needs_review: bool


class OcrEngine(Protocol):
    name: str

    def ocr(self, image: Image.Image) -> OcrResult: ...
    def release(self) -> None: ...


def render_page(page: pymupdf.Page, dpi: int = RENDER_DPI) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _cuda(preference: str) -> bool:
    if preference == "cpu":
        return False
    try:
        import torch

        return bool(torch.cuda.is_available())
    except ImportError:
        return False


class TesseractEngine:
    name = "tesseract"

    def __init__(self, lang: str = "ben+eng") -> None:
        if shutil.which("tesseract") is None:
            raise OcrUnavailable(
                "Tesseract is not installed. Fedora: sudo dnf install tesseract tesseract-langpack-ben "
                "· Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-ben"
            )
        import pytesseract

        if "ben" in lang and "ben" not in pytesseract.get_languages(config=""):
            raise OcrUnavailable("Tesseract Bengali data (ben) is missing: install tesseract-langpack-ben")
        self._pt = pytesseract
        self.lang = lang

    def ocr(self, image: Image.Image) -> OcrResult:
        data = self._pt.image_to_data(image, lang=self.lang, output_type=self._pt.Output.DICT)
        lines: dict[tuple[int, int, int], list[str]] = {}
        confs: list[float] = []
        for i, word in enumerate(data["text"]):
            conf = float(data["conf"][i])
            if not word.strip() or conf < 0:
                continue
            confs.append(conf)
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append(word)
        text = "\n".join(" ".join(words) for _, words in sorted(lines.items()))
        return OcrResult(text=text, confidence=sum(confs) / len(confs) if confs else 0.0, engine=self.name)

    def release(self) -> None:
        pass


class EasyOcrEngine:
    name = "easyocr"

    def __init__(self) -> None:
        try:
            import easyocr
        except ImportError as exc:
            raise OcrUnavailable("easyocr is not installed: uv pip install easyocr") from exc
        self.reader = easyocr.Reader(["bn", "en"], gpu=_cuda(settings.ocr_device), verbose=False)

    def ocr(self, image: Image.Image) -> OcrResult:
        import numpy as np

        results = self.reader.readtext(np.asarray(image), detail=1, paragraph=False)
        # sort top-to-bottom, then left-to-right
        results.sort(key=lambda r: (round(r[0][0][1] / 20), r[0][0][0]))
        text = "\n".join(r[1] for r in results)
        conf = 100.0 * sum(r[2] for r in results) / len(results) if results else 0.0
        return OcrResult(text=text, confidence=conf, engine=self.name)

    def release(self) -> None:
        self.reader = None  # type: ignore[assignment]
        free_gpu()


class _NotWired:
    """Surya / PaddleOCR APIs change between versions; wire one up after compare_ocr.py picks it."""

    def __init__(self, name: str, package: str) -> None:
        raise OcrUnavailable(f"{name} adapter not wired yet (install {package} and add it in ocr_service.py)")


def make_engine(name: str) -> OcrEngine:
    if name == "tesseract":
        return TesseractEngine()
    if name == "easyocr":
        return EasyOcrEngine()
    if name == "surya":
        return _NotWired("surya", "surya-ocr")  # type: ignore[return-value]
    if name == "paddleocr":
        return _NotWired("paddleocr", "paddleocr")  # type: ignore[return-value]
    raise OcrUnavailable(f"unknown OCR engine {name!r}")


def free_gpu() -> None:
    try:
        import gc

        import torch

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


class PageOcrRunner:
    """Primary engine first, second engine only when needed. Engines load lazily."""

    def __init__(
        self,
        primary: str | None = None,
        secondary: str | None = None,
        min_confidence: float | None = None,
        factory=make_engine,  # noqa: ANN001 - injectable for tests
    ) -> None:
        self.primary_name = primary or settings.ocr_provider
        self.secondary_name = secondary if secondary is not None else settings.ocr_second_engine
        self.min_confidence = settings.ocr_min_confidence if min_confidence is None else min_confidence
        self._factory = factory
        self._engines: dict[str, OcrEngine] = {}
        self._failed: set[str] = set()

    def _engine(self, name: str) -> OcrEngine | None:
        if name in self._failed:
            return None
        if name not in self._engines:
            try:
                self._engines[name] = self._factory(name)
            except OcrUnavailable as exc:
                logger.warning("ocr engine unavailable", extra={"data": {"engine": name, "error": str(exc)}})
                self._failed.add(name)
                return None
        return self._engines[name]

    def ocr_image(self, image: Image.Image, page_number: int) -> PageOcr:
        primary = self._engine(self.primary_name)
        best: OcrResult | None = primary.ocr(image) if primary else None
        if (best is None or best.confidence < self.min_confidence) and self.secondary_name:
            second = self._engine(self.secondary_name)
            if second is not None:
                alt = second.ocr(image)
                if best is None or alt.confidence > best.confidence:
                    best = alt
        if best is None:
            raise OcrUnavailable(
                f"no OCR engine available ({self.primary_name}, {self.secondary_name}); see ocr_service.py"
            )
        return PageOcr(page_number, best, needs_review=best.confidence < self.min_confidence)

    def ocr_page(self, page: pymupdf.Page) -> PageOcr:
        return self.ocr_image(render_page(page), page.number + 1)

    def release(self) -> None:
        for engine in self._engines.values():
            engine.release()
        self._engines.clear()
        free_gpu()
