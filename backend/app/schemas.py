"""Pydantic contracts between API, agents, services, and frontend."""

from datetime import datetime

from pydantic import BaseModel, Field


# --- Agent structured outputs (contracts the LLM must satisfy) ---

class SearchPlan(BaseModel):
    """P(q): the planner's decomposition of the question into a search strategy."""

    queries: list[str] = Field(description="Distinct, non-overlapping search queries (k ≤ max_queries).")
    rationale: str = Field(description="Why this decomposition answers the question.")


class Citation(BaseModel):
    """A provenance pointer: must resolve to a stored source id."""

    source_id: str
    span_text: str = Field(default="", description="Verbatim evidence span the citation supports.")


# --- Service-level contracts (search + curation) ---

class RawSource(BaseModel):
    """A source as discovered by Tavily, before curation."""

    url: str
    title: str | None = None
    snippet: str = ""
    raw_content: str = ""
    search_rank: int = 0
    domain: str | None = None


class CuratedSource(RawSource):
    """A source after dedupe + ranking; carries the curation score."""

    score: float = Field(default=0.0, description="Curation rank score, higher = better")


class CuratedChunk(BaseModel):
    """A semantic unit of evidence ready for embedding + indexing."""

    source_id: str
    ordinal: int
    text: str
    char_start: int
    char_end: int


# --- API contracts ---

class SourceRef(BaseModel):
    id: str
    url: str
    title: str | None = None
    domain: str | None = None
    score: float = 0.0
    is_cited: bool = False
    citation_number: int | None = None  # [n] used in the report text, if cited


class EventOut(BaseModel):
    id: int
    state: str
    message: str
    payload: dict | None = None
    created_at: datetime


class ReportOut(BaseModel):
    id: str
    query: str
    state: str
    title: str | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    search_plan: dict | None = None
    report_markdown: str | None = None
    citations: list[dict] = []  # [{"n": 1, "source_id": "..."}, ...] in first-use order
    sources: list[SourceRef] = []
    events: list[EventOut] = []


class CreateReportRequest(BaseModel):
    query: str = Field(min_length=8, max_length=600)


class CitationCheck(BaseModel):
    """Result of the integrity invariant: citations(R) ⊆ sources(R)."""

    ok: bool
    valid_citations: list[Citation] = []
    dropped: list[Citation] = []
