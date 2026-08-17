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
        if not settings.streaming_stt_api_key:
            raise ValueError("STREAMING_STT_API_KEY is required")
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
    ) -> str:
        frames_per_message = round(16_000 * self.settings.streaming_stt_frame_seconds)
        async with connect(
            self.url,
            open_timeout=self.settings.streaming_stt_open_timeout_seconds,
            close_timeout=self.settings.streaming_stt_close_timeout_seconds,
            ping_interval=None,
            max_size=None,
        ) as socket:
            await socket.send(
                json.dumps(
                    {
                        "type": "start",
                        "apiKey": self.settings.streaming_stt_api_key,
                        "model": self.model_name,
                        "language": language,
                        "format": "pcm_s16le",
                        "sampleRate": 16_000,
                    }
                )
            )
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
            try:
                async for raw_message in socket:
                    event = self._event(raw_message)
                    if event.get("type") != "transcript":
                        continue
                    committed = str(event.get("committed") or "")
                    partial = str(event.get("partial") or "")
                    if event.get("done"):
                        final_text = f"{committed}{partial}".strip()
                        break
                await sender
            finally:
                if not sender.done():
                    sender.cancel()
                    with suppress(asyncio.CancelledError):
                        await sender

            if final_text is None:
                raise RuntimeError("Streaming STT closed without a final transcript")
            return final_text

    async def _stream_batches(
        self,
        audio_path: Path,
        language: str,
        *,
        total_frames: int,
        sample_rate: int,
    ) -> list[tuple[int, int, str]]:
        batch_frames = round(sample_rate * self.settings.streaming_stt_batch_seconds)
        batches: list[tuple[int, int, str]] = []
        for start_frame in range(0, total_frames, batch_frames):
            frame_count = min(batch_frames, total_frames - start_frame)
            text = await self._stream(
                audio_path,
                language,
                start_frame=start_frame,
                frame_count=frame_count,
            )
            batches.append((start_frame, frame_count, text))
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
            (start_frame, batch_frame_count, batch_text.strip())
            for start_frame, batch_frame_count, batch_text in batches
            if batch_text.strip()
        ]
        if not nonempty_batches:
            raise RuntimeError("Streaming STT returned an empty transcript")
        text = "\n\n".join(batch_text for _, _, batch_text in nonempty_batches)
        return TranscriptionResult(
            text=text,
            segments=[
                TranscriptSegmentData(
                    ordinal=ordinal,
                    start_ms=round(start_frame / sample_rate * 1000),
                    end_ms=round((start_frame + batch_frame_count) / sample_rate * 1000),
                    text=batch_text,
                    speaker_label="SPEAKER_UNKNOWN",
                    language=resolved_language,
                    metadata={"streaming": True, "timestamps": "batch_bounds"},
                )
                for ordinal, (
                    start_frame,
                    batch_frame_count,
                    batch_text,
                ) in enumerate(nonempty_batches)
            ],
            language=resolved_language,
            provider=self.provider_name,
            model=self.model_name,
            duration_seconds=duration_seconds,
            metadata={
                "protocol": "pcm_s16le-websocket-v1",
                "diarization": False,
                "segment_timestamps": False,
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
                "segment_timestamps": False,
                "streaming": True,
                "sample_rate": 16_000,
            },
        )
