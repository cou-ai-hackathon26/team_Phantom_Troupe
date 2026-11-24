"""Conversations for follow-up questions, kept ONLY in this process's memory.

A conversation holds the citizen's turns and, for each assistant turn, the exact sources it cited (canonical
chunk ids + citation marker + content hash), never a copy of the knowledge base. It expires after
CONVERSATION_TTL_MINUTES without a new turn and is lost when the API restarts, like personal documents.

Ownership: a new conversation gets a random secret token (returned once to the client). Only its SHA-256 is
stored; every read checks it in constant time. A wrong token and an unknown id give the same error, so ids
cannot be probed. Turns are appended only after an answer is complete, both at once, under a per-conversation
guard that rejects a second concurrent message (no duplicate turn numbers, no interleaving).

`ConversationStore` is the interface; `MemoryConversationStore` is the only implementation. A shared store
(e.g. Redis, for several API workers) would implement the same four methods.
"""

import hashlib
import hmac
import secrets
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.core.config import settings

MAX_TURNS_KEPT = 40  # per conversation; older turns are dropped (only the last few are ever read)


class ConversationNotFound(KeyError):
    """Unknown, expired, or not owned by the caller (deliberately indistinguishable)."""


class ConversationBusy(RuntimeError):
    """Another message of the same conversation is still being answered."""


@dataclass(frozen=True)
class SourceRef:
    """One citation of an assistant turn. The marker ([১] = 1) is local to that turn."""

    marker: int
    kind: str  # official | web (personal-document citations are never stored)
    chunk_id: str  # canonical chunk id (official) or the web passage id
    document_id: str | None
    section: str
    citation: str
    source_version: str | None  # hash of the chunk text when it was cited (detects edited/replaced chunks)
    retrieval_method: str  # dense | bm25 | hybrid | exact | reused | web | cache
    rank: int | None = None  # position in the evidence bundle given to Call 2


@dataclass
class Turn:
    id: str
    number: int  # 1, 2, 3 … within the conversation
    role: Literal["user", "assistant"]
    content: str  # assistant turns about a personal document store "" (its text may quote the document)
    created_at: float
    status: str | None = None  # assistant: answered | partial | refused | clarify
    normalized: str | None = None  # assistant: the standalone question this turn answered
    area: str | None = None
    private: bool = False  # answered with a personal document
    request_id: str | None = None
    sources: list[SourceRef] = field(default_factory=list)


@dataclass
class Conversation:
    id: str
    token_hash: str
    created_at: float
    updated_at: float
    expires_at: float
    turns: list[Turn] = field(default_factory=list)

    @property
    def next_number(self) -> int:
        return self.turns[-1].number + 1 if self.turns else 1

    def append_exchange(self, user: Turn, assistant: Turn) -> None:
        """Numbers both turns and appends them together; call only under the conversation's guard."""
        user.number = self.next_number
        assistant.number = user.number + 1
        self.turns.extend((user, assistant))
        del self.turns[:-MAX_TURNS_KEPT]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_turn_id() -> str:
    return str(uuid.uuid4())


def new_conversation() -> tuple[Conversation, str]:
    """A conversation that is not stored yet (saved only after its first answer), and its secret token."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    conv = Conversation(
        id=str(uuid.uuid4()),
        token_hash=_hash(token),
        created_at=now,
        updated_at=now,
        expires_at=now + settings.conversation_ttl_minutes * 60,
    )
    return conv, token


class ConversationStore(Protocol):
    async def get(self, conversation_id: str, token: str) -> Conversation: ...
    async def save(self, conversation: Conversation) -> None: ...
    def guard(self, conversation_id: str) -> AbstractAsyncContextManager[None]: ...
    async def delete(self, conversation_id: str) -> None: ...


class MemoryConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._busy: set[str] = set()

    def _purge(self) -> None:
        now = time.time()
        for cid in [c for c, conv in self._conversations.items() if conv.expires_at < now and c not in self._busy]:
            del self._conversations[cid]
        while len(self._conversations) > settings.conversation_max_count:  # least recently used first
            del self._conversations[min(self._conversations, key=lambda c: self._conversations[c].updated_at)]

    async def get(self, conversation_id: str, token: str) -> Conversation:
        self._purge()
        conv = self._conversations.get(conversation_id)
        # compare even when the id is unknown, so timing does not reveal which ids exist
        expected = conv.token_hash if conv else _hash("")
        if not hmac.compare_digest(expected, _hash(token or "")) or conv is None:
            raise ConversationNotFound(conversation_id)
        return conv

    async def save(self, conversation: Conversation) -> None:
        now = time.time()
        conversation.updated_at = now
        conversation.expires_at = now + settings.conversation_ttl_minutes * 60
        self._conversations[conversation.id] = conversation
        self._purge()

    @asynccontextmanager
    async def guard(self, conversation_id: str) -> AsyncIterator[None]:
        """One message at a time per conversation. Single event loop: check-and-add cannot interleave."""
        if conversation_id in self._busy:
            raise ConversationBusy(conversation_id)
        self._busy.add(conversation_id)
        try:
            yield
        finally:
            self._busy.discard(conversation_id)

    async def delete(self, conversation_id: str) -> None:
        self._conversations.pop(conversation_id, None)

    def __len__(self) -> int:
        return len(self._conversations)


_store = MemoryConversationStore()


def get_conversation_store() -> MemoryConversationStore:
    return _store
