"""Evidence acquisition: web search via Tavily, Exa, or DuckDuckGo (the perception layer).

Provider is selected by settings.search_provider ("tavily" | "exa" | "duckduckgo").
The DuckDuckGo provider is keyless: SERP results come from the ddgs library
(run in a worker thread), and page content is fetched + extracted from the
top results so evidence has real depth, not just snippets.
Raw discovery only — curation happens in curate.py.
"""

import asyncio
import html as html_mod
import logging
import re
import threading

import httpx

from app.config import settings
from app.schemas import RawSource

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
EXA_SEARCH_URL = "https://api.exa.ai/search"

_UA = "Mozilla/5.0 (compatible; ResearchAgent/0.1)"


async def web_search(query: str, max_results: int | None = None) -> list[RawSource]:
    """Discover raw web evidence for a single query, via the configured provider."""
    if settings.search_provider == "exa":
        k = max_results or settings.exa_results_per_query
        return await _exa_search(query, k)
    if settings.search_provider == "duckduckgo":
        k = max_results or settings.tavily_results_per_query
        return await _duckduckgo_search(query, k)
    k = max_results or settings.tavily_results_per_query
    return await _tavily_search(query, k)


# --- Tavily ---


async def _tavily_search(query: str, k: int) -> list[RawSource]:
    body = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": "advanced",
        "max_results": k,
        "include_answer": False,
        "include_raw_content": True,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(TAVILY_SEARCH_URL, json=body)
        resp.raise_for_status()
        data = resp.json()

    sources: list[RawSource] = []
    for i, item in enumerate(data.get("results", []), start=1):
        url = item.get("url", "")
        if not url:
            continue
        raw = item.get("raw_content") or ""
        content = item.get("content") or ""
        sources.append(
            RawSource(
                url=url,
                title=item.get("title"),
                snippet=content,
                raw_content=raw if len(raw) > len(content) else "",
                search_rank=i,
                domain=_domain_of(url),
            )
        )
    logger.info("tavily query=%r -> %d sources", query, len(sources))
    return sources


# --- Exa ---


async def _exa_search(query: str, k: int) -> list[RawSource]:
    headers = {"x-api-key": settings.exa_api_key, "Content-Type": "application/json"}
    body = {
        "query": query,
        "numResults": k,
        "contents": {"text": {"maxCharacters": 8000}},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(EXA_SEARCH_URL, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    sources = []
    for i, item in enumerate(data.get("results", []), start=1):
        url = item.get("url", "")
        if not url:
            continue
        text = item.get("text") or ""
        sources.append(
            RawSource(
                url=url,
                title=item.get("title"),
                snippet=text[:1500],
                raw_content=text,
                search_rank=i,
                domain=_domain_of(url),
            )
        )
    logger.info("exa query=%r -> %d sources", query, len(sources))
    return sources


# --- DuckDuckGo (keyless) ---


_ddg_lock = threading.Lock()


def _ddg_serp(query: str, k: int) -> list[dict]:
    from ddgs import DDGS

    # Serialize ddgs calls across worker threads (rate-limit protection).
    with _ddg_lock:
        with DDGS() as d:
            return list(d.text(query, max_results=k))


async def _duckduckgo_search(query: str, k: int) -> list[RawSource]:
    try:
        rows = await asyncio.to_thread(_ddg_serp, query, k)
    except Exception as exc:  # noqa: BLE001 — SERP failure = no sources for this query
        logger.warning("ddg serp failed for %r: %s", query, exc)
        return []

    rows = [r for r in rows if r.get("href")]
    # Fetch page content for all results concurrently (best-effort).
    pages = await asyncio.gather(
        *(_fetch_page_text(r["href"]) for r in rows), return_exceptions=True
    )

    sources: list[RawSource] = []
    for i, (r, page) in enumerate(zip(rows, pages, strict=False), start=1):
        url = r["href"]
        body = (r.get("body") or "").strip()
        page_text = page if isinstance(page, str) else ""
        sources.append(
            RawSource(
                url=url,
                title=r.get("title"),
                snippet=body[:1500],
                raw_content=page_text if len(page_text) > len(body) else "",
                search_rank=i,
                domain=_domain_of(url),
            )
        )
    logger.info("duckduckgo query=%r -> %d sources", query, len(sources))
    return sources


async def _fetch_page_text(url: str, max_chars: int = 12000) -> str:
    """Best-effort extraction of readable text from a web page."""
    try:
        async with httpx.AsyncClient(
            timeout=10, follow_redirects=True, headers={"User-Agent": _UA}
        ) as client:
            resp = await client.get(url)
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype and "text/plain" not in ctype:
                return ""
            html = resp.text
    except Exception:  # noqa: BLE001 — any fetch failure just yields no content
        return ""

    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    text = html_mod.unescape(html)
    return re.sub(r"\s+", " ", text).strip()[:max_chars]


def _domain_of(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc.lower() or url[:200]
    except Exception:
        return url[:200]
