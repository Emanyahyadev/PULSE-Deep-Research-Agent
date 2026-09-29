"""Planner and writer agents (OpenAI Agents SDK over an OpenAI-compatible endpoint).

The LLM decides what to search and how to write; everything around it —
caps, retries, validation, persistence — is deterministic.

Routing: the endpoint is OpenAI-compatible (NVIDIA NIM by default), so we point
the Agents SDK's default client at it, switch the SDK to the chat-completions
API, and disable OpenAI-hosted tracing. Structured contracts are enforced by
deterministic parsing + Pydantic validation rather than provider-side
json_schema, so any compatible provider works.
"""

import asyncio
import logging
import re

from agents import Agent, ModelSettings, Runner, set_default_openai_api, set_default_openai_client, set_tracing_disabled
from agents.models.openai_provider import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from app.agents.prompts import PLANNER_SYSTEM_PROMPT, WRITER_SYSTEM_PROMPT
from app.config import settings
from app.schemas import Citation, SearchPlan

logger = logging.getLogger(__name__)

# --- Route the Agents SDK through the configured OpenAI-compatible endpoint ---
set_default_openai_client(
    AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.llm_base_url)
)
set_default_openai_api("chat_completions")
set_tracing_disabled(True)

# --- Agents (the decision-making layer) ---

# Explicit model instances: the SDK's string parsing rejects unknown provider
# prefixes like "nvidia/", so we bind the NIM client + model id directly.
# Bounded timeouts/retries: an intelligence-layer outage must fail fast into
# the deterministic fallbacks, not stall the whole run.
_nim_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.llm_base_url,
    timeout=90.0,
    max_retries=1,
)

planner_agent = Agent(
    name="ResearchPlanner",
    instructions=PLANNER_SYSTEM_PROMPT,
    model=OpenAIChatCompletionsModel(model=settings.planner_model, openai_client=_nim_client),
    model_settings=ModelSettings(temperature=0.2),
)

writer_agent = Agent(
    name="ReportWriter",
    instructions=WRITER_SYSTEM_PROMPT,
    model=OpenAIChatCompletionsModel(model=settings.writer_model, openai_client=_nim_client),
    model_settings=ModelSettings(temperature=0.3),
)


async def _run_with_timeout(agent: Agent, prompt: str, timeout: float):
    """Run an agent call under a hard per-stage timeout.

    A hung LLM endpoint must surface quickly so the caller's deterministic
    fallback can take over, instead of eating the run's wall-clock budget
    (a 90s client timeout + one retry once cost a run 182s of its 240s).
    """
    return await asyncio.wait_for(Runner.run(agent, prompt), timeout=timeout)


async def make_search_plan(query: str, max_queries: int | None = None) -> SearchPlan:
    """Stage: Planning — decompose q into P(q) = {s1..sk}, k ≤ cap.

    Falls back to a deterministic plan if the planner LLM is unavailable,
    so the bounded pipeline keeps running (degraded, never stuck).
    """
    cap = max_queries or settings.max_queries
    prompt = (
        f"Question: {query}\n\n"
        f"Produce at most {cap} distinct, non-overlapping search queries "
        f"as JSON: {{\"queries\": [\"...\"], \"rationale\": \"...\"}}. JSON only."
    )
    try:
        result = await _run_with_timeout(planner_agent, prompt, settings.planner_timeout)
        plan = _parse_json_loose(result.final_output, SearchPlan)
    except Exception as exc:  # noqa: BLE001 — LLM outage must not stop the run
        logger.warning("planner LLM failed (%s); using deterministic fallback plan", exc)
        return SearchPlan(
            queries=_fallback_queries(query, cap),
            rationale="Deterministic fallback plan (planner LLM unavailable).",
        )
    # Enforce bounds deterministically — never trust the LLM's self-restraint.
    plan.queries = plan.queries[:cap]
    return plan


def _fallback_queries(query: str, cap: int) -> list[str]:
    base = [
        query,
        f"{query} explained",
        f"{query} advantages and disadvantages",
        f"{query} real world examples",
        f"{query} criticism and limitations",
    ]
    return base[:cap]


async def replan(query: str, ran_queries: list[str], source_count: int) -> SearchPlan | None:
    """Second round: target gaps if evidence is thin. Returns None if budget is exhausted."""
    remaining = settings.max_queries - len(ran_queries)
    if remaining <= 0:
        return None
    prompt = (
        f"The previous search round produced thin evidence ({source_count} sources).\n"
        f"Original question: {query}\n"
        f"Queries already run: {', '.join(ran_queries) or 'none'}\n"
        f"Produce up to {remaining} NEW, differently-phrased queries targeting the gaps. "
        "Avoid repeating previous queries. Respond only with the structured search plan."
    )
    try:
        result = await _run_with_timeout(planner_agent, prompt, settings.planner_timeout)
        plan = _parse_json_loose(result.final_output, SearchPlan)
    except Exception as exc:  # noqa: BLE001 — a failed replan keeps the previous plan
        logger.warning("replan failed (%s); keeping previous plan", exc)
        return None
    plan.queries = plan.queries[:remaining]
    return plan


# --- Evidence block rendering for the writer ---


def render_evidence(chunks: list[dict]) -> str:
    """Deterministically render retrieved chunks into the writer's input."""
    lines = []
    for i, c in enumerate(chunks, start=1):
        lines.append(
            f"[EVIDENCE {i}] source_id={c['source_id']} url={c['url']} title={c['title'] or ''}"
        )
        lines.append(c["text"].strip())
        lines.append("")
    return "\n".join(lines)


async def write_report(query: str, evidence_chunks: list[dict], timeout: float | None = None) -> str:
    """Stage: Synthesis — transform evidence into a structured, cited report.

    Falls back to a deterministic evidence digest (still fully cited) if the
    writer LLM is unavailable — grounding and citation integrity hold either way.
    """
    if not evidence_chunks:
        raise RuntimeError("No evidence chunks available for synthesis")

    user_prompt = (
        f"Question: {query}\n\n"
        f"EVIDENCE ({len(evidence_chunks)} chunks):\n\n"
        f"{render_evidence(evidence_chunks)}\n\n"
        "Write the report now, following the structure and citation rules."
    )
    try:
        result = await _run_with_timeout(writer_agent, user_prompt, timeout or settings.writer_timeout)
        report = result.final_output
        if isinstance(report, str) and len(report.strip()) >= 100:
            return report.strip()
        raise RuntimeError("empty or trivial report")
    except Exception as exc:  # noqa: BLE001 — LLM outage must not waste the evidence
        logger.warning("writer LLM failed (%s); emitting evidence digest", exc)
        return _evidence_digest(query, evidence_chunks)


def _evidence_digest(query: str, evidence_chunks: list[dict]) -> str:
    """Deterministic, fully cited fallback report built from the evidence itself."""
    lines = [
        f"# Research Digest: {query}",
        "",
        "## Summary",
        "The report writer model was temporarily unavailable, so this is a "
        "deterministic digest of the collected evidence rather than a synthesized "
        "narrative. Every statement below traces to a stored source.",
        "",
        "## Evidence Digest",
    ]
    for i, c in enumerate(evidence_chunks, start=1):
        text = " ".join((c.get("text") or "").split())
        excerpt = text[:420] + ("…" if len(text) > 420 else "")
        lines.append(f"{i}. {excerpt} [source:{c['source_id']}]")
    lines += [
        "",
        "## Limitations",
        "This digest quotes evidence rather than synthesizing it; re-run the "
        "question later for a full narrative report.",
    ]
    return "\n".join(lines)


# --- Citation integrity: citations(R) ⊆ sources(R) ---

# Accepts every bracket style the writer has been observed emitting:
# [source:<uuid>], 【source:<uuid>】, [1], [1, 2], [1][2] — plus stray
# bare <uuid> tokens left behind by partial bracket stripping.
_ANY_CITATION_RE = re.compile(
    r"(?:(?P<ob>\[|【)\s*(?:source\s*:\s*)?(?P<sid1>[0-9a-fA-F-]{36})\s*(?P=ob)?\s*】?\]?)"
    r"|(?:(?P<ob2>\[|【)(?P<nums>[0-9]{1,2}(?:\s*,\s*[0-9]{1,2})*)\s*(?P=ob2)?\s*】?\]?)"
)
_BARE_UUID_RE = re.compile(r"(?<![\[])([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")


def _extract_citation_ids(text: str, source_ids: set[str]) -> tuple[set[str], list[str]]:
    """Extract all cited source ids from any citation syntax.

    Number citations are resolved via their first occurrence in the text:
    the n-th distinct UUID mentioned maps to number n.
    Returns (valid_ids, dropped_raw_citations).
    """
    ordered_uuids: list[str] = []
    num_map: dict[str, str] = {}

    def _register(uuid_str: str) -> str:
        if uuid_str not in ordered_uuids:
            ordered_uuids.append(uuid_str)
        return str(ordered_uuids.index(uuid_str) + 1)

    for m in _ANY_CITATION_RE.finditer(text):
        if m.group("sid1"):
            _register(m.group("sid1"))
        elif m.group("nums"):
            for n in re.split(r"\s*,\s*", m.group("nums")):
                num_map.setdefault(n.strip(), "")

    # Resolve number citations to uuids by order of uuid appearance.
    for i, sid in enumerate(ordered_uuids, start=1):
        num_map[str(i)] = sid

    valid: set[str] = set()
    dropped: list[str] = []
    for m in _ANY_CITATION_RE.finditer(text):
        if m.group("sid1"):
            sid = m.group("sid1")
            (valid.add if sid in source_ids else (lambda s: dropped.append(s)))(sid)
        elif m.group("nums"):
            for n in re.split(r"\s*,\s*", m.group("nums")):
                sid = num_map.get(n.strip())
                if sid and sid in source_ids:
                    valid.add(sid)
                elif not sid:
                    dropped.append(f"[unresolved:{n.strip()}]")

    # Stray bare uuids (brackets stripped by a prior cleanup) count as citations too.
    for m in _BARE_UUID_RE.finditer(text):
        sid = m.group(1)
        if sid in source_ids:
            valid.add(sid)
        elif sid not in [d.strip("[]") for d in dropped]:
            dropped.append(m.group(0))

    return valid, dropped


def _number_citations(
    markdown: str, source_ids: set[str], num_to_sid: dict[str, str]
) -> tuple[str, list[Citation], list[Citation]]:
    """Normalize every citation syntax to numbered chips [1], [2] (first-use order).

    Canonical order = first appearance of each valid source's uuid in the text;
    number citations are resolved against that same order, then renumbered,
    so all styles collapse to one consistent numbering.
    """
    # Canonical first-use order of valid sources, across ALL citation styles:
    # uuid citations, number citations (resolved via the evidence map), bare uuids.
    ordered: list[str] = []

    def _register(sid: str | None) -> None:
        if sid and sid in source_ids and sid not in ordered:
            ordered.append(sid)

    for m in _ANY_CITATION_RE.finditer(markdown):
        _register(m.group("sid1"))
        if m.group("nums"):
            for n in re.split(r"\s*,\s*", m.group("nums")):
                _register(num_to_sid.get(n.strip()))
    for m in _BARE_UUID_RE.finditer(markdown):
        _register(m.group(1))

    num_of = {sid: i + 1 for i, sid in enumerate(ordered)}

    valid: list[Citation] = []
    dropped: list[Citation] = []

    def _sub(m: re.Match) -> str:
        sid = m.group("sid1")
        if sid is not None:
            # uuid citation in some bracket style
            if sid in source_ids:
                return f"[{num_of[sid]}]"
            dropped.append(Citation(source_id=sid, span_text=""))
            return ""
        # number citation, possibly a list like [1, 2]
        parts = [n.strip() for n in re.split(r"\s*,\s*", m.group("nums"))]
        out_tokens = []
        seen = set()
        for n in parts:
            sid = num_to_sid.get(n)
            if sid and sid in source_ids:
                if num_of[sid] not in seen:
                    seen.add(num_of[sid])
                    out_tokens.append(f"[{num_of[sid]}]")
            else:
                dropped.append(Citation(source_id=f"unresolved:{n}", span_text=""))
        return "".join(out_tokens)

    out = _ANY_CITATION_RE.sub(_sub, markdown)

    def _sub_bare(m: re.Match) -> str:
        sid = m.group(1)
        if sid in source_ids:
            return f"[{num_of[sid]}]"
        return ""

    out = _BARE_UUID_RE.sub(_sub_bare, out)

    for sid in ordered:
        valid.append(Citation(source_id=sid, span_text=""))

    # Collapse adjacent duplicate markers like [1][1].
    out = re.sub(r"(?:\[(\d{1,2})\]\s*){2,}", lambda m: f"[{m.group(1)}]", out)
    return out, valid, dropped


def validate_citations(
    report_markdown: str, evidence_chunks: list[dict]
) -> tuple[str, list[Citation], list[Citation]]:
    """Integrity gate + normalization.

    The writer sees evidence numbered [EVIDENCE 1..N], each with a source_id.
    Citations therefore resolve as:
      - [source:<uuid>]/【source:<uuid>】 -> that source directly
      - [n] / [1, 2] -> the n-th evidence chunk's source
    Anything resolving to a source that is NOT in the evidence set is dropped
    (integrity invariant). Valid citations are renumbered to compact [n]
    chips in source first-use order.

    Returns (cleaned_markdown, valid_citations, dropped_citations).
    """
    source_ids = {c["source_id"] for c in evidence_chunks}
    num_to_sid = {
        str(i): c["source_id"] for i, c in enumerate(evidence_chunks, start=1)
    }
    return _number_citations(report_markdown, source_ids, num_to_sid)


# --- Deterministic contract enforcement for structured outputs ---


def _parse_json_loose(content: str, schema: type[SearchPlan]) -> SearchPlan:
    """Extract the first valid JSON object from a response, tolerating prose,
    code fences, and reasoning-model think blocks."""
    import json

    text = (content or "").strip()
    # 1) fenced code block, if present
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = []
    if fence:
        candidates.append(fence.group(1))
    # 2) first balanced JSON object via raw_decode at each '{' — robust to
    #    stray braces in surrounding prose/reasoning.
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(text[idx:])
                candidates.append(obj)
                break
            except json.JSONDecodeError:
                continue
    for cand in candidates:
        try:
            data = cand if isinstance(cand, dict) else json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            continue
        try:
            return schema.model_validate(data)
        except Exception:  # noqa: BLE001 — try next candidate
            continue
    raise RuntimeError(f"Planner returned unparseable JSON: {(content or '')[:300]}")


__all__ = [
    "make_search_plan",
    "replan",
    "render_evidence",
    "write_report",
    "validate_citations",
    "SearchPlan",
]
