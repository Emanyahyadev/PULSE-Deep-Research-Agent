"""The orchestrator: a deterministic, bounded, observable state machine wrapped
around non-deterministic intelligence.

State machine: planning → searching → reading → writing → done (or failed).
Every transition is logged to report_events; every stage respects the caps in
config; the citation integrity invariant is enforced before acceptance.
"""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.agents.research_agents import make_search_plan, replan, validate_citations, write_report
from app.config import settings
from app.db import SessionLocal
from app.models import Chunk, Report, ReportEvent, Source
from app.services import curate, embeddings, search, vector

logger = logging.getLogger(__name__)

TERMINAL_STATES = {"done", "failed"}


class BudgetExceeded(Exception):
    pass


def _event(db: DBSession, report_id: str, state: str, message: str, payload: dict | None = None) -> None:
    db.add(ReportEvent(report_id=report_id, state=state, message=message, payload=payload))
    db.commit()


def _set_state(db: DBSession, report: Report, state: str, message: str, payload: dict | None = None) -> None:
    report.state = state
    _event(db, report.id, state, message, payload)


def _deadline() -> float:
    return time.monotonic() + settings.max_total_seconds


def _assert_budget(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise BudgetExceeded(f"Run exceeded max_total_seconds={settings.max_total_seconds}")


async def run_report(report_id: str) -> None:
    """Execute the full pipeline for one report. Runs as a background task."""
    db = SessionLocal()
    deadline = _deadline()
    all_sources: list = []
    ran_queries: list[str] = []
    try:
        report = db.get(Report, report_id)
        if report is None:
            raise RuntimeError(f"report {report_id} not found")
        query = report.query

        # ---------- Stage 1: Planning ----------
        _set_state(db, report, "planning", "Decomposing question into a search plan")
        plan = await make_search_plan(query)
        report.plan_rationale = plan.rationale
        report.search_plan = {"queries": plan.queries, "rationale": plan.rationale}
        _event(db, report_id, "planning", f"Plan ready: {len(plan.queries)} queries", {"queries": plan.queries})
        db.commit()

        for round_no in range(1, settings.max_rounds + 1):
            _assert_budget(deadline)

            # ---------- Stage 2: Searching (acquisition) ----------
            _set_state(db, report, "searching", f"Round {round_no}: acquiring evidence")
            fresh_queries = [q for q in plan.queries if q not in ran_queries]
            ran_queries.extend(fresh_queries)

            # Parallel acquisition: queries are independent, so wall-clock is
            # the slowest query rather than the sum of all of them.
            results = await asyncio.gather(
                *(search.web_search(q) for q in fresh_queries), return_exceptions=True
            )
            round_sources: list = []
            for q, res in zip(fresh_queries, results):
                if isinstance(res, Exception):  # noqa: BLE001 — one query failing must not kill the run
                    logger.warning("search failed for %r: %s", q, res)
                    _event(db, report_id, "searching", f"Query failed: {q[:80]}", {"error": str(res)})
                    continue
                round_sources.extend(res)
            if fresh_queries:
                _event(
                    db,
                    report_id,
                    "searching",
                    f"{len(fresh_queries)} queries executed, {len(round_sources)} raw results",
                )
            all_sources.extend(round_sources)

            # ---------- Stage 3: Reading (curation + indexing) ----------
            _set_state(db, report, "reading", "Deduping, ranking, chunking, and indexing evidence")
            unique = curate.dedupe(all_sources)
            ranked = curate.rank(unique)[: settings.max_sources]  # bound: MAX_SOURCES

            db.query(Source).filter(Source.report_id == report_id).delete()
            db.query(Chunk).filter(Chunk.report_id == report_id).delete()
            db.flush()
            # Stale vectors from a previous round/retry would occupy top_k
            # retrieval slots, so purge them before indexing fresh chunks.
            try:
                await vector.delete_report_points(report_id)
            except Exception as exc:  # noqa: BLE001 — Qdrant hiccup must not kill the run
                logger.warning("vector purge failed for %s: %s", report_id, exc)

            source_rows: dict[str, Source] = {}
            all_chunks: list[tuple[str, curate.CuratedChunk]] = []
            for cs in ranked:
                sid = str(uuid.uuid4())
                row = Source(
                    id=sid,
                    report_id=report_id,
                    url=cs.url,
                    title=cs.title,
                    snippet=cs.snippet[:2000],
                    raw_content=(cs.raw_content or cs.snippet or "")[:20000],
                    score=cs.score,
                    domain=cs.domain,
                    search_rank=cs.search_rank,
                )
                db.add(row)
                source_rows[sid] = row

                text = (cs.raw_content or cs.snippet or "").strip()
                for ch in curate.chunk_source(sid, text):
                    cid = str(uuid.uuid4())
                    db.add(
                        Chunk(
                            id=cid,
                            source_id=sid,
                            report_id=report_id,
                            ordinal=ch.ordinal,
                            text=ch.text,
                            char_start=ch.char_start,
                            char_end=ch.char_end,
                        )
                    )
                    all_chunks.append((cid, ch))
            db.commit()

            _event(db, report_id, "reading", f"Curated {len(ranked)} sources, {len(all_chunks)} chunks")

            # ---------- Indexing: embed chunks into Qdrant (semantic memory) ----------
            if all_chunks:
                _assert_budget(deadline)
                try:
                    vectors_out = await embeddings.embed_texts(
                        [ch.text for _, ch in all_chunks], input_type="passage"
                    )
                    await vector.index_chunks(
                        report_id,
                        [cid for cid, _ in all_chunks],
                        [ch for _, ch in all_chunks],
                        vectors_out,
                    )
                except Exception as exc:  # noqa: BLE001 — indexing failure must not kill the run
                    logger.warning("chunk indexing failed: %s", exc)
                    _event(db, report_id, "reading", f"Indexing failed: {exc}")

            if all_chunks or round_no == settings.max_rounds:
                break  # enough evidence — or no budget left to try again

            # Evidence is thin: try one replan targeting the gaps
            _event(db, report_id, "reading", "Evidence thin; replanning")
            plan = (await replan(query, ran_queries, len(ranked))) or plan
            if not plan.queries:
                break

        # ---------- Stage 4: Retrieval (report-scoped) ----------
        _assert_budget(deadline)
        _set_state(db, report, "reading", "Retrieving relevant passages (vector search, report-scoped)")
        if all_chunks:
            qvec = (await embeddings.embed_texts([query]))[0]
            hits = await vector.retrieve_for_report(report_id, qvec)
            # Deterministic hydration: map hits back to their stored chunks/sources
            chunk_rows = db.execute(select(Chunk).where(Chunk.report_id == report_id)).scalars().all()
            by_id = {c.id: c for c in chunk_rows}
            source_rows = {s.id: s for s in db.execute(select(Source).where(Source.report_id == report_id)).scalars().all()}
            evidence = []
            seen_texts: set[str] = set()
            for h in hits:
                # hits carry source_id + text from payload; use them directly
                if not h["source_id"] or h["source_id"] not in source_rows:
                    continue
                key = h["text"][:200]
                if key in seen_texts:
                    continue
                seen_texts.add(key)
                src = source_rows[h["source_id"]]
                evidence.append(
                    {
                        "source_id": h["source_id"],
                        "url": src.url,
                        "title": src.title,
                        "text": h["text"],
                        "score": h["score"],
                    }
                )
            _event(db, report_id, "reading", f"Retrieved {len(evidence)} evidence chunks")
        else:
            evidence = []
            _event(db, report_id, "reading", "No evidence collected")

        # ---------- Stage 5: Writing (synthesis) ----------
        _assert_budget(deadline)
        if not evidence:
            report.state = "failed"
            report.error = "No usable evidence was collected for this question."
            _event(db, report_id, "failed", report.error)
            db.commit()
            return

        _set_state(db, report, "writing", f"Synthesizing report from {len(evidence)} chunks")
        report_markdown = await write_report(query, evidence)

        # ---------- Citation integrity gate ----------
        # The writer sees [EVIDENCE 1..N]; validate against that map, then
        # normalize every citation style to numbered [n] chips.
        cleaned, valid, dropped = validate_citations(report_markdown, evidence)
        if dropped:
            _event(
                db,
                report_id,
                "writing",
                f"Dropped {len(dropped)} invalid citations (integrity invariant)",
                {"dropped": [d.source_id for d in dropped][:10]},
            )

        # Citation map in first-use order: [{"n": 1, "source_id": ...}, ...]
        seen: dict[str, int] = {}
        citation_map: list[dict] = []
        for v in valid:
            if v.source_id not in seen:
                seen[v.source_id] = len(seen) + 1
                citation_map.append({"n": seen[v.source_id], "source_id": v.source_id})

        cited_ids = set(seen.keys())
        for sid in cited_ids:
            if sid in source_rows:
                source_rows[sid].is_cited = True

        report.title = _extract_title(cleaned) or query[:280]
        report.report_markdown = cleaned
        report.citations = citation_map
        report.state = "done"
        report.completed_at = datetime.now(UTC)
        _event(
            db,
            report_id,
            "done",
            f"Report complete: {len(valid)} valid citations across {len(cited_ids)} sources",
            {"valid_citations": len(valid), "cited_sources": len(cited_ids)},
        )
        db.commit()
        logger.info("report %s done", report_id)

    except BudgetExceeded as exc:
        db.rollback()
        report = db.get(Report, report_id)
        if report:
            report.state = "failed"
            report.error = str(exc)
            _event(db, report_id, "failed", str(exc))
            db.commit()
    except Exception as exc:  # noqa: BLE001 — terminal failure must be recorded
        logger.exception("report %s failed", report_id)
        db.rollback()
        report = db.get(Report, report_id)
        if report:
            report.state = "failed"
            report.error = f"{type(exc).__name__}: {exc}"
            _event(db, report_id, "failed", report.error)
            db.commit()
    finally:
        db.close()


def _extract_title(markdown: str) -> str | None:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()[:280]
    return None
