"""Web fallback: Tavily search over an allow-list of official websites.

Used only when local retrieval is weak (orchestrator), before Call 2, so the 2-call limit holds.
Only Call 1's search_query is sent (never the raw message or a personal document), results outside
the allow-list are dropped, and any failure returns [] so the answer pipeline never breaks.
Web text is evidence, never instructions (the answer prompt says so).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
MIN_PASSAGE_CHARS = 80
MAX_PASSAGE_CHARS = 2500
WEB_ACT = "সরকারি ওয়েবসাইট"


@dataclass
class WebPassageSource:
    """A passage from an official website, shaped like a ChunkRecord for the prompt and validator."""

    id: str
    title: str
    citation: str
    text: str
    source_url: str
    act: str = WEB_ACT
    part: int | None = None
    notes: list[str] = field(default_factory=list)
    kind: str = "web"

    @property
    def section(self) -> str:
        return urlparse(self.source_url).hostname or ""

    def embedding_text(self) -> str:
        return f"{self.citation}\n{self.text}"


def allowed_domains() -> list[str]:
    return [d.strip().lower() for d in settings.web_allowed_domains.split(",") if d.strip()]


def is_allowed(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


class WebSearchClient:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None, retries: int = 2) -> None:
        self._api_key = api_key
        self._client = client
        self._retries = retries

    async def _post(self, payload: dict) -> dict:
        client = self._client or httpx.AsyncClient(timeout=settings.web_timeout_s)
        try:
            for attempt in range(self._retries + 1):
                resp = await client.post(TAVILY_URL, json=payload, headers={"Authorization": f"Bearer {self._api_key}"})
                if (resp.status_code == 429 or resp.status_code >= 500) and attempt < self._retries:
                    await asyncio.sleep(2**attempt)  # rate limit or server error: back off and retry
                    continue
                resp.raise_for_status()
                return resp.json()
            return {}
        finally:
            if self._client is None:
                await client.aclose()

    async def search(self, query: str) -> list[WebPassageSource]:
        domains = allowed_domains()
        payload = {
            "query": query[:400],
            "search_depth": "advanced",  # returns the most relevant chunks of each page as `content`
            "chunks_per_source": 3,
            "max_results": settings.web_max_results,
            "include_domains": domains,
        }
        try:
            data = await self._post(payload)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("web search failed", extra={"data": {"error": type(exc).__name__}})
            return []
        passages: list[WebPassageSource] = []
        for i, result in enumerate(data.get("results", []), start=1):
            url = str(result.get("url") or "")
            text = " ".join(str(result.get("content") or "").split())
            if not is_allowed(url, domains) or len(text) < MIN_PASSAGE_CHARS:
                continue  # outside the allow-list, or too little text to cite
            title = " ".join(str(result.get("title") or "").split())[:120] or (urlparse(url).hostname or url)
            host = urlparse(url).hostname or ""
            passages.append(
                WebPassageSource(
                    id=f"web:{i}:{url[:200]}",
                    title=title,
                    citation=f"{title} ({host})",
                    text=text[:MAX_PASSAGE_CHARS],
                    source_url=url,
                )
            )
        logger.info("web search", extra={"data": {"results": len(data.get("results", [])), "kept": len(passages)}})
        return passages


@lru_cache
def get_web_search() -> WebSearchClient | None:
    """None when the fallback is switched off or no key is configured."""
    if not settings.web_fallback or settings.tavily_api_key is None:
        return None
    return WebSearchClient(settings.tavily_api_key.get_secret_value())
