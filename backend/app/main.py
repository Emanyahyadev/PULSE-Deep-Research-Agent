"""FastAPI entrypoint. Lifespan initializes Postgres schema and the Qdrant collection.

Startup coroutines execute on the persistent background loop (the same loop
that runs report jobs) so every async resource in the process shares one loop
affinity.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routes import router
from app.services import vector
from app.task_runner import get_loop

logging.basicConfig(level=logging.INFO)


def _run_on_bg_loop(coro) -> None:
    import asyncio

    future = asyncio.run_coroutine_threadsafe(coro, get_loop())
    future.result(timeout=30)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    _fail_stale_reports()
    try:
        _run_on_bg_loop(vector.ensure_collection())
    except Exception as exc:  # noqa: BLE001 — Qdrant may start after the API
        logging.getLogger(__name__).warning("Qdrant not ready at startup: %s", exc)
    yield


def _fail_stale_reports() -> None:
    """Observable state hygiene: runs orphaned by a restart are marked failed,
    never left in a non-terminal state forever."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Report, ReportEvent

    db = SessionLocal()
    try:
        stale = (
            db.execute(
                select(Report).where(
                    Report.state.notin_(["done", "failed"])  # type: ignore[attr-defined]
                )
                .where(Report.id.isnot(None))  # type: ignore[attr-defined]
            )
            .scalars()
            .all()
        )
        for r in stale:
            r.state = "failed"
            r.error = "Interrupted by server restart"
            db.add(
                ReportEvent(
                    report_id=r.id,
                    state="failed",
                    message="Interrupted by server restart",
                )
            )
        if stale:
            db.commit()
            logging.getLogger(__name__).warning("marked %d stale reports as failed", len(stale))
    finally:
        db.close()


app = FastAPI(title="Autonomous Research Agent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/healthz")
async def healthz() -> dict:
    from qdrant_client import AsyncQdrantClient

    from app.config import settings

    qdrant_ok = True
    try:
        client = AsyncQdrantClient(url=settings.qdrant_url, timeout=3)
        await client.get_collections()
        await client.close()
    except Exception:  # noqa: BLE001
        qdrant_ok = False
    return {"status": "ok", "qdrant": qdrant_ok}
