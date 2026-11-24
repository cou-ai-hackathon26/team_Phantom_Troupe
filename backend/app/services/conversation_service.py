"""/chat with follow-up conversations: ownership, history, and source provenance around the orchestrator.

1. No conversation_id: a new conversation (stored only once its first answer is complete).
   With an id: the token must match (else ConversationNotFound → HTTP 404, same as unknown/expired).
2. One message at a time per conversation (ConversationBusy → HTTP 409).
3. The orchestrator runs with the last few exchanges as context.
4. Only after a complete answer are the user turn and the assistant turn appended together, with the
   assistant turn's exact citation → canonical source mapping. A failed request appends nothing, so a retry
   starts from the same state.

Privacy: for a personal-document answer the assistant text is not kept (it may quote the document), and
personal-document citations are never stored; official citations (canonical ids only) are.
"""

import time

from app.core.config import settings
from app.schemas.chat import ChatRequest, ChatResponse, Citation
from app.schemas.ingestion import ChunkRecord
from app.services.conversation_store import (
    ConversationNotFound,
    ConversationStore,
    SourceRef,
    Turn,
    new_conversation,
    new_turn_id,
)
from app.services.evidence import source_version
from app.services.followup_resolver import TurnContext
from app.services.orchestrator import Orchestrator, TurnOutcome


def source_refs(citations: list[Citation], outcome: TurnOutcome, chunks: dict[str, ChunkRecord]) -> list[SourceRef]:
    """The citation → canonical source mapping actually shown with this answer."""
    refs: list[SourceRef] = []
    for c in citations:
        if c.kind == "user":
            continue  # personal documents are never persisted
        chunk = chunks.get(c.chunk_id) if c.kind == "official" else None
        method, rank = outcome.evidence.get(c.chunk_id, ("cache" if outcome.cached else "unknown", None))
        refs.append(
            SourceRef(
                marker=c.marker,
                kind=c.kind,
                chunk_id=c.chunk_id,
                document_id=chunk.document_id if chunk else None,
                section=c.section,
                citation=c.citation,
                source_version=source_version(chunk) if chunk else None,
                retrieval_method="web" if c.kind == "web" else method,
                rank=rank,
            )
        )
    return refs


class ConversationService:
    def __init__(self, orchestrator: Orchestrator, store: ConversationStore) -> None:
        self.orchestrator = orchestrator
        self.store = store

    async def handle(self, request: ChatRequest) -> ChatResponse:
        token: str | None = None
        if request.conversation_id is None:
            conversation, token = new_conversation()
        elif not request.conversation_token:
            raise ConversationNotFound(request.conversation_id)
        else:
            conversation = await self.store.get(request.conversation_id, request.conversation_token)

        async with self.store.guard(conversation.id):
            context = TurnContext.from_conversation(conversation, settings.conversation_history_exchanges)
            outcome = await self.orchestrator.run_turn(request, context)
            response = outcome.response
            now = time.time()
            user_turn = Turn(id=new_turn_id(), number=0, role="user", content=request.message, created_at=now)
            assistant_turn = Turn(
                id=new_turn_id(),
                number=0,
                role="assistant",
                content="" if outcome.private else response.answer,
                created_at=now,
                status=response.status,
                normalized=response.normalized_question,
                area=response.area,
                private=outcome.private,
                request_id=response.request_id,
                sources=source_refs(response.citations, outcome, self.orchestrator.retriever.chunks),
            )
            conversation.append_exchange(user_turn, assistant_turn)
            await self.store.save(conversation)  # raises on a storage failure: no "saved" response is returned

        response.conversation_id = conversation.id
        response.conversation_token = token  # only for a new conversation
        response.turn_id = assistant_turn.id
        return response
