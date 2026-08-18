from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest

from podcast_intelligence.adapters.object_store.local import LocalObjectStore
from podcast_intelligence.config import Settings
from podcast_intelligence.domain.errors import MediaValidationError, NotFoundError


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        desktop_mode=True,
        app_secret_key="test-secret-with-enough-entropy",
        desktop_api_base_url="http://127.0.0.1:41821",
        desktop_data_dir=tmp_path,
        local_storage_dir=tmp_path / "objects",
        processing_temp_dir=tmp_path / "tmp",
    )


def test_signed_upload_and_playback_round_trip(tmp_path: Path) -> None:
    store = LocalObjectStore(_settings(tmp_path))
    source = tmp_path / "source.mp3"
    source.write_bytes(b"podcast-bytes")
    key = "workspace/uploads/example/audio.mp3"

    post = store.presign_post(key, "audio/mpeg", source.stat().st_size)
    token = post["url"].rsplit("/", 1)[-1]
    claims = store.verify_token(token, "put")
    store.write_uploaded_file(
        object_key=str(claims["key"]),
        source=source,
        content_type=str(claims["content_type"]),
        expected_size_bytes=int(claims["size"]),
    )

    playback_token = store.presign_get(key).rsplit("/", 1)[-1]
    path, metadata = store.local_path_for_token(playback_token)
    assert path.read_bytes() == b"podcast-bytes"
    assert metadata["content_type"] == "audio/mpeg"
    assert store.head(key) == {
        "content_length": len(b"podcast-bytes"),
        "content_type": "audio/mpeg",
        "etag": hashlib.sha256(b"podcast-bytes").hexdigest(),
        "metadata": {"expected-size": str(len(b"podcast-bytes"))},
    }


def test_tokens_are_operation_scoped_and_tamper_evident(tmp_path: Path) -> None:
    store = LocalObjectStore(_settings(tmp_path))
    post_token = store.presign_post("safe/audio.wav", "audio/wav", 10)["url"].rsplit("/", 1)[-1]

    with pytest.raises(MediaValidationError):
        store.verify_token(post_token, "get")
    with pytest.raises(MediaValidationError):
        store.verify_token(post_token[:-1] + ("a" if post_token[-1] != "a" else "b"), "put")


def test_expired_and_traversal_tokens_are_rejected(tmp_path: Path) -> None:
    store = LocalObjectStore(_settings(tmp_path))
    expired = store._sign(  # noqa: SLF001 - focused security test
        {"op": "get", "key": "safe/audio.wav", "exp": int(time.time()) - 1}
    )
    with pytest.raises(MediaValidationError):
        store.verify_token(expired, "get")
    with pytest.raises(MediaValidationError):
        store.presign_get("../outside.wav")


def test_missing_object_raises_not_found(tmp_path: Path) -> None:
    store = LocalObjectStore(_settings(tmp_path))
    with pytest.raises(NotFoundError):
        store.head("safe/missing.wav")
