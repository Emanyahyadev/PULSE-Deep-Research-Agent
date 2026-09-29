"""Unit tests for the citation integrity gate: citations(R) ⊆ sources(R).

Covers every citation style the writer has been observed emitting:
[source:<uuid>], 【source:<uuid>】, [n], [n, m], bare uuids — plus the
first-use-order renumbering.
"""

from app.agents.research_agents import validate_citations

SID_A = "11111111-1111-1111-1111-111111111111"
SID_B = "22222222-2222-2222-2222-222222222222"
SID_C = "33333333-3333-3333-3333-333333333333"
UNKNOWN = "99999999-9999-9999-9999-999999999999"

EVIDENCE = [
    {"source_id": SID_A, "url": "https://a.com", "title": "A", "text": "alpha", "score": 0.9},
    {"source_id": SID_B, "url": "https://b.com", "title": "B", "text": "beta", "score": 0.8},
    {"source_id": SID_C, "url": "https://c.com", "title": "C", "text": "gamma", "score": 0.7},
]


def _ids(valid):
    return [c.source_id for c in valid]


def test_number_citations_resolve_to_evidence_sources():
    md = f"Claim one. [1] Claim two. [2] More [3]."
    cleaned, valid, dropped = validate_citations(md, EVIDENCE)
    assert _ids(valid) == [SID_A, SID_B, SID_C]  # first-use order
    assert dropped == []
    assert "[1]" in cleaned and "[2]" in cleaned and "[3]" in cleaned


def test_uuid_citations_are_renumbered_to_first_use_order():
    md = f"Start with B [source:{SID_B}], then A [source:{SID_A}]."
    cleaned, valid, dropped = validate_citations(md, EVIDENCE)
    assert _ids(valid) == [SID_B, SID_A]
    assert dropped == []
    # B was used first, so B becomes [1] and A becomes [2]
    assert f"[source:{SID_B}]" not in cleaned
    assert cleaned.index("[1]") < cleaned.index("[2]")


def test_citations_to_unknown_sources_are_dropped():
    md = f"Good [source:{SID_A}] bad [source:{UNKNOWN}]."
    cleaned, valid, dropped = validate_citations(md, EVIDENCE)
    assert _ids(valid) == [SID_A]
    assert any(UNKNOWN in d.source_id for d in dropped)
    assert UNKNOWN not in cleaned  # invalid marker removed from the text


def test_unresolved_numbers_are_dropped():
    md = "Good [1] bogus [7]."
    cleaned, valid, dropped = validate_citations(md, EVIDENCE)
    assert _ids(valid) == [SID_A]
    assert any("7" in d.source_id for d in dropped)
    assert "[7]" not in cleaned


def test_full_width_bracket_uuid_style():
    md = f"Claim 【source:{SID_A}】."
    cleaned, valid, dropped = validate_citations(md, EVIDENCE)
    assert _ids(valid) == [SID_A]
    assert dropped == []
    assert "[1]" in cleaned


def test_bare_uuid_counts_as_citation():
    md = f"Claim {SID_A}."
    cleaned, valid, dropped = validate_citations(md, EVIDENCE)
    assert _ids(valid) == [SID_A]
    assert dropped == []
    assert SID_A not in cleaned
    assert "[1]" in cleaned


def test_list_citations_expand_and_dedupe():
    md = f"A claim [1, 2] more [1]."
    cleaned, valid, dropped = validate_citations(md, EVIDENCE)
    assert _ids(valid) == [SID_A, SID_B]
    assert dropped == []
    assert cleaned.count("[1]") == 1  # adjacent duplicate collapsed


def test_adjacent_duplicate_markers_collapse():
    md = f"Claim [1][1] [source:{SID_A}]."
    cleaned, valid, _ = validate_citations(md, EVIDENCE)
    assert cleaned.count("[1]") == 1


def test_mixed_styles_share_one_numbering():
    md = f"Uuid first [source:{SID_B}], then numbers [1] and [3]."
    cleaned, valid, dropped = validate_citations(md, EVIDENCE)
    assert dropped == []
    # B first (from uuid), then A ([1] → evidence 1), then C ([3] → evidence 3)
    assert _ids(valid) == [SID_B, SID_A, SID_C]


def test_no_citations_yields_no_valid():
    md = "A paragraph with no citations at all."
    cleaned, valid, dropped = validate_citations(md, EVIDENCE)
    assert valid == [] and dropped == []
    assert cleaned == md  # untouched
