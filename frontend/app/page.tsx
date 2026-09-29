"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createReport, listReports, type Report, type ReportState } from "@/lib/api";

const EXAMPLES = [
  "What are the latest advances in solid-state batteries?",
  "How do sales prediction models work?",
  "What is the current state of carbon capture technology?",
];

const PLACEHOLDERS = [
  "Ask about a technology, a market, a scientific question…",
  "e.g. How do fusion startups approach tokamak design?",
  "e.g. What do researchers say about intermittent fasting?",
  "e.g. Compare vector databases for a RAG pipeline…",
];

export default function Home() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<Report[]>([]);
  const [placeholderIdx, setPlaceholderIdx] = useState(0);

  useEffect(() => {
    listReports()
      .then(setRecent)
      .catch(() => {});
  }, []);

  useEffect(() => {
    const t = setInterval(() => setPlaceholderIdx((i) => (i + 1) % PLACEHOLDERS.length), 4000);
    return () => clearInterval(t);
  }, []);

  async function start(q: string) {
    if (q.trim().length < 8) {
      setError("Please enter a research question (at least 8 characters).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const report = await createReport(q.trim());
      router.push(`/reports/${report.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setBusy(false);
    }
  }

  return (
    <main className="home-dark">
      <section className="hero">
        <div className="container">
          <p className="eyebrow">Pulse</p>
          <h1>Autonomous Research Agent</h1>
          <p className="hero-sub">
            Ask anything. Pulse plans its own searches, reads the web, and writes a fully cited
            report — every claim traced to its source.
          </p>

          <form
            className="query-card"
            onSubmit={(e) => {
              e.preventDefault();
              start(query);
            }}
          >
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={PLACEHOLDERS[placeholderIdx]}
              aria-label="Research question"
              rows={2}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  start(query);
                }
              }}
            />
            <div className="query-actions">
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy ? "Starting…" : "Start research"}
              </button>
            </div>
          </form>

          <div className="example-chips" role="list" aria-label="Example questions">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                type="button"
                className="chip"
                role="listitem"
                onClick={() => {
                  setQuery(ex);
                  start(ex);
                }}
                disabled={busy}
              >
                {ex}
              </button>
            ))}
          </div>

          {error && (
            <div className="error-box" style={{ marginTop: 16, maxWidth: 760 }}>
              {error}
            </div>
          )}
        </div>
      </section>

      <section className="container" id="recent" style={{ paddingBottom: 80 }}>
        {recent.length === 0 ? (
          <div className="empty">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.5" />
              <path d="M20 20l-3.5-3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <p>No research yet — start with a question above.</p>
            <div className="example-chips">
              {EXAMPLES.slice(0, 2).map((ex) => (
                <button key={ex} type="button" className="chip" onClick={() => start(ex)}>
                  {ex}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            <h2 className="section-title">Recent research</h2>
            <div className="recent-list">
              {recent.map((r) => (
                <a key={r.id} href={`/reports/${r.id}`} className="recent-row">
                  <StatusBadge state={r.state} />
                  <span className="q">{r.title ?? r.query}</span>
                  <span className="time">{relTime(r.created_at)}</span>
                  <svg className="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </a>
              ))}
            </div>
          </>
        )}
      </section>
    </main>
  );
}

// Local helpers — Next.js App Router pages may only export the default component.
function StatusBadge({ state }: { state: ReportState }) {
  const cls =
    state === "done" ? "done" : state === "failed" ? "failed" : "running";
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

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}
