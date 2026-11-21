"""Users' personal documents (deeds, letters, notices…), kept ONLY in this process's memory.

Never embedded, never written to Qdrant/Postgres/BM25/disk, never cached or logged. Each document expires
after USER_DOC_TTL_MINUTES or when the user removes it. For a question, the most relevant passages of the
document are picked with an in-memory BM25 and passed to Call 2 next to the official sources.
"""

import secrets
import time
from dataclasses import dataclass, field

from rank_bm25 import BM25Plus

from app.core.config import settings
from app.ingestion.text_normalizer import tokenize

PASSAGE_CHARS = 900
MAX_PASSAGES_TO_LLM = 3


class UserDocExpired(KeyError):
    pass


@dataclass
class Passage:
    index: int  # 1-based within the document
    page: int
    text: str


@dataclass
class UserDoc:
    id: str
    filename: str
    pages: int
    passages: list[Passage]
    methods: list[str]
    needs_review: bool
    expires_at: float
    _bm25: BM25Plus | None = field(default=None, repr=False)

    @property
    def chars(self) -> int:
        return sum(len(p.text) for p in self.passages)

    def select(self, question: str, k: int = MAX_PASSAGES_TO_LLM) -> list[Passage]:
        if len(self.passages) <= k:
            return list(self.passages)
        if self._bm25 is None:
            self._bm25 = BM25Plus([tokenize(p.text) or ["_"] for p in self.passages])
        # BM25Plus: Okapi's IDF is zero or negative in tiny corpora (2–3 passages), which hides the match
        scores = self._bm25.get_scores(tokenize(question) or ["_"])
        ranked = sorted(range(len(self.passages)), key=lambda i: -scores[i])
        chosen = sorted(ranked[:k]) if scores[ranked[0]] > 0 else list(range(k))  # nothing matched: start of doc
        return [self.passages[i] for i in chosen]


def split_passages(pages: list[tuple[int, str]]) -> list[Passage]:
    passages: list[Passage] = []
    for page, text in pages:
        buf = ""
        for para in (p.strip() for p in text.split("\n") if p.strip()):
            if buf and len(buf) + len(para) > PASSAGE_CHARS:
                passages.append(Passage(len(passages) + 1, page, buf))
                buf = para
            else:
                buf = f"{buf}\n{para}".strip()
        if buf:
            passages.append(Passage(len(passages) + 1, page, buf))
    return passages


class UserDocStore:
    def __init__(self) -> None:
        self._docs: dict[str, UserDoc] = {}

    def _purge(self) -> None:
        now = time.time()
        for doc_id in [d for d, doc in self._docs.items() if doc.expires_at < now]:
            del self._docs[doc_id]
        while len(self._docs) > settings.user_doc_max_count:  # oldest first
            del self._docs[min(self._docs, key=lambda d: self._docs[d].expires_at)]

    def add(self, filename: str, pages: list[tuple[int, str]], methods: list[str], needs_review: bool) -> UserDoc:
        self._purge()
        doc = UserDoc(
            id=secrets.token_urlsafe(16),  # unguessable: the id is the only handle to the document
            filename=filename,
            pages=len({p for p, _ in pages}),
            passages=split_passages(pages),
            methods=methods,
            needs_review=needs_review,
            expires_at=time.time() + settings.user_doc_ttl_minutes * 60,
        )
        self._docs[doc.id] = doc
        return doc

    def get(self, doc_id: str) -> UserDoc:
        self._purge()
        doc = self._docs.get(doc_id)
        if doc is None:
            raise UserDocExpired(doc_id)
        return doc

    def delete(self, doc_id: str) -> bool:
        return self._docs.pop(doc_id, None) is not None

    def __len__(self) -> int:
        return len(self._docs)


_store = UserDocStore()


def get_user_doc_store() -> UserDocStore:
    return _store
