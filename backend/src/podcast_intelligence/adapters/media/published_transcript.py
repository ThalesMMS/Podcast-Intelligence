from __future__ import annotations

import html
import json
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import httpx

from podcast_intelligence.adapters.media.safe_http import SafeHTTPClient
from podcast_intelligence.domain.errors import SourceResolutionError
from podcast_intelligence.domain.types import (
    TranscriptionResult,
    TranscriptReference,
    TranscriptSegmentData,
)

_CUE_TIME_RE = re.compile(
    r"(?:(?P<hours>\d{1,3}):)?(?P<minutes>\d{1,2}):(?P<seconds>\d{2})"
    r"[,.](?P<millis>\d{3})"
)
_VOICE_RE = re.compile(r"^\s*<v(?:\.[^ >]+)*\s+([^>]+)>(.*)$", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_SPEAKER_PREFIX_RE = re.compile(r"^\s*([^:\n]{1,80}):\s+(.+)$", re.DOTALL)


def _milliseconds(value: str) -> int:
    match = _CUE_TIME_RE.search(value.strip())
    if not match:
        raise ValueError(f"Invalid transcript timestamp: {value}")
    return (
        int(match.group("hours") or 0) * 3600
        + int(match.group("minutes")) * 60
        + int(match.group("seconds"))
    ) * 1000 + int(match.group("millis"))


def _clean_cue_text(value: str) -> tuple[str, str | None]:
    value = html.unescape(value).strip()
    speaker: str | None = None
    voice = _VOICE_RE.match(value)
    if voice:
        speaker = voice.group(1).strip()
        value = voice.group(2)
    value = _TAG_RE.sub("", value)
    value = " ".join(value.split())
    if speaker is None:
        prefix = _SPEAKER_PREFIX_RE.match(value)
        if prefix:
            candidate = prefix.group(1).strip()
            if 1 <= len(candidate.split()) <= 8:
                speaker = candidate
                value = prefix.group(2).strip()
    return value, speaker


def parse_timed_text(text: str, *, language: str | None = None) -> list[TranscriptSegmentData]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    blocks = re.split(r"\n\s*\n", normalized)
    segments: list[TranscriptSegmentData] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or lines[0].upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        timestamp_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if timestamp_index is None:
            continue
        left, right = lines[timestamp_index].split("-->", 1)
        right_timestamp = right.strip().split()[0]
        try:
            start_ms = _milliseconds(left)
            end_ms = _milliseconds(right_timestamp)
        except ValueError:
            continue
        cue_text, speaker = _clean_cue_text("\n".join(lines[timestamp_index + 1 :]))
        if not cue_text:
            continue
        label = (speaker or "SPEAKER_UNKNOWN")[:100]
        segments.append(
            TranscriptSegmentData(
                ordinal=len(segments),
                start_ms=start_ms,
                end_ms=max(start_ms, end_ms),
                text=cue_text,
                speaker_label=label,
                confidence=1.0,
                language=language,
                metadata={"speaker_name": speaker} if speaker else {},
            )
        )
    return segments


def _number(value: object) -> float | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_json_transcript(
    text: str, *, language: str | None = None, duration_ms: int | None = None
) -> list[TranscriptSegmentData]:
    payload = json.loads(text)
    if isinstance(payload, dict):
        raw_segments = payload.get("segments") or payload.get("items") or payload.get("transcript")
    else:
        raw_segments = payload
    if not isinstance(raw_segments, list):
        raise ValueError("JSON transcript does not contain a segment list")

    segments: list[TranscriptSegmentData] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        body = item.get("body") or item.get("text") or item.get("content")
        if not body:
            continue
        start = _number(item.get("startTime") or item.get("start_time") or item.get("start"))
        end = _number(item.get("endTime") or item.get("end_time") or item.get("end"))
        start_ms = max(0, round((start or 0) * 1000))
        end_ms = max(start_ms, round(end * 1000)) if end is not None else start_ms
        speaker_value = item.get("speaker") or item.get("speakerName") or item.get("speaker_name")
        if isinstance(speaker_value, dict):
            speaker_value = speaker_value.get("name") or speaker_value.get("id")
        speaker = str(speaker_value).strip() if speaker_value else None
        segments.append(
            TranscriptSegmentData(
                ordinal=len(segments),
                start_ms=start_ms,
                end_ms=end_ms,
                text=" ".join(str(body).split()),
                speaker_label=(speaker or "SPEAKER_UNKNOWN")[:100],
                confidence=1.0,
                language=str(item.get("language") or language)
                if (item.get("language") or language)
                else None,
                metadata={"speaker_name": speaker} if speaker else {},
            )
        )

    for index, segment in enumerate(segments):
        if segment.end_ms > segment.start_ms:
            continue
        if index + 1 < len(segments):
            segment.end_ms = max(segment.start_ms, segments[index + 1].start_ms)
        elif duration_ms is not None:
            segment.end_ms = max(segment.start_ms, duration_ms)
    return segments


class PublishedTranscriptLoader:
    """Load Podcast Namespace transcript references before invoking paid speech-to-text."""

    def __init__(self, http: SafeHTTPClient) -> None:
        self.http = http

    @staticmethod
    def _format(reference: TranscriptReference) -> str | None:
        mime = (reference.mime_type or "").lower().split(";", 1)[0].strip()
        suffix = PurePosixPath(urlsplit(reference.url).path).suffix.lower()
        if mime in {"text/vtt", "application/vtt"} or suffix == ".vtt":
            return "vtt"
        if mime in {"application/x-subrip", "application/srt", "text/srt"} or suffix == ".srt":
            return "srt"
        if mime in {"application/json", "application/ld+json"} or suffix == ".json":
            return "json"
        return None

    def load_first(
        self,
        references: list[TranscriptReference],
        *,
        language: str | None,
        duration_ms: int | None,
    ) -> TranscriptionResult | None:
        ranked = sorted(
            ((self._format(reference), reference) for reference in references),
            key=lambda item: {"vtt": 0, "srt": 1, "json": 2}.get(item[0] or "", 99),
        )
        errors: list[str] = []
        for transcript_format, reference in ranked:
            if transcript_format is None:
                continue
            try:
                text = self.http.fetch_text(reference.url, max_bytes=50 * 1024 * 1024)
                if transcript_format in {"vtt", "srt"}:
                    segments = parse_timed_text(text, language=reference.language or language)
                else:
                    segments = parse_json_transcript(
                        text,
                        language=reference.language or language,
                        duration_ms=duration_ms,
                    )
                if not segments:
                    raise ValueError("published transcript did not contain timed segments")
                return TranscriptionResult(
                    text=" ".join(segment.text for segment in segments),
                    segments=segments,
                    language=reference.language or language,
                    provider="published_transcript",
                    model=transcript_format,
                    metadata={
                        "published": True,
                        "format": transcript_format,
                        "source_url": reference.url,
                    },
                )
            except (SourceResolutionError, ValueError, httpx.HTTPError) as exc:
                errors.append(f"{transcript_format}: {exc}")
        if errors:
            raise SourceResolutionError("; ".join(errors))
        return None
