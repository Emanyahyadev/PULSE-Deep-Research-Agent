"""API surface: start runs, observe state, fetch cited results."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Report, ReportEvent, Source
from app.orchestrator import run_report
from app.schemas import CreateReportRequest, EventOut, ReportOut, SourceRef
from app.task_runner import submit_run

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("", response_model=ReportOut, status_code=201)
def create_report(req: CreateReportRequest, db: Session = Depends(get_db)) -> ReportOut:
    report = Report(id=str(uuid.uuid4()), query=req.query.strip(), state="planning")
    db.add(report)
    db.add(
        ReportEvent(
            report_id=report.id,
            state="planning",
            message="Report created; queuing research run",
        )
    )
    db.commit()

    # Execute on the persistent background loop; state is observable via the API.
    submit_run(report.id, lambda rid=report.id: run_report(rid))

    return _to_report_out(db, report)


@router.get("", response_model=list[ReportOut])
def list_reports(db: Session = Depends(get_db)) -> list[ReportOut]:
    reports = db.execute(select(Report).order_by(Report.created_at.desc()).limit(50)).scalars().all()
    return [_to_report_out(db, r, with_events=False) for r in reports]


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: str, db: Session = Depends(get_db)) -> ReportOut:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return _to_report_out(db, report)


@router.post("/{report_id}/retry", response_model=ReportOut, status_code=202)
def retry_report(report_id: str, db: Session = Depends(get_db)) -> ReportOut:
    """Re-run a failed report through the full pipeline (fresh attempt, same id)."""
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.state not in {"done", "failed"}:
        raise HTTPException(status_code=409, detail="Report is still running")

    # Reset state; sources stay for provenance but will be replaced on re-run.
    report.state = "planning"
    report.error = None
    report.title = None
    report.report_markdown = None
    report.citations = None
    report.completed_at = None
    db.add(ReportEvent(report_id=report.id, state="planning", message="Retry requested"))
    db.commit()

    submit_run(report.id, lambda rid=report.id: run_report(rid))
    return _to_report_out(db, report)


@router.get("/{report_id}/events", response_model=list[EventOut])
def get_events(report_id: str, db: Session = Depends(get_db)) -> list[EventOut]:
    if db.get(Report, report_id) is None:
        raise HTTPException(status_code=404, detail="Report not found")
    events = (
        db.execute(
            select(ReportEvent)
            .where(ReportEvent.report_id == report_id)
            .order_by(ReportEvent.created_at.asc(), ReportEvent.id.asc())
        )
        .scalars()
        .all()
    )
    return [
        EventOut(id=e.id, state=e.state, message=e.message, payload=e.payload, created_at=e.created_at)
        for e in events
    ]


def _to_report_out(db: Session, report: Report, with_events: bool = True) -> ReportOut:
    sources = (
        db.execute(select(Source).where(Source.report_id == report.id).order_by(Source.score.desc()))
        .scalars()
        .all()
    )
    events = []
    if with_events:
        events = (
            db.execute(
                select(ReportEvent)
                .where(ReportEvent.report_id == report.id)
                .order_by(ReportEvent.created_at.asc(), ReportEvent.id.asc())
            )
            .scalars()
            .all()
        )
    citations = report.citations or []
    num_by_sid = {c["source_id"]: c["n"] for c in citations if isinstance(c, dict)}

    return ReportOut(
        id=report.id,
        query=report.query,
        state=report.state,
        title=report.title,
        error=report.error,
        created_at=report.created_at,
        completed_at=report.completed_at,
        search_plan=report.search_plan,
        report_markdown=report.report_markdown,
        citations=citations,
        sources=[
            SourceRef(
                id=s.id,
                url=s.url,
                title=s.title,
                domain=s.domain,
                score=s.score,
                is_cited=s.id in num_by_sid,
                citation_number=num_by_sid.get(s.id),
            )
            for s in sources
        ],
        events=[
            EventOut(id=e.id, state=e.state, message=e.message, payload=e.payload, created_at=e.created_at)
            for e in events
        ],
    )
