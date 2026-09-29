"""Qdrant semantic memory: index curated chunks, retrieve report-scoped top-k.

Scoped memory invariant: every search filters on report_id, so one query's
evidence can never contaminate another's.

Client policy: a fresh AsyncQdrantClient per call, always closed in finally.
This keeps every connection bound to whichever loop is running the call —
required because runs execute on a persistent background loop while startup
and health checks run on uvicorn's loop.
"""

import logging
import uuid

from qdrant_client import AsyncQdrantClient, models

from app.config import settings
from app.schemas import CuratedChunk

logger = logging.getLogger(__name__)


def _client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.qdrant_url)


async def ensure_collection() -> None:
    """Idempotently create the chunk collection with cosine distance."""
    client = _client()
    try:
        exists = await client.collection_exists(settings.qdrant_collection)
        if exists:
            return
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=models.VectorParams(
                size=settings.embedding_dim,
                distance=models.Distance.COSINE,
            ),
        )
        # Payload indexes make the per-report filter fast.
        await client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name="report_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        await client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name="source_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        logger.info("created qdrant collection %s", settings.qdrant_collection)
    finally:
        await client.close()


async def delete_report_points(report_id: str) -> None:
    """Remove all vectors belonging to one report.

    Called before re-indexing (retry, multi-round) so stale points can never
    occupy top_k retrieval slots after their sources were replaced.
    """
    client = _client()
    try:
        await client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="report_id", match=models.MatchValue(value=report_id)
                        )
                    ]
                )
            ),
        )
    finally:
        await client.close()


async def index_chunks(
    report_id: str,
    chunk_ids: list[str],
    chunks: list[CuratedChunk],
    vectors: list[list[float]],
) -> int:
    """Upsert chunk vectors with payload {report_id, source_id}. Returns count."""
    if not chunks:
        return 0
    points = [
        models.PointStruct(
            id=uuid.UUID(cid) if _is_uuid(cid) else uuid.uuid5(uuid.NAMESPACE_URL, cid),
            vector=vec,
            payload={
                "report_id": report_id,
                "source_id": c.source_id,
                "ordinal": c.ordinal,
                "text": c.text,
            },
        )
        for cid, c, vec in zip(chunk_ids, chunks, vectors, strict=False)
    ]
    client = _client()
    try:
        await client.upsert(collection_name=settings.qdrant_collection, points=points, wait=True)
    finally:
        await client.close()
    logger.info("indexed %d chunks for report %s", len(points), report_id)
    return len(points)


async def retrieve_for_report(
    report_id: str, query_embedding: list[float], top_k: int | None = None
) -> list[dict]:
    """Report-scoped vector search: the only retrieval path in the system.

    Returns [{source_id, text, score, ordinal}] ordered by similarity.
    """
    client = _client()
    try:
        hits = await client.query_points(
            collection_name=settings.qdrant_collection,
            query=query_embedding,
            limit=top_k or settings.top_k,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="report_id", match=models.MatchValue(value=report_id)
                    )
                ]
            ),
            with_payload=True,
        )
    finally:
        await client.close()

    out = []
    for p in hits.points:
        payload = p.payload or {}
        out.append(
            {
                "source_id": payload.get("source_id"),
                "text": payload.get("text", ""),
                "ordinal": payload.get("ordinal", 0),
                "score": p.score,
            }
        )
    return out


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
