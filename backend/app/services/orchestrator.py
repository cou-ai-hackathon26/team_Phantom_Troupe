"""The /chat pipeline. At most 2 LLM calls per question.

cache(raw) → Call 1 normalize → gate → cache(normalized) → retrieve → gate → Call 2 → validate → log

With a personal document (request.user_doc_id) the question is "private": no cache read/write, no
refusal before Call 2 (the answer may be in the user's document), and nothing about it is logged.

Follow-up mode (`run_turn` with a TurnContext that has history; see services/conversation_service.py):
Call 1 also sees the recent exchanges and returns a follow-up intent (followup_resolver). CLARIFY stops at
the pre-retrieval gate. CONTINUE/EXPAND re-verify the referenced turn's cited chunks (evidence.py) and put
them before the fresh hybrid results; NEW_TOPIC uses fresh results only. Fresh retrieval always runs (it is
local; judging "enough evidence" would need a third LLM call). Follow-ups never read or write the answer
cache, because the cache key cannot see the conversation.
"""

import logging
import time
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.constants import REFUSAL_TEXT
from app.models.llm_client import LLMBadOutput, LLMClient
from app.schemas.chat import ChatRequest, ChatResponse, Trace, TraceCandidate
from app.schemas.conflict import ConflictAnalysis
from app.schemas.conversation import FollowupResolution
from app.schemas.ingestion import ChunkRecord
from app.services.answer_cache import AnswerCache, cache_key
from app.services.citation_validator import validate_answer
from app.services.conflict_disclosure import ConflictRun, failed_analysis, finalize, prepare
from app.services.evidence import ReuseReport, merge_evidence, retrieval_method, reusable_sources
from app.services.followup_resolver import (
    TurnContext,
    answer_history_block,
    apply_resolution,
    normalize_history_block,
    resolve_followup,
)
from app.services.generation_service import (
    FollowupPrompt,
    generate_answer,
    label_chunks,
    label_user_passages,
    label_web_passages,
)
from app.services.query_log import record_query
from app.services.query_normalizer import normalize_query
from app.services.retrieval_service import RetrievalResult, Retriever, merge_results
from app.services.trust_policy import Gate, pre_retrieval_gate, retrieval_gate
from app.services.user_docs import UserDocStore, get_user_doc_store
from app.services.web_search import WebSearchClient

logger = logging.getLogger(__name__)

OFFICIAL_CHUNKS_WITH_USER_DOC = 3  # keep the prompt within free-tier token limits
OFFICIAL_CHUNKS_WITH_WEB = 3  # local chunks kept next to web passages (token budget)
HISTORY_EXCHANGES_FOR_ANSWER = 2  # referenced exchanges shown to Call 2 (token budget)
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
    cached: bool = False
    resolution: FollowupResolution | None = None  # follow-up mode only
    reuse: ReuseReport | None = None  # earlier sources that were re-checked (follow-up mode only)
    evidence: dict[str, tuple[str, int]] = field(default_factory=dict)  # passage id -> (method, rank in bundle)


@dataclass
class TurnOutcome:
    """A finished turn plus the provenance the conversation needs to remember its sources."""

    response: ChatResponse
    evidence: dict[str, tuple[str, int]]  # passage id -> (retrieval method, rank) for every passage given to Call 2
    resolution: FollowupResolution | None
    private: bool
    cached: bool


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
        """A single question without conversation context (scripts, voice route, older callers)."""
        return (await self.run_turn(request)).response

    async def run_turn(self, request: ChatRequest, context: TurnContext | None = None) -> TurnOutcome:
        run = _Run(started=time.perf_counter())
        response = await self._pipeline(request, context or TurnContext(), run)
        return TurnOutcome(response, dict(run.evidence), run.resolution, run.private, run.cached)

    async def _pipeline(self, request: ChatRequest, context: TurnContext, run: _Run) -> ChatResponse:
        user_doc = self.user_docs.get(request.user_doc_id) if request.user_doc_id else None  # UserDocExpired → 404
        run.private = user_doc is not None
        use_cache = not run.private and not context.has_history
        raw_key = cache_key(request.message, request.area, self.llm.model, "raw") if use_cache else None
        if raw_key and (hit := await self.cache.get(raw_key)) is not None:
            return await self._from_cache(hit, request, run)

        # ---- Call 1: normalize + classify (LLM errors other than bad output propagate → HTTP 503);
        # with history it also resolves references and classifies the follow-up intent
        history = normalize_history_block(context) if context.has_history else None
        query = await normalize_query(self.llm, request.message, history=history)
        run.llm_calls += 1
        if context.has_history:
            run.resolution = resolve_followup(query, context)
            query = apply_resolution(query, run.resolution)
        run.normalized = query.standard_bangla
        run.search = query.search_query or query.standard_bangla
        run.area = request.area or query.area

        gate = pre_retrieval_gate(query)
        if gate.decision == "refuse" and not run.private:
            return await self._finish(request, run, gate.reason, "refused", REFUSAL_TEXT, raw_key=raw_key)
        if gate.decision == "clarify" and not run.private:
            return await self._finish(request, run, gate.reason, "clarify", query.clarification_question or "")

        norm_key = cache_key(run.normalized, run.area, self.llm.model, "normalized") if use_cache else None
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
        fresh_gate = retrieval_gate(run.retrieval)
        reused = self._reusable_evidence(run, context)
        web_passages = await self._web_fallback(run, fresh_gate.decision)
        gate = fresh_gate
        if web_passages:
            gate = Gate("continue", f"{gate.reason}+web")
        if gate.decision == "refuse" and reused:
            gate = Gate("continue", f"{gate.reason}+reused")  # verified earlier evidence still goes to Call 2
        if gate.decision == "refuse" and not run.private:
            return await self._finish(
                request, run, gate.reason, "refused", REFUSAL_TEXT, raw_key=raw_key, norm_key=norm_key
            )

        # ---- evidence bundle: reused earlier sources first, then fresh chunks if they passed the score gate
        top = run.retrieval.top_chunks()
        fresh = top if fresh_gate.decision == "continue" else []  # failed: only web/user/reused passages go in
        if user_doc is not None:
            cap = OFFICIAL_CHUNKS_WITH_USER_DOC
        elif web_passages:
            cap = OFFICIAL_CHUNKS_WITH_WEB
        else:
            cap = max(len(top), settings.fused_top_k)
        methods = {c.chunk_id: retrieval_method(c) for c in run.retrieval.candidates}
        bundle = merge_evidence(reused, fresh, methods, cap)
        run.evidence = {chunk.id: (method, rank) for rank, (chunk, method) in enumerate(bundle, start=1)}
        labelled: dict = label_chunks([chunk for chunk, _ in bundle])
        if user_doc is not None:
            # the user's passages always go in (never stored, never reused in a later turn)
            labelled.update(label_user_passages(user_doc.id, user_doc.filename, user_doc.select(run.search)))
        if web_passages:
            labelled.update(label_web_passages(web_passages))
            for passage in web_passages:
                run.evidence[passage.id] = ("web", len(run.evidence) + 1)

        # ---- conflict check on the evidence (rules, no LLM), then Call 2 with its brief
        conflicts = self._conflict_run(labelled, run)
        try:
            result = await generate_answer(
                self.llm,
                run.normalized,
                labelled,
                self._followup_prompt(request, run, context),
                conflict_brief=conflicts.brief if conflicts else None,
            )
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
        answer, citations, warnings = validation.answer, validation.citations, list(validation.warnings)
        analysis: ConflictAnalysis | None = None
        if settings.conflict_detection:
            analysis = failed_analysis()
            if conflicts is not None:
                try:
                    disclosure = finalize(conflicts, result.data, answer, citations)
                    answer, citations, analysis = disclosure.answer, disclosure.citations, disclosure.analysis
                    warnings += disclosure.warnings
                except Exception as exc:  # noqa: BLE001 - never fail the answer; report "insufficient evidence"
                    logger.warning("conflict finalize failed", extra={"data": {"error": type(exc).__name__}})
        response = await self._finish(
            request,
            run,
            "answered",
            validation.status,
            answer,
            citations=citations,
            warnings=warnings + ([WEB_WARNING] if any(c.kind == "web" for c in citations) else []),
            raw_key=raw_key,
            norm_key=norm_key,
            conflict_analysis=analysis,
        )
        return response

    # ------------------------------------------------------------------ helpers
    def _conflict_run(self, labelled: dict, run: _Run) -> ConflictRun | None:
        """Claims + rule-based conflict pairs for the passages Call 2 will see. None if off or it failed."""
        if not settings.conflict_detection:
            return None
        try:
            return prepare(labelled, run.normalized, self.retriever.programmes())
        except Exception as exc:  # noqa: BLE001 - the answer goes on; the analysis reports insufficient evidence
            logger.warning("conflict check failed", extra={"data": {"error": type(exc).__name__}})
            return None

    def _reusable_evidence(self, run: _Run, context: TurnContext) -> list[ChunkRecord]:
        """CONTINUE/EXPAND: the referenced turns' cited chunks, reloaded from the live index and re-verified."""
        res = run.resolution
        if res is None or not res.reuse_previous_sources or run.retrieval is None:
            return []
        exchanges = context.by_turn_id(res.referenced_turn_ids)
        # most recent referenced turn first; within a turn, in citation order
        sources = [s for ex in reversed(exchanges) for s in sorted(ex.sources, key=lambda s: s.marker)]
        limit = settings.conversation_max_reused_sources
        if res.intent == "EXPAND":
            limit = max(1, limit - 1)  # leave more room for the fresh passages the new question needs
        run.reuse = reusable_sources(
            sources,
            self.retriever.bm25,
            query=f"{run.normalized} {run.search}",
            fresh_ids=[c.chunk_id for c in run.retrieval.candidates],
            limit=limit,
        )
        return run.reuse.chunks

    @staticmethod
    def _followup_prompt(request: ChatRequest, run: _Run, context: TurnContext) -> FollowupPrompt | None:
        """Conversation context for Call 2, only when the question continues an earlier one."""
        res = run.resolution
        if res is None or res.intent not in ("CONTINUE", "EXPAND"):
            return None  # first question or NEW_TOPIC: earlier turns must not colour the answer
        exchanges = context.by_turn_id(res.referenced_turn_ids)[-HISTORY_EXCHANGES_FOR_ANSWER:]
        if not exchanges:
            return None
        return FollowupPrompt(original_message=request.message, history=answer_history_block(exchanges))

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
            followup_intent=run.resolution.intent if run.resolution else None,
            reused_chunk_ids=[c.id for c in run.reuse.chunks] if run.reuse else [],
            dropped_reuse=dict(run.reuse.dropped) if run.reuse else {},
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
        conflict_analysis: ConflictAnalysis | None = None,
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
            conflict_analysis=conflict_analysis,
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
        run.cached = True
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
