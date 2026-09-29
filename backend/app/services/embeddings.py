"""Embeddings via an OpenAI-compatible endpoint (NVIDIA NIM by default).

NIM retrieval models are asymmetric: use input_type="query" for the report
question and input_type="passage" for evidence chunks.

Client policy: a fresh AsyncOpenAI client per call (async context manager).
The Agents SDK's shared client is bound to the persistent background loop, so
binding this module's calls to the same loop forever would deadlock the loop's
DNS/worker threads. Per-call clients are cheap and loop-safe.
"""

import logging

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


async def embed_texts(texts: list[str], input_type: str = "query") -> list[list[float]]:
    """Return one vector per text, in input order. Empty input → empty output.

    input_type: "query" (search queries) or "passage" (documents/chunks) —
    passed through to NIM retrieval models; ignored by providers that don't
    use it.
    """
    if not texts:
        return []
    async with AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.embeddings_base_url,
    ) as client:
        resp = await client.embeddings.create(
            model=settings.embedding_model,
            input=[t[:6000] for t in texts],
            extra_body={"input_type": input_type, "truncate": "END"},
        )
    vectors = [d.embedding for d in resp.data]
    logger.info(
        "embedded %d %s texts (dim=%s, model=%s)",
        len(vectors),
        input_type,
        len(vectors[0]) if vectors else 0,
        settings.embedding_model,
    )
    return vectors
