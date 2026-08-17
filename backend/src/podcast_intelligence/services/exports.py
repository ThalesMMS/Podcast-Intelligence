from __future__ import annotations

import json
from collections.abc import Sequence

from podcast_intelligence.models import Summary, TranscriptSegment


def _srt_time(milliseconds: int) -> str:
    hours, remainder = divmod(max(0, milliseconds), 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _vtt_time(milliseconds: int) -> str:
    return _srt_time(milliseconds).replace(",", ".")


def transcript_srt(segments: Sequence[TranscriptSegment]) -> str:
    blocks = []
    for index, segment in enumerate(segments, start=1):
        speaker = None
        if segment.speaker:
            speaker = segment.speaker.display_name or segment.speaker.label
        text = f"{speaker}: {segment.text}" if speaker else segment.text
        blocks.append(
            f"{index}\n{_srt_time(segment.start_ms)} --> {_srt_time(segment.end_ms)}\n{text}"
        )
    return "\n\n".join(blocks) + "\n"


def transcript_vtt(segments: Sequence[TranscriptSegment]) -> str:
    body = []
    for segment in segments:
        speaker = None
        if segment.speaker:
            speaker = segment.speaker.display_name or segment.speaker.label
        text = f"<v {speaker}>{segment.text}" if speaker else segment.text
        body.append(f"{_vtt_time(segment.start_ms)} --> {_vtt_time(segment.end_ms)}\n{text}")
    return "WEBVTT\n\n" + "\n\n".join(body) + "\n"


def summary_markdown(title: str, summary: Summary) -> str:
    content = summary.content_json
    lines = [f"# {title}", "", str(content.get("executive_summary") or ""), ""]
    detailed = content.get("detailed_summary")
    if detailed:
        lines.extend(["## Detailed summary", "", str(detailed), ""])
    chapters = content.get("chapters") or []
    if chapters:
        lines.extend(["## Chapters", ""])
        for chapter in chapters:
            start_ms = int(chapter.get("start_ms") or 0)
            timestamp = _vtt_time(start_ms).split(".", 1)[0]
            lines.extend(
                [
                    f"### {timestamp} — {chapter.get('title', 'Chapter')}",
                    "",
                    str(chapter.get("summary") or ""),
                    "",
                ]
            )
    takeaways = content.get("key_takeaways") or []
    if takeaways:
        lines.extend(["## Key takeaways", ""])
        lines.extend(f"- {item.get('text', '')}" for item in takeaways)
        lines.append("")
    return "\n".join(lines)


def export_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
