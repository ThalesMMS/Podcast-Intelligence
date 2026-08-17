from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pytest import MonkeyPatch

from podcast_intelligence.adapters.media.safe_http import SafeHTTPClient
from podcast_intelligence.config import Settings
from podcast_intelligence.domain.errors import MediaValidationError, SourceResolutionError
from podcast_intelligence.worker import tasks


class _SuccessfulPipeline:
    def __init__(self, _session: object, _registry: object) -> None:
        pass

    def run(self, _job_id: uuid.UUID) -> None:
        pass


def _mock_http(
    monkeypatch: MonkeyPatch,
    *,
    content: bytes,
    content_length: str | None,
    max_remote_file_bytes: int = 4,
) -> SafeHTTPClient:
    http = SafeHTTPClient(Settings(max_remote_file_bytes=max_remote_file_bytes))
    http.client.close()
    headers = {"Content-Type": "audio/mpeg"}
    if content_length is not None:
        headers["Content-Length"] = content_length
    http.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers=headers,
                stream=httpx.ByteStream(content),
            )
        )
    )
    monkeypatch.setattr(http, "validate_url", lambda url: url)
    return http


def test_safe_http_client_close_is_idempotent() -> None:
    http = SafeHTTPClient(Settings())

    http.close()
    http.close()

    assert http.client.is_closed


@pytest.mark.parametrize("content_length", ["N/A", "-1"])
@pytest.mark.parametrize("operation", ["fetch", "download"])
def test_remote_content_length_must_be_a_non_negative_decimal(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    content_length: str,
    operation: str,
) -> None:
    http = _mock_http(
        monkeypatch,
        content=b"ok",
        content_length=content_length,
    )
    try:
        if operation == "fetch":
            with pytest.raises(SourceResolutionError, match="invalid Content-Length"):
                http.fetch_bytes("https://media.example/metadata", max_bytes=4)
        else:
            with pytest.raises(MediaValidationError, match="invalid Content-Length"):
                http.download("https://media.example/audio", tmp_path)
    finally:
        http.close()


@pytest.mark.parametrize("operation", ["fetch", "download"])
def test_oversized_content_length_uses_size_limit_path_before_integer_conversion(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    operation: str,
) -> None:
    http = _mock_http(
        monkeypatch,
        content=b"ok",
        content_length="9" * 5_000,
    )
    try:
        if operation == "fetch":
            with pytest.raises(SourceResolutionError, match="larger than"):
                http.fetch_bytes("https://media.example/metadata", max_bytes=4)
        else:
            with pytest.raises(MediaValidationError, match="exceeds"):
                http.download("https://media.example/audio", tmp_path)
    finally:
        http.close()


def test_missing_content_length_keeps_streaming_size_limit(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    accepted = _mock_http(
        monkeypatch,
        content=b"four",
        content_length=None,
    )
    rejected = _mock_http(
        monkeypatch,
        content=b"five!",
        content_length=None,
    )
    try:
        assert accepted.fetch_bytes("https://media.example/metadata", max_bytes=4) == b"four"
        with pytest.raises(MediaValidationError, match="exceeded the size limit"):
            rejected.download("https://media.example/audio", tmp_path)
        assert not (tmp_path / "source-media").exists()
    finally:
        accepted.close()
        rejected.close()


@pytest.mark.parametrize("operation", ["fetch", "download"])
def test_declared_content_length_above_limit_is_rejected(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    operation: str,
) -> None:
    http = _mock_http(
        monkeypatch,
        content=b"x",
        content_length="5",
    )
    try:
        if operation == "fetch":
            with pytest.raises(SourceResolutionError, match="larger than"):
                http.fetch_bytes("https://media.example/metadata", max_bytes=4)
        else:
            with pytest.raises(MediaValidationError, match="exceeds"):
                http.download("https://media.example/audio", tmp_path)
    finally:
        http.close()


@pytest.mark.parametrize("operation", ["fetch", "download"])
def test_declared_content_length_equal_to_limit_is_accepted(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    operation: str,
) -> None:
    http = _mock_http(
        monkeypatch,
        content=b"four",
        content_length="4",
    )
    try:
        if operation == "fetch":
            assert http.fetch_bytes("https://media.example/metadata", max_bytes=4) == b"four"
        else:
            media = http.download("https://media.example/audio", tmp_path)
            assert media.size_bytes == 4
            assert media.path.read_bytes() == b"four"
    finally:
        http.close()


def test_successful_worker_task_does_not_fail_during_cleanup(monkeypatch: MonkeyPatch) -> None:
    http = SafeHTTPClient(Settings())
    registry = SimpleNamespace(http=http)
    monkeypatch.setattr(tasks, "build_registry", lambda _settings: registry)
    monkeypatch.setattr(tasks, "JobPipeline", _SuccessfulPipeline)

    job_id = uuid.uuid4()
    result = tasks.process_job.run(str(job_id))

    assert result == {"job_id": str(job_id), "status": "completed"}
    assert http.client.is_closed
