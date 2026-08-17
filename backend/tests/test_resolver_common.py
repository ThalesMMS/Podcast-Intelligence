from __future__ import annotations

from podcast_intelligence.adapters.resolvers.common import (
    clean_html,
    parse_duration_ms,
    title_similarity,
)


def test_duration_parsing() -> None:
    assert parse_duration_ms("01:02:03") == 3_723_000
    assert parse_duration_ms("12:34") == 754_000
    assert parse_duration_ms(10.5) == 10_500
    assert parse_duration_ms("invalid") is None


def test_title_similarity_normalizes_accents_and_punctuation() -> None:
    assert title_similarity("Über Audio — Episode 4", "Uber Audio: Episode 4") > 0.95


def test_clean_html_compacts_text() -> None:
    assert clean_html("<p>Some  clean</p>\n<p>text</p>") == "Some clean text"
