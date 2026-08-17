from __future__ import annotations

import math
from pathlib import Path

from podcast_intelligence.adapters.ai.demo import (
    DemoLanguageModel,
    DemoTranscriber,
    DeterministicEmbeddingProvider,
)
from podcast_intelligence.domain.types import RetrievedChunk


def test_deterministic_embeddings_are_normalized_and_repeatable() -> None:
    provider = DeterministicEmbeddingProvider(dimension=128)
    first, second, different = provider.embed(
        [
            "radiology and artificial intelligence",
            "radiology and artificial intelligence",
            "cooking",
        ]
    )
    assert first == second
    assert first != different
    assert math.isclose(sum(value * value for value in first), 1.0, rel_tol=1e-6)


def test_demo_answer_uses_only_context_segment_ids() -> None:
    model = DemoLanguageModel()
    context = RetrievedChunk(
        chunk_id="chunk-1",
        episode_id="episode-1",
        episode_title="Test",
        text="Hybrid retrieval combines lexical and vector search.",
        start_ms=0,
        end_ms=5000,
        segment_ids=["segment-1"],
        speaker_labels=["Person"],
        combined_score=0.9,
    )
    answer = model.answer("How does retrieval work?", [context], [])
    assert answer.insufficient_evidence is False
    assert answer.cited_segment_ids == ["segment-1"]
    assert "retrieval" in answer.answer.lower()


def test_demo_answer_abstains_without_context() -> None:
    answer = DemoLanguageModel().answer("Question", [], [])
    assert answer.insufficient_evidence is True
    assert answer.cited_segment_ids == []
    assert answer.answer == "There is not enough evidence in the indexed transcript to answer."


def test_demo_transcriber_labels_its_fixed_synthetic_content_as_english(tmp_path: Path) -> None:
    media = tmp_path / "episode.wav"
    media.write_bytes(b"demo")

    result = DemoTranscriber().transcribe(media, language="pt-BR")

    assert result.language == "en"
    assert all(segment.language == "en" for segment in result.segments)
    assert result.text.startswith("This is a synthetic transcript")
