from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from podcast_intelligence.adapters.media.ffmpeg import FFmpegProcessor
from podcast_intelligence.domain.errors import MediaValidationError


def _processor(
    *,
    format_duration: object = "12.5",
    stream_duration: object = "20",
    max_duration_seconds: int = 10_000,
) -> FFmpegProcessor:
    settings = Mock()
    settings.ffprobe_binary = "ffprobe"
    settings.max_audio_duration_seconds = max_duration_seconds
    processor = FFmpegProcessor(settings)
    payload = {
        "format": {"duration": format_duration},
        "streams": [
            {
                "codec_type": "audio",
                "duration": stream_duration,
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
            }
        ],
    }
    processor._run = Mock(
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )
    )
    return processor


@pytest.mark.parametrize(
    "invalid_format_duration",
    ["N/A", "0", "0.0", "NaN", "Infinity", "-1", None],
)
def test_probe_falls_back_to_valid_audio_stream_duration(
    invalid_format_duration: object,
) -> None:
    metadata = _processor(
        format_duration=invalid_format_duration,
        stream_duration="12.5",
    ).probe(Path("valid-audio.m4a"))

    assert metadata.duration_ms == 12_500
    assert metadata.codec_name == "aac"
    assert metadata.sample_rate == 48_000
    assert metadata.channels == 2


def test_probe_prefers_valid_format_duration() -> None:
    metadata = _processor(
        format_duration="8.25",
        stream_duration="12.5",
    ).probe(Path("valid-audio.m4a"))

    assert metadata.duration_ms == 8_250


def test_probe_rejects_media_without_any_valid_duration() -> None:
    with pytest.raises(MediaValidationError, match="could not be determined"):
        _processor(
            format_duration="N/A",
            stream_duration="NaN",
        ).probe(Path("invalid-audio.m4a"))


def test_probe_enforces_duration_limit_after_stream_fallback() -> None:
    with pytest.raises(MediaValidationError, match="exceeds MAX_AUDIO_DURATION_SECONDS"):
        _processor(
            format_duration="N/A",
            stream_duration="101",
            max_duration_seconds=100,
        ).probe(Path("too-long.m4a"))
