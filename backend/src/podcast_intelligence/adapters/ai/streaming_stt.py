from __future__ import annotations

import asyncio
import json
import wave
from contextlib import suppress
from pathlib import Path
from typing import Any

from websockets.asyncio.client import connect

from podcast_intelligence.config import Settings
from podcast_intelligence.domain.types import (
    ProviderCapabilities,
    TranscriptionResult,
    TranscriptSegmentData,
)


class StreamingWebSocketTranscriber:
    provider_name = "streaming_ws"

    def __init__(self, settings: Settings) -> None:
        url = settings.streaming_stt_url
        if not url:
            raise ValueError("STREAMING_STT_URL is required")
        self.settings = settings
        self.url = url
        self.model_name = settings.streaming_stt_model

    @staticmethod
    def _wave_details(audio_path: Path) -> tuple[int, int]:
        with wave.open(str(audio_path), "rb") as source:
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            sample_rate = source.getframerate()
            frame_count = source.getnframes()
        if channels != 1 or sample_width != 2 or sample_rate != 16_000:
            raise RuntimeError(
                "Streaming STT requires mono 16-bit PCM WAV audio sampled at 16000 Hz"
            )
        return frame_count, sample_rate

    @staticmethod
    def _event(raw_message: str | bytes) -> dict[str, Any]:
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")
        try:
            payload = json.loads(raw_message)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Streaming STT returned an invalid JSON message") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Streaming STT returned a non-object JSON message")
        if payload.get("type") == "error":
            raise RuntimeError(str(payload.get("message") or "Streaming STT request failed"))
        return payload

    async def _stream(
        self,
        audio_path: Path,
        language: str,
        *,
        start_frame: int,
        frame_count: int,
    ) -> tuple[str, list[dict[str, Any]]]:
        frames_per_message = round(16_000 * self.settings.streaming_stt_frame_seconds)
        async with connect(
            self.url,
            open_timeout=self.settings.streaming_stt_open_timeout_seconds,
            close_timeout=self.settings.streaming_stt_close_timeout_seconds,
            ping_interval=None,
            max_size=None,
        ) as socket:
            start_message: dict[str, Any] = {
                "type": "start",
                "model": self.model_name,
                "language": language,
                "format": "pcm_s16le",
                "sampleRate": 16_000,
            }
            if self.settings.streaming_stt_api_key:
                start_message["apiKey"] = self.settings.streaming_stt_api_key
            await socket.send(json.dumps(start_message))
            ready = self._event(await socket.recv())
            if ready.get("type") != "ready":
                raise RuntimeError("Streaming STT did not acknowledge the session")

            async def send_audio() -> None:
                with wave.open(str(audio_path), "rb") as source:
                    source.setpos(start_frame)
                    frames_remaining = frame_count
                    while frames_remaining > 0:
                        frames = source.readframes(min(frames_per_message, frames_remaining))
                        if not frames:
                            break
                        await socket.send(frames)
                        await asyncio.sleep(0)
                        frames_remaining -= len(frames) // source.getsampwidth()
                await socket.send(json.dumps({"type": "stop"}))

            sender = asyncio.create_task(send_audio())
            final_text: str | None = None
            final_segments: list[dict[str, Any]] = []
            try:
                async for raw_message in socket:
                    event = self._event(raw_message)
                    if event.get("type") != "transcript":
                        continue
                    committed = str(event.get("committed") or "")
                    partial = str(event.get("partial") or "")
                    if event.get("done"):
                        final_text = f"{committed}{partial}".strip()
                        segments = event.get("segments")
                        if isinstance(segments, list):
                            final_segments = [
                                segment for segment in segments if isinstance(segment, dict)
                            ]
                        break
                await sender
            finally:
                if not sender.done():
                    sender.cancel()
                    with suppress(asyncio.CancelledError):
                        await sender

            if final_text is None:
                raise RuntimeError("Streaming STT closed without a final transcript")
            return final_text, final_segments

    async def _stream_batches(
        self,
        audio_path: Path,
        language: str,
        *,
        total_frames: int,
        sample_rate: int,
    ) -> list[tuple[int, int, str, list[dict[str, Any]]]]:
        batch_frames = round(sample_rate * self.settings.streaming_stt_batch_seconds)
        batches: list[tuple[int, int, str, list[dict[str, Any]]]] = []
        for start_frame in range(0, total_frames, batch_frames):
            frame_count = min(batch_frames, total_frames - start_frame)
            text, segments = await self._stream(
                audio_path,
                language,
                start_frame=start_frame,
                frame_count=frame_count,
            )
            batches.append((start_frame, frame_count, text, segments))
        return batches

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        known_speakers: dict[str, Path] | None = None,
    ) -> TranscriptionResult:
        del known_speakers
        frame_count, sample_rate = self._wave_details(audio_path)
        duration_seconds = frame_count / sample_rate
        resolved_language = (language or self.settings.streaming_stt_language).split("-", 1)[0]
        resolved_language = resolved_language.lower()
        batches = asyncio.run(
            self._stream_batches(
                audio_path,
                resolved_language,
                total_frames=frame_count,
                sample_rate=sample_rate,
            )
        )
        nonempty_batches = [
            (start_frame, batch_frame_count, batch_text.strip(), segments)
            for start_frame, batch_frame_count, batch_text, segments in batches
            if batch_text.strip()
        ]
        if not nonempty_batches:
            raise RuntimeError("Streaming STT returned an empty transcript")
        text = "\n\n".join(batch_text for _, _, batch_text, _ in nonempty_batches)
        transcript_segments: list[TranscriptSegmentData] = []
        gateway_timestamps = False
        for start_frame, batch_frame_count, batch_text, gateway_segments in nonempty_batches:
            batch_offset_ms = round(start_frame / sample_rate * 1000)
            usable_segments = [
                segment
                for segment in gateway_segments
                if str(segment.get("text") or "").strip()
                and isinstance(segment.get("start"), (int, float))
                and isinstance(segment.get("end"), (int, float))
            ]
            if usable_segments:
                gateway_timestamps = True
                for segment in usable_segments:
                    channel = str(segment.get("channel") or "mixed")
                    transcript_segments.append(
                        TranscriptSegmentData(
                            ordinal=len(transcript_segments),
                            start_ms=batch_offset_ms + round(float(segment["start"]) * 1000),
                            end_ms=batch_offset_ms + round(float(segment["end"]) * 1000),
                            text=str(segment["text"]).strip(),
                            speaker_label=(
                                channel if channel not in {"mixed", "unknown"}
                                else "SPEAKER_UNKNOWN"
                            ),
                            language=resolved_language,
                            metadata={
                                "streaming": True,
                                "timestamps": "gateway",
                                "utterance_id": segment.get("utteranceId"),
                                "revision": segment.get("revision"),
                                "channel": channel,
                            },
                        )
                    )
                continue
            transcript_segments.append(
                TranscriptSegmentData(
                    ordinal=len(transcript_segments),
                    start_ms=batch_offset_ms,
                    end_ms=round((start_frame + batch_frame_count) / sample_rate * 1000),
                    text=batch_text,
                    speaker_label="SPEAKER_UNKNOWN",
                    language=resolved_language,
                    metadata={"streaming": True, "timestamps": "batch_bounds"},
                )
            )
        return TranscriptionResult(
            text=text,
            segments=transcript_segments,
            language=resolved_language,
            provider=self.provider_name,
            model=self.model_name,
            duration_seconds=duration_seconds,
            metadata={
                "protocol": "pcm_s16le-websocket-v1",
                "diarization": False,
                "segment_timestamps": gateway_timestamps,
                "batch_count": len(batches),
                "batch_seconds": self.settings.streaming_stt_batch_seconds,
            },
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.provider_name,
            kind="transcription",
            model=self.model_name,
            capabilities={
                "real_transcription": True,
                "diarization": False,
                "segment_timestamps": True,
                "streaming": True,
                "sample_rate": 16_000,
            },
        )
