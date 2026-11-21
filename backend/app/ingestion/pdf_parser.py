"""Page-preserving PDF text extraction with PyMuPDF.

Bangla conjunct glyphs often break PyMuPDF's line grouping: one visual row comes back as several
"lines" that split a word in the middle ("প্রেক্ষি" + "তে"). We rebuild visual rows:
- glyph text comes from `words` extraction (the only mode that keeps multi-codepoint glyphs like "্ষি"),
- whether two fragments on the same row need a space comes from `rawdict`, which keeps the real
  space characters at fragment edges.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

ROW_TOLERANCE = 6.0  # points; fragments whose vertical centres are this close share a row


@dataclass
class Row:
    y_mid: float
    x0: float
    x1: float
    text: str


@dataclass
class PageText:
    page_number: int  # 1-based
    width: float
    height: float
    rows: list[Row] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(r.text for r in self.rows)

    @property
    def char_count(self) -> int:
        return sum(len(r.text.strip()) for r in self.rows)


@dataclass
class _Fragment:
    y_mid: float
    x0: float
    x1: float
    text: str
    space_before: bool
    space_after: bool


def _edge_spaces(page: pymupdf.Page) -> dict[tuple[int, int], tuple[bool, bool]]:
    edges: dict[tuple[int, int], tuple[bool, bool]] = {}
    for block in page.get_text("rawdict")["blocks"]:
        for line_no, line in enumerate(block.get("lines", [])):
            raw = "".join(ch["c"] for span in line["spans"] for ch in span["chars"])
            edges[(block["number"], line_no)] = (raw[:1].isspace(), raw[-1:].isspace())
    return edges


def extract_rows(page: pymupdf.Page, keep: Callable[[float, float], bool] | None = None) -> list[Row]:
    """Rebuild visual rows. `keep(x0, x1)` selects fragments before rows are joined, which lets a
    caller separate a margin column (e.g. bdlaws section titles) from the body text."""
    edges = _edge_spaces(page)
    grouped: dict[tuple[int, int], list[tuple[float, float, float, float, str]]] = defaultdict(list)
    for x0, y0, x1, y1, word, block_no, line_no, _ in page.get_text("words"):
        grouped[(block_no, line_no)].append((x0, y0, x1, y1, word))

    fragments: list[_Fragment] = []
    for key, words in grouped.items():
        words.sort(key=lambda w: w[0])
        before, after = edges.get(key, (True, True))
        fragments.append(
            _Fragment(
                y_mid=(min(w[1] for w in words) + max(w[3] for w in words)) / 2,
                x0=words[0][0],
                x1=max(w[2] for w in words),
                text=" ".join(w[4] for w in words),
                space_before=before,
                space_after=after,
            )
        )

    if keep is not None:
        fragments = [f for f in fragments if keep(f.x0, f.x1)]
    fragments.sort(key=lambda f: (f.y_mid, f.x0))
    rows: list[list[_Fragment]] = []
    for frag in fragments:
        if rows and abs(frag.y_mid - rows[-1][0].y_mid) < ROW_TOLERANCE:
            rows[-1].append(frag)
        else:
            rows.append([frag])
    return [_join_row(sorted(r, key=lambda f: f.x0)) for r in rows]


def _join_row(frags: list[_Fragment]) -> Row:
    text = frags[0].text
    for prev, frag in zip(frags, frags[1:], strict=False):
        sep = " " if (prev.space_after or frag.space_before) else ""
        text += sep + frag.text
    return Row(y_mid=frags[0].y_mid, x0=frags[0].x0, x1=max(f.x1 for f in frags), text=text)


def parse_pdf(path: str | Path) -> list[PageText]:
    pages: list[PageText] = []
    with pymupdf.open(path) as doc:
        for index, page in enumerate(doc):
            pages.append(
                PageText(
                    page_number=index + 1,
                    width=page.rect.width,
                    height=page.rect.height,
                    rows=extract_rows(page),
                )
            )
    return pages
