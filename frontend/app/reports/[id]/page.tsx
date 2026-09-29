"use client";

import { useParams } from "next/navigation";
import React, { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { getReport, retryReport, type Report, type ReportState } from "@/lib/api";

const STEPS: { key: ReportState; label: string }[] = [
  { key: "planning", label: "Planning" },
  { key: "searching", label: "Searching" },
  { key: "reading", label: "Reading" },
  { key: "writing", label: "Writing" },
  { key: "done", label: "Complete" },
];

const STEP_STATUS_TEXT: Record<string, string> = {
  planning: "Decomposing the question into a search plan…",
  searching: "Searching the web for evidence…",
  reading: "Reading sources and indexing evidence…",
  writing: "Writing the report…",
};

const STAGE_ORDER = STEPS.map((s) => s.key);

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [highlightSid, setHighlightSid] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const feedRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    async function poll() {
      try {
        const r = await getReport(id!);
        if (cancelled) return;
        setReport(r);
        setError(null);
        if (!["done", "failed"].includes(r.state)) {
          timer.current = setTimeout(poll, 2000);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load report");
        timer.current = setTimeout(poll, 5000);
      }
    }
    poll();

    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [id]);

  const numBySid = useMemo(() => {
    const m: Record<string, number> = {};
    for (const c of report?.citations ?? []) m[c.source_id] = c.n;
    return m;
  }, [report?.citations]);

  const isRunning = report ? !["done", "failed"].includes(report.state) : false;

  // Keep the live event feed pinned to the newest event while the run progresses.
  useEffect(() => {
    if (isRunning && feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [report?.events.length, isRunning]);

  const { citedSources, uncitedSources } = useMemo(() => {
    const all = report?.sources ?? [];
    return {
      citedSources: all
        .filter((s) => s.is_cited)
        .sort((a, b) => (a.citation_number ?? 99) - (b.citation_number ?? 99)),
      uncitedSources: all.filter((s) => !s.is_cited),
    };
  }, [report?.sources]);

  if (error && !report) {
    return (
      <main className="container" style={{ paddingTop: 32 }}>
        <div className="error-box">{error}</div>
      </main>
    );
  }

  if (!report) {
    return (
      <main className="container" style={{ paddingTop: 32 }}>
        <p className="hero-sub">Loading…</p>
      </main>
    );
  }

  const failed = report.state === "failed";

  // Which stage did a failed run die in? Derived from the last stage event.
  let failedAt = -1;
  if (failed) {
    const lastStageEvent = [...report.events]
      .reverse()
      .find((ev) => STAGE_ORDER.includes(ev.state as ReportState) && ev.state !== "done");
    failedAt = lastStageEvent ? STAGE_ORDER.indexOf(lastStageEvent.state as ReportState) : 0;
  }
  const activeIdx = STAGE_ORDER.indexOf(report.state);

  async function onCopy() {
    if (!report?.report_markdown) return;
    await navigator.clipboard.writeText(report.report_markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function onRetry() {
    if (!report) return;
    const r = await retryReport(report.id);
    setReport(r);
  }

  function onCiteClick(sid: string) {
    setHighlightSid(sid);
    document.getElementById(`src-${sid}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => setHighlightSid(null), 2200);
  }

  return (
    <main>
      {/* ---------- Header ---------- */}
      <div className="container report-header">
        <a href="/" className="backlink">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M15 18l-6-6 6-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          All research
        </a>

        <h1>{report.title ?? report.query}</h1>

        <div className="header-meta">
          <StatusBadge state={report.state} />
          <span>Started {new Date(report.created_at).toLocaleString()}</span>
          {report.completed_at && (
            <span>
              · Completed {new Date(report.completed_at).toLocaleTimeString()}
            </span>
          )}
          <span className="spacer" />
          {report.report_markdown && (
            <button type="button" className="btn-accent" onClick={onCopy}>
              {copied ? "Copied ✓" : "Copy markdown"}
            </button>
          )}
          {failed && (
            <button type="button" className="btn-ghost" onClick={onRetry}>
              Retry
            </button>
          )}
        </div>
      </div>

      {/* ---------- Overview band: workflow + search plan in one view ---------- */}
      <div className="container overview-grid">
        <section className="panel progress-panel" aria-label="Workflow progress">
          <h2>Workflow</h2>
          <nav className="stepper" aria-label="Research progress">
            {STEPS.map((s, i) => {
              const cls = failed
                ? i < failedAt
                  ? "done"
                  : i === failedAt
                    ? "failed"
                    : ""
                : report.state === "done" || i < activeIdx
                  ? "done"
                  : i === activeIdx
                    ? "active"
                    : "";
              return (
                <span key={s.key} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  {i > 0 && <span className="step-sep" aria-hidden="true" />}
                  <span className={`step ${cls}`} aria-current={cls === "active" ? "step" : undefined}>
                    <span className="step-dot" aria-hidden="true" />
                    {s.label}
                  </span>
                </span>
              );
            })}
          </nav>
          {isRunning && (
            <p className="progress-hint" aria-live="polite">
              {STEP_STATUS_TEXT[report.state] ?? "Working…"}
            </p>
          )}
          {report.events.length > 0 && (
            <div className="event-feed" ref={feedRef}>
              <ul className="timeline">
                {report.events.map((ev) => (
                  <li key={ev.id}>
                    <time>{new Date(ev.created_at).toLocaleTimeString()}</time>
                    <span className="tag">{ev.state}</span>
                    <span>{ev.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="panel plan-panel" aria-label="Search plan">
          <h2>Search plan</h2>
          {report.search_plan ? (
            <>
              <ol className="plan-queries">
                {report.search_plan.queries.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ol>
              {report.search_plan.rationale && (
                <p className="plan-rationale">{report.search_plan.rationale}</p>
              )}
            </>
          ) : (
            <p className="plan-empty">
              {failed
                ? "No plan was produced for this run."
                : "The planner is decomposing your question into search queries…"}
            </p>
          )}
        </section>
      </div>

      {/* ---------- Report + sources ---------- */}
      <div className={`container report-grid ${report.sources.length > 0 ? "has-sources" : ""}`}>
        <div>
          {report.error && <div className="error-box">{report.error}</div>}

          {isRunning && (
            <div className="report-card" aria-live="polite">
              <p style={{ fontSize: 14, color: "var(--text-2)", marginTop: 0 }}>
                {STEP_STATUS_TEXT[report.state] ?? "Working…"}
              </p>
              <div className="skel h1" />
              <div className="skel p" style={{ width: "100%" }} />
              <div className="skel p" style={{ width: "96%" }} />
              <div className="skel p" style={{ width: "92%" }} />
              <div className="skel h2" />
              <div className="skel p" style={{ width: "98%" }} />
              <div className="skel p" style={{ width: "88%" }} />
            </div>
          )}

          {failed && !report.report_markdown && (
            <div className="empty">
              <p>The research run failed before producing a report.</p>
              <button type="button" className="btn-primary" onClick={onRetry}>
                Retry research
              </button>
            </div>
          )}

          {report.report_markdown && (
            <div className="report-card">
              <article className="md">
                <ReactMarkdown
                  components={{
                    p: ({ children }) => <p>{renderCitationChips(children, numBySid, onCiteClick)}</p>,
                    li: ({ children }) => <li>{renderCitationChips(children, numBySid, onCiteClick)}</li>,
                    h1: ({ children }) => <h1>{children}</h1>,
                    h2: ({ children }) => <h2>{children}</h2>,
                    h3: ({ children }) => <h3>{children}</h3>,
                    blockquote: ({ children }) => <blockquote>{renderCitationChips(children, numBySid, onCiteClick)}</blockquote>,
                  }}
                >
                  {report.report_markdown}
                </ReactMarkdown>
              </article>
            </div>
          )}
        </div>

        {/* Sources column */}
        {report.sources.length > 0 && (
          <aside>
            <div className="sources-panel">
              <h2>
                Sources{" "}
                <span style={{ color: "var(--text-3)", fontWeight: 450 }}>
                  ({report.citations.length} cited of {report.sources.length})
                </span>
              </h2>

              {citedSources.length > 0 && (
                <>
                  <h3 className="src-group-label">Cited in report</h3>
                  {citedSources.map((s) => (
                    <SourceRow key={s.id} source={s} highlight={highlightSid === s.id} />
                  ))}
                </>
              )}

              {uncitedSources.length > 0 && (
                <>
                  <h3 className="src-group-label">
                    {citedSources.length > 0 ? "Also retrieved" : "Retrieved sources"}
                  </h3>
                  {uncitedSources.map((s) => (
                    <SourceRow key={s.id} source={s} highlight={highlightSid === s.id} />
                  ))}
                </>
              )}
            </div>
          </aside>
        )}
      </div>
    </main>
  );
}

function SourceRow({ source: s, highlight }: { source: { id: string; url: string; title: string | null; domain: string | null; is_cited: boolean; citation_number: number | null }; highlight: boolean }) {
  return (
    <a
      id={`src-${s.id}`}
      href={s.url}
      target="_blank"
      rel="noreferrer"
      className={`source-row ${highlight ? "highlight" : ""} ${s.is_cited ? "" : "uncited-row"}`}
    >
      <span className={`n ${s.is_cited ? "" : "uncited"}`} aria-hidden="true">
        {s.citation_number ?? "–"}
      </span>
      <span className="body">
        <span className="t">{s.title ?? s.url}</span>
        <span className="d" style={{ display: "block" }}>{s.domain}</span>
      </span>
      <svg className="ext" width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M7 17L17 7M17 7H9M17 7v8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </a>
  );
}

/* Render [n] markers in markdown text as clickable chips. */
function renderCitationChips(
  children: React.ReactNode,
  numBySid: Record<string, number>,
  onCiteClick: (sid: string) => void
): React.ReactNode {
  // numBySid maps source_id → n, but in markdown we only have [n]; build n → n chip.
  function process(node: React.ReactNode): React.ReactNode {
    if (typeof node === "string") {
      const parts = node.split(/(\[\d{1,2}\])/g);
      if (parts.length === 1) return node;
      return parts.map((part, i) => {
        const m = part.match(/^\[(\d{1,2})\]$/);
        if (!m) return part;
        const n = Number(m[1]);
        return (
          <button
            key={i}
            type="button"
            className="cite"
            title="Show source"
            onClick={() => {
              // Find source by citation number via the ordered citations array.
              const sid = Object.entries(numBySid).find(([, v]) => v === n)?.[0];
              if (sid) onCiteClick(sid);
            }}
          >
            {n}
          </button>
        );
      });
    }
    if (Array.isArray(node)) return <>{node.map((c, i) => <span key={i}>{process(c)}</span>)}</>;
    if (React.isValidElement(node)) {
      const el = node as React.ReactElement<{ children?: React.ReactNode }>;
      if (el.props?.children) {
        return React.cloneElement(el, {}, process(el.props.children));
      }
    }
    return node;
  }
  return process(children);
}

function StatusBadge({ state }: { state: ReportState }) {
  const cls = state === "done" ? "done" : state === "failed" ? "failed" : "running";
  const label =
    state === "done"
      ? "Complete"
      : state === "failed"
        ? "Failed"
        : state === "planning"
          ? "Planning"
          : state === "searching"
            ? "Searching"
            : state === "reading"
              ? "Reading"
              : "Writing";
  return (
    <span className={`badge ${cls}`} role="status" aria-label={`Status: ${label}`}>
      <span className="dot" aria-hidden="true" />
      {label}
    </span>
  );
}
