from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Any

import podcast_intelligence.adapters.ai.streaming_stt as streaming_stt
from podcast_intelligence.adapters.ai.streaming_stt import StreamingWebSocketTranscriber
from podcast_intelligence.config import Settings


class _Socket:
    def __init__(self) -> None:
        self.sent: list[str | bytes] = []
        self.incoming = iter(
            [
                json.dumps(
                    {
                        "type": "transcript",
                        "committed": "real transcript",
                        "partial": "",
                        "done": True,
                    }
                )
            ]
        )

    async def __aenter__(self) -> _Socket:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        return json.dumps({"type": "ready", "message": "ok"})

    def __aiter__(self) -> _Socket:
        return self

    async def __anext__(self) -> str:
        try:
            return next(self.incoming)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _write_pcm16_wav(path: Path, *, duration_seconds: int = 2) -> None:
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(16_000)
        destination.writeframes(b"\x00\x00" * 16_000 * duration_seconds)


def test_streaming_stt_sends_pcm_and_returns_grounded_episode_segment(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    socket = _Socket()
    connect_kwargs: dict[str, Any] = {}

    def fake_connect(*_args: object, **kwargs: Any) -> _Socket:
        connect_kwargs.update(kwargs)
        return socket

    monkeypatch.setattr(streaming_stt, "connect", fake_connect)
    audio_path = tmp_path / "audio.wav"
    _write_pcm16_wav(audio_path)
    settings = Settings(
        _env_file=None,
        transcription_provider="streaming_ws",
        streaming_stt_url="ws://gateway.test/v1/audio/transcriptions/stream",
        streaming_stt_api_key="stt-key",
        streaming_stt_model="whisper-large-v3-turbo",
    )

    result = StreamingWebSocketTranscriber(settings).transcribe(
        audio_path,
        language="pt-BR",
    )

    start = json.loads(str(socket.sent[0]))
    assert start == {
        "type": "start",
        "apiKey": "stt-key",
        "model": "whisper-large-v3-turbo",
        "language": "pt",
        "format": "pcm_s16le",
        "sampleRate": 16_000,
    }
    assert any(isinstance(message, bytes) for message in socket.sent)
    assert json.loads(str(socket.sent[-1])) == {"type": "stop"}
    assert connect_kwargs["ping_interval"] is None
    assert result.text == "real transcript"
    assert result.provider == "streaming_ws"
    assert result.segments[0].start_ms == 0
    assert result.segments[0].end_ms == 2_000
    assert result.segments[0].speaker_label == "SPEAKER_UNKNOWN"


def test_streaming_stt_batches_long_audio_into_separate_sessions(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    sockets: list[_Socket] = []

    def fake_connect(*_args: object, **_kwargs: Any) -> _Socket:
        socket = _Socket()
        sockets.append(socket)
        return socket

    monkeypatch.setattr(streaming_stt, "connect", fake_connect)
    audio_path = tmp_path / "audio.wav"
    _write_pcm16_wav(audio_path, duration_seconds=5)
    settings = Settings(
        _env_file=None,
        transcription_provider="streaming_ws",
        streaming_stt_url="ws://gateway.test/v1/audio/transcriptions/stream",
        streaming_stt_api_key="stt-key",
        streaming_stt_model="whisper-large-v3-turbo",
        streaming_stt_frame_seconds=1,
        streaming_stt_batch_seconds=2,
    )

    result = StreamingWebSocketTranscriber(settings).transcribe(
        audio_path,
        language="pt",
    )

    assert len(sockets) == 3
    assert [(segment.start_ms, segment.end_ms) for segment in result.segments] == [
        (0, 2_000),
        (2_000, 4_000),
        (4_000, 5_000),
    ]
    assert result.metadata["batch_count"] == 3
