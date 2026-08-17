from __future__ import annotations

import json

from podcast_intelligence.adapters.media.published_transcript import (
    parse_json_transcript,
    parse_timed_text,
)


def test_parse_vtt_preserves_speaker_and_timestamps() -> None:
    segments = parse_timed_text(
        """WEBVTT

00:00:01.000 --> 00:00:04.500
<v Alice>First statement.

2
00:04.500 --> 00:08.000
Bob: Second statement.
""",
        language="en",
    )
    assert [segment.speaker_label for segment in segments] == ["Alice", "Bob"]
    assert segments[0].start_ms == 1000
    assert segments[1].end_ms == 8000
    assert segments[0].metadata["speaker_name"] == "Alice"


def test_parse_podcast_json_fills_missing_end_time() -> None:
    payload = {
        "segments": [
            {"startTime": 0, "body": "Introduction", "speaker": "Host"},
            {"startTime": 3.5, "endTime": 7, "body": "Answer", "speaker": "Guest"},
        ]
    }
    segments = parse_json_transcript(json.dumps(payload), duration_ms=10_000)
    assert segments[0].end_ms == 3500
    assert segments[1].start_ms == 3500
    assert segments[1].end_ms == 7000


def test_parse_podcast_json_clamps_negative_last_segment_timestamps() -> None:
    payload = {
        "segments": [
            {"startTime": -2, "endTime": -1, "body": "Introduction"},
        ]
    }

    [segment] = parse_json_transcript(json.dumps(payload))

    assert segment.start_ms == 0
    assert segment.end_ms == 0


def test_parse_podcast_json_fills_clamped_segment_from_next_start() -> None:
    payload = {
        "segments": [
            {"startTime": -2, "body": "Introduction"},
            {"startTime": 3.5, "endTime": 7, "body": "Answer"},
        ]
    }

    segments = parse_json_transcript(json.dumps(payload))

    assert segments[0].start_ms == 0
    assert segments[0].end_ms == 3500


def test_parse_podcast_json_fills_clamped_last_segment_from_duration() -> None:
    payload = {
        "segments": [
            {"startTime": -2, "body": "Introduction"},
        ]
    }

    [segment] = parse_json_transcript(json.dumps(payload), duration_ms=10_000)

    assert segment.start_ms == 0
    assert segment.end_ms == 10_000
