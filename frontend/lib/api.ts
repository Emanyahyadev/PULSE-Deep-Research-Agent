export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type EventOut = {
  id: number;
  state: string;
  message: string;
  payload: Record<string, unknown> | null;
  created_at: string;
};

export type SourceRef = {
  id: string;
  url: string;
  title: string | null;
  domain: string | null;
  score: number;
  is_cited: boolean;
  citation_number: number | null;
};

export type ReportState = "planning" | "searching" | "reading" | "writing" | "done" | "failed";

export type Report = {
  id: string;
  query: string;
  state: ReportState;
  title: string | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  search_plan: { queries: string[]; rationale: string } | null;
  report_markdown: string | null;
  citations: { n: number; source_id: string }[];
  sources: SourceRef[];
  events: EventOut[];
};

export async function createReport(query: string): Promise<Report> {
  const res = await fetch(`${API_BASE}/api/reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error(`Failed to start research (${res.status})`);
  return res.json();
}

export async function getReport(id: string): Promise<Report> {
  const res = await fetch(`${API_BASE}/api/reports/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load report (${res.status})`);
  return res.json();
}

export async function listReports(): Promise<Report[]> {
  const res = await fetch(`${API_BASE}/api/reports`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load reports (${res.status})`);
  return res.json();
}

export async function retryReport(id: string): Promise<Report> {
  const res = await fetch(`${API_BASE}/api/reports/${id}/retry`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to retry (${res.status})`);
  return res.json();
}
