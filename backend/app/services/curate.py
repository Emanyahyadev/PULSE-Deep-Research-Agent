"""Curation: filter, dedupe, rank, and segment evidence into retrievable units.

- Dedupe by normalized URL (and near-dupes by domain+path stem)
- Rank with a deterministic heuristic (domain diversity, content length, rank positions)
- Chunk into ~chunk_size passages with overlap so retrieval can select precise spans
"""

import logging
import re
from collections import defaultdict

from urllib.parse import urlparse

from app.config import settings
from app.schemas import CuratedChunk, CuratedSource, RawSource

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_url(url: str) -> str:
    """Canonical form for dedupe: lowercase host, strip tracking params/fragments."""
    try:
        p = urlparse(url)
        query = "&".join(
            sorted(kv for kv in p.query.split("&") if kv and not kv.lower().startswith(("utm_", "ref", "fbclid", "gclid")))
        )
        return f"{p.scheme.lower()}://{p.netloc.lower()}{p.path.rstrip('/')}" + (f"?{query}" if query else "")
    except Exception:
        return url.strip().lower()


def dedupe(sources: list[RawSource]) -> list[RawSource]:
    """Keep the first occurrence per normalized URL."""
    seen: set[str] = set()
    out: list[RawSource] = []
    for s in sources:
        key = normalize_url(s.url)
        if key in seen or not key:
            continue
        seen.add(key)
        out.append(s)
    return out


def rank(sources: list[RawSource]) -> list[CuratedSource]:
    """Deterministic heuristic ranking (no LLM in the hot path).

    score = w1 * search_rank_quality + w2 * content_length + w3 * domain_spread
    Domain spread: demote the 3rd+ source from the same domain to force diversity.
    """
    if not sources:
        return []

    domain_counts: dict[str, int] = defaultdict(int)
    max_len = max((len(s.raw_content or "") + len(s.snippet or "")) for s in sources) or 1

    ranked: list[CuratedSource] = []
    for s in sources:
        len_score = (len(s.raw_content or "") + len(s.snippet or "")) / max_len
        domain_counts[s.domain or "unknown"] += 1
        diversity_penalty = 0.5 ** (domain_counts[s.domain or "unknown"] - 1)  # 1, .5, .25...
        search_quality = 1.0 / (1 + s.search_rank - 1)
        score = (
            0.35 * search_quality
            + 0.35 * len_score
            + 0.30 * diversity_penalty
        )
        ranked.append(CuratedSource(**s.model_dump(), score=round(score, 4)))

    ranked.sort(key=lambda c: c.score, reverse=True)
    return ranked


def chunk_source(source_id: str, text: str) -> list[CuratedChunk]:
    """Split one source's text into overlapping passages (~settings.chunk_size chars).

    Semantic separability: store passages, not whole pages, so vector search can
    select exactly the relevant spans at write time.
    """
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if not text:
        return []

    size = settings.chunk_size
    overlap = settings.chunk_overlap
    chunks: list[CuratedChunk] = []
    start = 0
    ordinal = 0
    while start < len(text):
        end = min(start + size, len(text))
        # Don't cut mid-word unless we're at the tail
        if end < len(text):
            space = text.rfind(" ", start + size - 120, end)
            if space != -1 and space > start:
                end = space
        chunks.append(
            CuratedChunk(
                source_id=source_id,
                ordinal=ordinal,
                text=text[start:end].strip(),
                char_start=start,
                char_end=end,
            )
        )
        ordinal += 1
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks
