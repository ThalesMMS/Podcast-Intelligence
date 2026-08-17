from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from podcast_intelligence.adapters.ai.codex_cli import CodexCLILanguageModel
from podcast_intelligence.adapters.ai.openai import OpenAILanguageModel
from podcast_intelligence.domain.types import RetrievedChunk, SectionDigest


def _context() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="chunk-1",
        episode_id="episode-1",
        episode_title="Episode",
        text="Grounded evidence.",
        start_ms=0,
        end_ms=1_000,
        segment_ids=["segment-1"],
        speaker_labels=["Host"],
    )


def test_openai_prompts_define_language_and_use_english_labels(monkeypatch: Any) -> None:
    calls: list[tuple[str, str]] = []

    def capture(
        _self: OpenAILanguageModel,
        instructions: str,
        payload: str,
        output_type: type[BaseModel],
    ) -> BaseModel:
        calls.append((instructions, payload))
        return output_type.model_construct()

    monkeypatch.setattr(OpenAILanguageModel, "_parse", capture)
    model = OpenAILanguageModel.__new__(OpenAILanguageModel)

    model.summarize_section("Episode", "Opening", "Transcript text", ["segment-1"])
    model.synthesize_summary(
        "Episode",
        [
            SectionDigest(
                title="Opening",
                summary="Summary",
                start_ms=0,
                end_ms=1_000,
                supporting_segment_ids=["segment-1"],
            )
        ],
    )
    model.answer("What happened?", [_context()], [])

    assert "same language as the transcript" in calls[0][0]
    assert "EPISODE:" in calls[0][1]
    assert "SECTION:" in calls[0][1]
    assert "TRANSCRIPT:" in calls[0][1]
    assert "segment-1" in calls[0][1]
    assert "same language as the partial summaries" in calls[1][0]
    assert "PARTIAL_SUMMARIES:" in calls[1][1]
    assert "same language as the user's question" in calls[2][0]
    assert "QUESTION:" in calls[2][1]
    assert "AUXILIARY_HISTORY:" in calls[2][1]
    assert "EVIDENCE:" in calls[2][1]
    assert "segment-1" in calls[2][1]


def test_codex_prompts_define_language_and_use_english_labels(monkeypatch: Any) -> None:
    prompts: list[str] = []

    def capture(
        _self: CodexCLILanguageModel, prompt: str, output_type: type[BaseModel]
    ) -> BaseModel:
        prompts.append(prompt)
        return output_type.model_construct()

    monkeypatch.setattr(CodexCLILanguageModel, "_run", capture)
    model = CodexCLILanguageModel.__new__(CodexCLILanguageModel)

    model.summarize_section("Episode", "Opening", "Transcript text", ["segment-1"])
    model.synthesize_summary(
        "Episode",
        [
            SectionDigest(
                title="Opening",
                summary="Summary",
                start_ms=0,
                end_ms=1_000,
                supporting_segment_ids=["segment-1"],
            )
        ],
    )
    model.answer("What happened?", [_context()], [])

    assert "same language as the transcript" in prompts[0]
    assert "EPISODE:" in prompts[0]
    assert "SECTION:" in prompts[0]
    assert "TRANSCRIPT:" in prompts[0]
    assert "segment-1" in prompts[0]
    assert "same language as the partial summaries" in prompts[1]
    assert "PARTIAL_SUMMARIES:" in prompts[1]
    assert "same language as the user's question" in prompts[2]
    assert "QUESTION:" in prompts[2]
    assert "AUXILIARY_HISTORY:" in prompts[2]
    assert "CONTEXTS:" in prompts[2]
    assert "segment-1" in prompts[2]
