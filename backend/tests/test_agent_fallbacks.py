"""Tests for LLM-layer resilience: hard per-stage timeouts and the
deterministic fallbacks that must keep the bounded pipeline running
when the planner or writer hangs or fails.
"""

import asyncio

from app.agents import research_agents as ra


class _FakeResult:
    def __init__(self, final_output):
        self.final_output = final_output


def _runner_raising(exc):
    """Fake Runner whose .run always raises (simulates a hung/failed LLM)."""

    class _FakeRunner:
        @staticmethod
        async def run(agent, prompt, **kwargs):
            raise exc

    return _FakeRunner


def _runner_returning(final_output):
    class _FakeRunner:
        @staticmethod
        async def run(agent, prompt, **kwargs):
            return _FakeResult(final_output)

    return _FakeRunner


# --- planner fallback ---


def test_make_search_plan_falls_back_when_llm_hangs(monkeypatch):
    monkeypatch.setattr(ra, "Runner", _runner_raising(asyncio.TimeoutError("hung")))
    plan = asyncio.run(ra.make_search_plan("what is quantum error correction"))
    assert len(plan.queries) <= ra.settings.max_queries
    assert "fallback" in plan.rationale.lower()
    assert any("quantum error correction" in q for q in plan.queries)


def test_make_search_plan_caps_llm_queries(monkeypatch):
    out = '{"queries": ["a", "b", "c", "d", "e", "f", "g"], "rationale": "r"}'
    monkeypatch.setattr(ra, "Runner", _runner_returning(out))
    plan = asyncio.run(ra.make_search_plan("test question for cap enforcement"))
    assert len(plan.queries) == ra.settings.max_queries


# --- replan resilience ---


def test_replan_failure_keeps_previous_plan(monkeypatch):
    monkeypatch.setattr(ra, "Runner", _runner_raising(RuntimeError("llm down")))
    assert asyncio.run(ra.replan("q", ["q1"], 1)) is None


def test_replan_respects_query_budget(monkeypatch):
    out = '{"queries": ["a", "b", "c"], "rationale": "r"}'
    monkeypatch.setattr(ra, "Runner", _runner_returning(out))
    # 4 of MAX_QUERIES already ran → only 1 slot remains
    plan = asyncio.run(ra.replan("q", ["q1", "q2", "q3", "q4"], 1))
    assert plan is not None
    assert len(plan.queries) == ra.settings.max_queries - 4


# --- writer fallback ---


def test_write_report_falls_back_to_cited_digest(monkeypatch):
    monkeypatch.setattr(ra, "Runner", _runner_raising(asyncio.TimeoutError("writer hung")))
    sid_a, sid_b = "1" * 8 + "-1111-1111-1111-111111111111", "2" * 8 + "-2222-2222-2222-222222222222"
    evidence = [
        {"source_id": sid_a, "url": "u", "title": "T", "text": "evidence text " * 40, "score": 1},
        {"source_id": sid_b, "url": "u", "title": "T", "text": "more evidence " * 90, "score": 0.9},
    ]
    report = asyncio.run(ra.write_report("q?", evidence))
    assert "Research Digest" in report
    # The digest must keep provenance pointers so citation integrity still holds
    assert sid_a in report and sid_b in report


def test_write_report_rejects_empty_evidence():
    import pytest

    with pytest.raises(RuntimeError):
        asyncio.run(ra.write_report("q?", []))


# --- timeout wrapper itself ---


def test_timeout_wrapper_enforces_deadline(monkeypatch):
    class _HangingRunner:
        @staticmethod
        async def run(agent, prompt, **kwargs):
            await asyncio.sleep(999)

    monkeypatch.setattr(ra, "Runner", _HangingRunner)
    import pytest

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(ra._run_with_timeout(ra.planner_agent, "p", 0.05))
