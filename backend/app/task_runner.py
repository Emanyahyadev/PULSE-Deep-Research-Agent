"""Background execution policy for report runs.

Runs the orchestrator on a single persistent asyncio event loop (a dedicated
daemon thread) instead of per-run loops. This matters because shared async
HTTP clients (the Agents SDK / OpenAI client, Qdrant client) bind connections
to the loop they were created on — a fresh loop per run triggers
"Event loop is closed" errors on every run after the first.
"""

import asyncio
import logging
import threading

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None
_lock = threading.Lock()


def get_loop() -> asyncio.AbstractEventLoop:
    """Return the persistent background loop, creating it on first use."""
    global _loop
    with _lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            threading.Thread(
                target=_loop.run_forever,
                name="report-runner-loop",
                daemon=True,
            ).start()
            logger.info("persistent background loop started")
        return _loop


def submit_run(report_id: str, run_coro_factory) -> None:
    """Schedule a report run on the persistent loop.

    run_coro_factory is a zero-arg callable returning a coroutine, so each run
    gets a fresh coroutine (and thus fresh per-run resources like Qdrant/HTTP
    clients) bound to the persistent loop.
    """
    loop = get_loop()
    asyncio.run_coroutine_threadsafe(run_coro_factory(), loop)
    logger.info("report %s scheduled on background loop", report_id)
