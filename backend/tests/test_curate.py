"""Unit tests for curation: URL normalization, dedupe, ranking, chunking."""

from app.schemas import RawSource
from app.services import curate


def _src(url: str, raw: str = "", snippet: str = "s", rank: int = 1, domain: str | None = None) -> RawSource:
    return RawSource(
        url=url,
        title="t",
        snippet=snippet,
        raw_content=raw,
        search_rank=rank,
        domain=domain,
    )


# --- normalize_url ---


def test_normalize_url_strips_tracking_params_and_case():
    assert (
        curate.normalize_url("HTTPS://Example.com/Path/?utm_source=x&id=2")
        == "https://example.com/Path?id=2"
    )


def test_normalize_url_strips_trailing_slash_and_fragment():
    assert (
        curate.normalize_url("https://example.com/a/#frag")
        == "https://example.com/a"
    )


# --- dedupe ---


def test_dedupe_keeps_first_occurrence_per_normalized_url():
    sources = [
        _src("https://example.com/a?utm_campaign=z"),
        _src("https://example.com/a"),
        _src("https://other.com/b"),
    ]
    out = curate.dedupe(sources)
    assert len(out) == 2
    assert {s.url for s in out} == {"https://example.com/a?utm_campaign=z", "https://other.com/b"}


# --- rank ---


def test_rank_prefers_content_length_and_diversity():
    sources = [
        _src("https://a.com/1", raw="x" * 4000, rank=1, domain="a.com"),
        _src("https://a.com/2", raw="x" * 4000, rank=2, domain="a.com"),
        _src("https://b.com/3", raw="x" * 4000, rank=3, domain="b.com"),
    ]
    ranked = curate.rank(sources)
    scores = {c.url: c.score for c in ranked}
    # Same length: earlier search rank wins
    assert scores["https://a.com/1"] > scores["https://a.com/2"]
    # Same length + rank: the 2nd source from the same domain is demoted
    assert scores["https://a.com/2"] < scores["https://b.com/3"]


def test_rank_is_deterministic():
    sources = [_src(f"https://{d}.com/{i}", raw="x" * 100 * i, rank=i) for i, d in enumerate("abc", start=1)]
    first = [c.url for c in curate.rank(list(sources))]
    second = [c.url for c in curate.rank(list(sources))]
    assert first == second


# --- chunk_source ---


def test_chunk_source_splits_long_text_with_overlap():
    text = " ".join(f"word{i}" for i in range(1000))  # ~7000 chars
    chunks = curate.chunk_source("sid", text)
    assert len(chunks) > 1
    # Contiguity: each chunk starts within the overlap window of the previous end
    for prev, nxt in zip(chunks, chunks[1:]):
        assert 0 < nxt.char_start <= prev.char_end
    # Full coverage: no text lost between chunk spans
    assert chunks[0].char_start == 0
    assert chunks[-1].char_end >= len(text) - 5


def test_chunk_source_short_text_single_chunk():
    chunks = curate.chunk_source("sid", "short text")
    assert len(chunks) == 1
    assert chunks[0].text == "short text"
    assert chunks[0].ordinal == 0


def test_chunk_source_empty_text():
    assert curate.chunk_source("sid", "   ") == []
