from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from podcast_intelligence.domain.types import ChunkInput


class SpeakerLike(Protocol):
    @property
    def label(self) -> str: ...

    @property
    def display_name(self) -> str | None: ...


class SegmentLike(Protocol):
    @property
    def id(self) -> object: ...

    @property
    def ordinal(self) -> int: ...

    @property
    def start_ms(self) -> int: ...

    @property
    def end_ms(self) -> int: ...

    @property
    def text(self) -> str: ...

    @property
    def speaker(self) -> SpeakerLike | None: ...


def estimate_tokens(text: str) -> int:
    # A conservative language-agnostic approximation that avoids tokenizer coupling.
    return max(1, round(len(text.split()) * 1.35))


def build_chunks(
    segments: Sequence[SegmentLike],
    *,
    target_tokens: int = 600,
    overlap_tokens: int = 80,
) -> list[ChunkInput]:
    if target_tokens < 50:
        raise ValueError("target_tokens must be at least 50")
    if overlap_tokens < 0 or overlap_tokens >= target_tokens:
        raise ValueError("overlap_tokens must be non-negative and smaller than target_tokens")

    ordered = sorted(segments, key=lambda segment: segment.ordinal)
    chunks: list[ChunkInput] = []
    window: list[SegmentLike] = []
    window_tokens = 0

    def render(current: Sequence[SegmentLike], ordinal: int) -> ChunkInput:
        lines: list[str] = []
        speaker_labels: list[str] = []
        for segment in current:
            label = (
                segment.speaker.display_name
                if segment.speaker and segment.speaker.display_name
                else (segment.speaker.label if segment.speaker else "SPEAKER_UNKNOWN")
            )
            speaker_labels.append(label)
            lines.append(f"[{label}] {segment.text.strip()}")
        return ChunkInput(
            ordinal=ordinal,
            text="\n".join(lines),
            start_ms=current[0].start_ms,
            end_ms=current[-1].end_ms,
            segment_ids=[str(segment.id) for segment in current],
            speaker_labels=list(dict.fromkeys(speaker_labels)),
            token_count=sum(estimate_tokens(segment.text) for segment in current),
        )

    def overlap_tail(current: Sequence[SegmentLike]) -> list[SegmentLike]:
        if not current or overlap_tokens == 0:
            return []
        selected: list[SegmentLike] = []
        count = 0
        for segment in reversed(current):
            selected.append(segment)
            count += estimate_tokens(segment.text)
            if count >= overlap_tokens:
                break
        return list(reversed(selected))

    for segment in ordered:
        segment_tokens = estimate_tokens(segment.text)
        if window and window_tokens + segment_tokens > target_tokens:
            chunks.append(render(window, len(chunks)))
            window = overlap_tail(window)
            window_tokens = sum(estimate_tokens(item.text) for item in window)
        window.append(segment)
        window_tokens += segment_tokens

    if window:
        rendered = render(window, len(chunks))
        if not chunks or rendered.segment_ids != chunks[-1].segment_ids:
            chunks.append(rendered)
    return chunks
