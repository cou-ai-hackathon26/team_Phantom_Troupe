"""The /chat pipeline. At most 2 LLM calls per question.

cache(raw) → Call 1 normalize → gate → cache(normalized) → retrieve → gate → Call 2 → validate → log
"""

import time
from dataclasses import dataclass, field

from app.core.constants import REFUSAL_TEXT
from app.models.llm_client import LLMBadOutput, LLMClient
from app.schemas.chat import ChatRequest, ChatResponse, Trace, TraceCandidate
from app.services.answer_cache import AnswerCache, cache_key
from app.services.citation_validator import validate_answer
from app.services.generation_service import generate_answer, label_chunks
from app.services.query_log import record_query
from app.services.query_normalizer import normalize_query
from app.services.retrieval_service import RetrievalResult, Retriever
from app.services.trust_policy import pre_retrieval_gate, retrieval_gate


@dataclass
class _Run:
    started: float
    llm_calls: int = 0
    gate: str = ""
    retrieval: RetrievalResult | None = None
    normalized: str = ""
    area: str | None = None
    warnings: list[str] = field(default_factory=list)


class Orchestrator:
    def __init__(self, retriever: Retriever, llm: LLMClient, cache: AnswerCache) -> None:
        self.retriever = retriever
        self.llm = llm
        self.cache = cache

    async def run(self, request: ChatRequest) -> ChatResponse:
        run = _Run(started=time.perf_counter())
        raw_key = cache_key(request.message, request.area, self.llm.model, "raw")
        if (hit := await self.cache.get(raw_key)) is not None:
            return await self._from_cache(hit, request, run)

        # ---- Call 1: normalize + classify (LLM errors other than bad output propagate → HTTP 503)
        query = await normalize_query(self.llm, request.message)
        run.llm_calls += 1
        run.normalized = query.standard_bangla
        run.area = request.area or query.area

        gate = pre_retrieval_gate(query)
        if gate.decision == "refuse":
            return await self._finish(request, run, gate.reason, "refused", REFUSAL_TEXT, raw_key=raw_key)
        if gate.decision == "clarify":
            return await self._finish(request, run, gate.reason, "clarify", query.clarification_question or "")

        norm_key = cache_key(run.normalized, run.area, self.llm.model, "normalized")
        if (hit := await self.cache.get(norm_key)) is not None:
            await self.cache.set(raw_key, hit)
            return await self._from_cache(hit, request, run)

        # ---- retrieval + score gate
        run.retrieval = await self.retriever.retrieve(run.normalized, area=run.area)
        gate = retrieval_gate(run.retrieval)
        if gate.decision == "refuse":
            return await self._finish(
                request, run, gate.reason, "refused", REFUSAL_TEXT, raw_key=raw_key, norm_key=norm_key
            )

        # ---- Call 2: grounded answer, then validation in code
        labelled = label_chunks(run.retrieval.top_chunks())
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
            warnings=validation.warnings,
            raw_key=raw_key,
            norm_key=norm_key,
        )
        return response

    # ------------------------------------------------------------------ helpers
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
        for key in (raw_key, norm_key):
            if key is not None:
                await self.cache.set(key, cacheable)
        response.request_id = await record_query(
            message=request.message,
            normalized_question=response.normalized_question,
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
