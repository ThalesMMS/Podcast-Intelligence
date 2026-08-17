from __future__ import annotations

import uuid
from types import SimpleNamespace

from podcast_intelligence.services.chunking import build_chunks, estimate_tokens


def segment(ordinal: int, text: str, speaker: str):
    return SimpleNamespace(
        id=uuid.uuid4(),
        ordinal=ordinal,
        start_ms=ordinal * 1000,
        end_ms=(ordinal + 1) * 1000,
        text=text,
        speaker=SimpleNamespace(display_name=speaker, label=speaker),
    )


def test_chunking_preserves_time_speakers_and_segment_ids() -> None:
    segments = [
        segment(0, "first statement with a few terms", "Alice"),
        segment(1, "second statement with other terms", "Bob"),
        segment(2, "third statement that forces a new block", "Alice"),
    ]
    chunks = build_chunks(segments, target_tokens=50, overlap_tokens=10)
    assert chunks
    assert chunks[0].start_ms == 0
    assert chunks[-1].end_ms == 3000
    assert "Alice" in {name for chunk in chunks for name in chunk.speaker_labels}
    assert all(chunk.segment_ids for chunk in chunks)


def test_token_estimate_never_returns_zero() -> None:
    assert estimate_tokens("") == 1
