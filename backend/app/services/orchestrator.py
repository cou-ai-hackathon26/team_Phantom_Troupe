"""The /chat pipeline. At most 2 LLM calls per question.

cache(raw) → Call 1 normalize → gate → cache(normalized) → retrieve → gate → Call 2 → validate → log

With a personal document (request.user_doc_id) the question is "private": no cache read/write, no
refusal before Call 2 (the answer may be in the user's document), and nothing about it is logged.
"""

import time
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.constants import REFUSAL_TEXT
from app.models.llm_client import LLMBadOutput, LLMClient
from app.schemas.chat import ChatRequest, ChatResponse, Trace, TraceCandidate
from app.services.answer_cache import AnswerCache, cache_key
from app.services.citation_validator import validate_answer
from app.services.generation_service import generate_answer, label_chunks, label_user_passages, label_web_passages
from app.services.query_log import record_query
from app.services.query_normalizer import normalize_query
from app.services.retrieval_service import RetrievalResult, Retriever, merge_results
from app.services.trust_policy import pre_retrieval_gate, retrieval_gate
from app.services.user_docs import UserDocStore, get_user_doc_store
from app.services.web_search import WebSearchClient

OFFICIAL_CHUNKS_WITH_USER_DOC = 3  # keep the prompt within free-tier token limits
OFFICIAL_CHUNKS_WITH_WEB = 3  # local chunks kept next to web passages (token budget)
WEB_WARNING = "এই উত্তরের কিছু অংশ সরকারি ওয়েবসাইট থেকে নেওয়া, যা আমাদের যাচাই করা নথিভান্ডারের বাইরে। লিংকে গিয়ে যাচাই করুন।"


@dataclass
class _Run:
    started: float
    llm_calls: int = 0
    gate: str = ""
    retrieval: RetrievalResult | None = None
    normalized: str = ""
    search: str = ""  # Call 1's search_query: what retrieval looks for
    area: str | None = None
    warnings: list[str] = field(default_factory=list)
    private: bool = False


class Orchestrator:
    def __init__(
        self,
        retriever: Retriever,
        llm: LLMClient,
        cache: AnswerCache,
        user_docs: UserDocStore | None = None,
        web: WebSearchClient | None = None,
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.cache = cache
        self.user_docs = user_docs or get_user_doc_store()
        self.web = web  # None: web fallback off (WEB_FALLBACK=false or no TAVILY_API_KEY)

    async def run(self, request: ChatRequest) -> ChatResponse:
        run = _Run(started=time.perf_counter())
        user_doc = self.user_docs.get(request.user_doc_id) if request.user_doc_id else None  # UserDocExpired → 404
        run.private = user_doc is not None
        raw_key = None if run.private else cache_key(request.message, request.area, self.llm.model, "raw")
        if raw_key and (hit := await self.cache.get(raw_key)) is not None:
            return await self._from_cache(hit, request, run)

        # ---- Call 1: normalize + classify (LLM errors other than bad output propagate → HTTP 503)
        query = await normalize_query(self.llm, request.message)
        run.llm_calls += 1
        run.normalized = query.standard_bangla
        run.search = query.search_query or query.standard_bangla
        run.area = request.area or query.area

        gate = pre_retrieval_gate(query)
        if gate.decision == "refuse" and not run.private:
            return await self._finish(request, run, gate.reason, "refused", REFUSAL_TEXT, raw_key=raw_key)
        if gate.decision == "clarify" and not run.private:
            return await self._finish(request, run, gate.reason, "clarify", query.clarification_question or "")

        norm_key = None if run.private else cache_key(run.normalized, run.area, self.llm.model, "normalized")
        if norm_key and (hit := await self.cache.get(norm_key)) is not None:
            if raw_key:
                await self.cache.set(raw_key, hit)
            return await self._from_cache(hit, request, run)

        # ---- retrieval + score gate
        run.retrieval = await self.retriever.retrieve(run.search, area=run.area)
        if run.area and not request.area:
            # the area is Call 1's guess: also search every area and fuse, so a wrong guess
            # (e.g. a lost NID classified as "general") cannot hide the right documents
            wide = await self.retriever.retrieve(run.search, area=None)
            run.retrieval = merge_results(run.retrieval, wide, top_n=settings.fused_top_k, k=settings.rrf_k)
        # a multi-issue question (land grab + theft + threat): one more search per other problem, all areas,
        # fused into the same ranking with one extra slot each so every problem can reach Call 2
        for i, extra in enumerate(query.extra_queries, start=1):
            more = await self.retriever.retrieve(extra, area=None)
            run.retrieval = merge_results(run.retrieval, more, top_n=settings.fused_top_k + i, k=settings.rrf_k)
        gate = retrieval_gate(run.retrieval)
        web_passages = await self._web_fallback(run, gate.decision)
        if web_passages:
            gate = type(gate)("continue", f"{gate.reason}+web")
        if gate.decision == "refuse" and not run.private:
            return await self._finish(
                request, run, gate.reason, "refused", REFUSAL_TEXT, raw_key=raw_key, norm_key=norm_key
            )

        # ---- Call 2: grounded answer, then validation in code
        official = run.retrieval.top_chunks()
        if user_doc is not None:
            # official passages only if the score gate passed; the user's passages always go in
            official = official[:OFFICIAL_CHUNKS_WITH_USER_DOC] if gate.decision == "continue" else []
            labelled: dict = label_chunks(official)
            labelled.update(label_user_passages(user_doc.id, user_doc.filename, user_doc.select(run.search)))
        else:
            labelled = label_chunks(official[:OFFICIAL_CHUNKS_WITH_WEB] if web_passages else official)
        if web_passages:
            if gate.reason.startswith(("low_score", "no_candidates")):
                labelled = {}  # local chunks failed the score gate: only the web passages go in
            labelled.update(label_web_passages(web_passages))
        try:
            result = await generate_answer(self.llm, run.normalized, labelled)
        except LLMBadOutput:
            run.llm_calls += 1
            return await self._finish(request, run, "answer_bad_json", "refused", REFUSAL_TEXT)
        run.llm_calls += 1
        validation = validate_answer(result.data, labelled)
        if validation.status == "refused":
            return await self._finish(
                request,
                run,
                f"validation:{validation.reason}",
                "refused",
                REFUSAL_TEXT,
                raw_key=raw_key,
                norm_key=norm_key,
            )
        response = await self._finish(
            request,
            run,
            "answered",
            validation.status,
            validation.answer,
            citations=validation.citations,
            warnings=validation.warnings
            + ([WEB_WARNING] if any(c.kind == "web" for c in validation.citations) else []),
            raw_key=raw_key,
            norm_key=norm_key,
        )
        return response

    # ------------------------------------------------------------------ helpers
    async def _web_fallback(self, run: _Run, gate_decision: str) -> list:
        """Search official websites when local evidence is weak. Never for personal-document questions
        (their text must not leave the server) or when a named section was matched exactly."""
        if self.web is None or run.private or run.retrieval is None:
            return []
        if any(c.exact_section for c in run.retrieval.candidates):
            return []
        weak = gate_decision == "refuse" or run.retrieval.best_dense_score < settings.web_trigger_score
        if not weak:
            return []
        return await self.web.search(run.search)

    def _trace(self, run: _Run) -> Trace:
        candidates: list[TraceCandidate] = []
        if run.retrieval is not None:
            for c in run.retrieval.candidates:
                chunk = run.retrieval.chunks.get(c.chunk_id)
                candidates.append(
                    TraceCandidate(
                        chunk_id=c.chunk_id,
                        citation=chunk.citation if chunk else c.chunk_id,
                        title=chunk.title if chunk else "",
                        part=chunk.part if chunk else None,
                        dense_rank=c.dense_rank,
                        dense_score=c.dense_score,
                        bm25_rank=c.bm25_rank,
                        bm25_score=c.bm25_score,
                        fused_score=c.fused_score,
                        exact_section=c.exact_section,
                    )
                )
        return Trace(
            candidates=candidates,
            best_dense_score=run.retrieval.best_dense_score if run.retrieval else 0.0,
            llm_calls=run.llm_calls,
            model=self.llm.model,
            gate=run.gate,
        )

    async def _finish(
        self,
        request: ChatRequest,
        run: _Run,
        gate: str,
        status: str,
        answer: str,
        *,
        citations: list | None = None,
        warnings: list[str] | None = None,
        raw_key: str | None = None,
        norm_key: str | None = None,
    ) -> ChatResponse:
        run.gate = gate
        latency_ms = int((time.perf_counter() - run.started) * 1000)
        trace = self._trace(run)
        response = ChatResponse(
            status=status,  # type: ignore[arg-type]
            answer=answer,
            citations=citations or [],
            normalized_question=run.normalized or request.message,
            area=run.area or "unknown",
            warnings=warnings or [],
            trace=trace if request.debug else None,
            latency_ms=latency_ms,
            cached=False,
        )
        # cache the full response (incl. trace) so a cached answer can still show "how it was found"
        cacheable = response.model_dump(exclude={"latency_ms", "cached", "request_id"}) | {"trace": trace.model_dump()}
        # refusals are not cached: after new documents or a prompt fix the same question may be answerable,
        # and a cached refusal would hide that (the answer cache is cleared on ingest, but not on code changes)
        for key in (raw_key, norm_key) if status != "refused" else ():
            if key is not None:
                await self.cache.set(key, cacheable)
        response.request_id = await record_query(
            message=request.message,
            normalized_question=response.normalized_question,
            private=run.private,
            area=run.area,
            status=status,
            retrieved_chunk_ids=[c.chunk_id for c in trace.candidates],
            best_dense_score=trace.best_dense_score if run.retrieval else None,
            latency_ms=latency_ms,
            llm_calls=run.llm_calls,
            cached=False,
            model=self.llm.model,
            gate=gate,
        )
        return response

    async def _from_cache(self, hit: dict, request: ChatRequest, run: _Run) -> ChatResponse:
        latency_ms = int((time.perf_counter() - run.started) * 1000)
        response = ChatResponse(**{**hit, "latency_ms": latency_ms, "cached": True})
        if not request.debug:
            response.trace = None
        response.request_id = await record_query(
            message=request.message,
            normalized_question=response.normalized_question,
            area=response.area,
            status=response.status,
            retrieved_chunk_ids=[c.chunk_id for c in response.citations],
            best_dense_score=None,
            latency_ms=latency_ms,
            llm_calls=run.llm_calls,
            cached=True,
            model=self.llm.model,
            gate="cache",
        )
        return response
