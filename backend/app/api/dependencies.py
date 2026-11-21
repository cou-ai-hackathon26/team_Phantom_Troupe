from functools import lru_cache

from fastapi import HTTPException

from app.core.constants import RATE_LIMIT_TEXT
from app.models.llm_client import get_llm_client
from app.services.answer_cache import get_answer_cache
from app.services.orchestrator import Orchestrator
from app.services.retrieval_service import Retriever, get_retriever

INDEX_MISSING_TEXT = "নথির সূচি এখনো তৈরি হয়নি। আগে ingestion চালান।"


def retriever_dep() -> Retriever:
    try:
        return get_retriever()
    except FileNotFoundError as exc:
        raise HTTPException(503, detail={"code": "index_missing", "message": INDEX_MISSING_TEXT}) from exc


@lru_cache
def _orchestrator() -> Orchestrator:
    return Orchestrator(get_retriever(), get_llm_client(), get_answer_cache())


def orchestrator_dep() -> Orchestrator:
    retriever_dep()  # surface a clear 503 if the index is missing
    return _orchestrator()


def http_error(code: str, message: str = RATE_LIMIT_TEXT, status: int = 503) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})
