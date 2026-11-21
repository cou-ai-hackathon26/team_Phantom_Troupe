import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import admin, chat, evaluation, feedback, health, sources, user_docs, voice
from app.core.config import settings
from app.core.logging import setup_logging

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Load the BM25 index once, and warm the embedding model in the background so the first
    # question does not pay the model-load cost. Failures are logged; /health reports them.
    from app.models.embedding_client import get_embedding_client
    from app.services.retrieval_service import get_retriever

    try:
        get_retriever()
    except FileNotFoundError as exc:
        logger.warning("index not loaded", extra={"data": {"error": str(exc)}})
    warm = asyncio.create_task(asyncio.to_thread(get_embedding_client().embed_query, "warm up"))
    yield
    warm.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="AdhikarAI API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (
        health.router,
        voice.router,
        chat.router,
        sources.router,
        feedback.router,
        evaluation.router,
        user_docs.router,
        admin.router,
    ):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
