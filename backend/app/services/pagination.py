"""Page slicing, text filtering and an index-bound cache for the document listings (/sources, /admin/documents)."""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.ingestion.text_normalizer import bn_to_ascii_digits, normalize_text

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass
class Page[T]:
    items: list[T]
    total: int
    page: int  # 1-based, clamped to the last page
    page_size: int
    pages: int


def paginate[T](items: Sequence[T], page: int, page_size: int) -> Page[T]:
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    pages = max(1, math.ceil(len(items) / page_size))
    page = max(1, min(page, pages))
    start = (page - 1) * page_size
    return Page(list(items[start : start + page_size]), len(items), page, page_size, pages)


def search_key(*fields: str | None) -> str:
    """Lower-cased, normalized text to match a query against; Bangla digits become ASCII so ২০০৬ = 2006."""
    return bn_to_ascii_digits(normalize_text(" ".join(f for f in fields if f))).lower()


def matches(query: str | None, key: str) -> bool:
    q = search_key(query) if query else ""
    return not q or all(word in key for word in q.split())


class IndexCache[T]:
    """Holds one computed value per loaded index. The retriever swaps in a new BM25 index after every
    admin upload/delete (Retriever.replace_index), so the value is rebuilt exactly when the documents change."""

    def __init__(self) -> None:
        self._key: object | None = None
        self._value: T | None = None

    def get(self, index: object, build: Callable[[], T]) -> T:
        if self._key is not index or self._value is None:
            self._value = build()
            self._key = index
        return self._value

    def clear(self) -> None:
        self._key = None
        self._value = None
