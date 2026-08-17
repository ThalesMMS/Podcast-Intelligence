from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

from podcast_intelligence.config import Settings
from podcast_intelligence.domain.errors import MediaValidationError
from podcast_intelligence.domain.types import AudioMetadata


class FFmpegProcessor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _run(self, command: list[str], *, timeout: int = 7200) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise MediaValidationError(f"Required media binary not found: {command[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise MediaValidationError("FFmpeg operation timed out") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "FFmpeg failed")[-4000:]
            raise MediaValidationError(detail) from exc

    def probe(self, source: Path) -> AudioMetadata:
        result = self._run(
            [
                self.settings.ffprobe_binary,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(source),
            ],
            timeout=120,
        )
        try:
            payload: dict[str, Any] = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise MediaValidationError("ffprobe returned invalid JSON") from exc

        streams = payload.get("streams") or []
        audio_stream = next(
            (stream for stream in streams if stream.get("codec_type") == "audio"), None
        )
        if not audio_stream:
            raise MediaValidationError("No audio stream was found")

        format_info = payload.get("format") or {}
        duration_seconds = None
        for candidate in (format_info.get("duration"), audio_stream.get("duration")):
            try:
                parsed_duration = float(str(candidate))
            except (TypeError, ValueError):
                continue
            if math.isfinite(parsed_duration) and parsed_duration > 0:
                duration_seconds = parsed_duration
                break
        if duration_seconds is None:
            raise MediaValidationError("Audio duration could not be determined")
        if duration_seconds > self.settings.max_audio_duration_seconds:
            raise MediaValidationError("Audio exceeds MAX_AUDIO_DURATION_SECONDS")

        def to_int(value: object) -> int | None:
            try:
                return int(str(value))
            except (TypeError, ValueError):
                return None

        return AudioMetadata(
            duration_ms=int(duration_seconds * 1000),
            codec_name=audio_stream.get("codec_name"),
            format_name=format_info.get("format_name"),
            sample_rate=to_int(audio_stream.get("sample_rate")),
            channels=to_int(audio_stream.get("channels")),
            bit_rate=to_int(format_info.get("bit_rate") or audio_stream.get("bit_rate")),
        )

    def normalize(self, source: Path, destination: Path) -> AudioMetadata:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                self.settings.ffmpeg_binary,
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                str(self.settings.audio_channels),
                "-ar",
                str(self.settings.audio_sample_rate),
                "-c:a",
                "pcm_s16le",
                str(destination),
            ]
        )
        return self.probe(destination)

    def create_playback(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                self.settings.ffmpeg_binary,
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-movflags",
                "+faststart",
                str(destination),
            ]
        )
