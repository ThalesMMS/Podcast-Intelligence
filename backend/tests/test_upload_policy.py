from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from podcast_intelligence.adapters.object_store.s3 import S3ObjectStore
from podcast_intelligence.config import Settings
from podcast_intelligence.domain.errors import MediaValidationError
from podcast_intelligence.schemas import UploadInitiateRequest
from podcast_intelligence.services.imports import ImportService
from podcast_intelligence.services.pipeline import _validated_upload_head


class _RecordingStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, int]] = []

    def presign_post(
        self,
        object_key: str,
        content_type: str,
        expected_size_bytes: int,
        expires_seconds: int = 900,
    ) -> dict[str, object]:
        self.calls.append((object_key, content_type, expected_size_bytes, expires_seconds))
        return {
            "url": "https://storage.example/upload",
            "fields": {
                "key": object_key,
                "Content-Type": content_type,
                "x-amz-meta-expected-size": str(expected_size_bytes),
            },
        }


def test_upload_initiation_binds_declared_size_and_content_type() -> None:
    store = _RecordingStore()
    settings = Settings(max_remote_file_bytes=1_000)
    service = ImportService(SimpleNamespace(), store, settings)  # type: ignore[arg-type]

    response = service.initiate_upload(
        uuid.uuid4(),
        UploadInitiateRequest(
            filename="episode.mp3",
            content_type="audio/mpeg",
            size_bytes=321,
        ),
    )

    assert response.method == "POST"
    assert response.upload_url == "https://storage.example/upload"
    assert response.fields["Content-Type"] == "audio/mpeg"
    assert response.fields["x-amz-meta-expected-size"] == "321"
    assert store.calls[0][1:] == ("audio/mpeg", 321, 900)


def test_upload_initiation_respects_configured_remote_limit() -> None:
    service = ImportService(
        SimpleNamespace(),
        _RecordingStore(),
        Settings(max_remote_file_bytes=100),
    )  # type: ignore[arg-type]

    with pytest.raises(MediaValidationError, match="MAX_REMOTE_FILE_BYTES"):
        service.initiate_upload(
            uuid.uuid4(),
            UploadInitiateRequest(
                filename="episode.mp3",
                content_type="audio/mpeg",
                size_bytes=101,
            ),
        )


def test_upload_initiation_allows_configured_limit_above_one_gibibyte() -> None:
    declared_size = 1024 * 1024 * 1024 + 1
    store = _RecordingStore()
    service = ImportService(
        SimpleNamespace(),
        store,
        Settings(max_remote_file_bytes=declared_size),
    )  # type: ignore[arg-type]

    service.initiate_upload(
        uuid.uuid4(),
        UploadInitiateRequest(
            filename="long-episode.mp3",
            content_type="audio/mpeg",
            size_bytes=declared_size,
        ),
    )

    assert store.calls[0][2] == declared_size


@pytest.mark.parametrize(
    ("content_type", "normalized"),
    [
        ("audio/mpeg", "audio/mpeg"),
        (" Video/MP4 ", "video/mp4"),
        ("audio/vnd.wave", "audio/vnd.wave"),
    ],
)
def test_upload_request_accepts_only_concrete_media_mime_types(
    content_type: str,
    normalized: str,
) -> None:
    request = UploadInitiateRequest(
        filename="episode.bin",
        content_type=content_type,
        size_bytes=1,
    )

    assert request.content_type == normalized


@pytest.mark.parametrize(
    "content_type",
    [
        "application/octet-stream",
        "text/html",
        "audio/*",
        "audio/",
        "audio/mpeg; charset=utf-8",
    ],
)
def test_upload_request_rejects_unsupported_mime_types(content_type: str) -> None:
    with pytest.raises(ValidationError, match="concrete audio or video MIME type"):
        UploadInitiateRequest(
            filename="episode.bin",
            content_type=content_type,
            size_bytes=1,
        )


def test_s3_policy_contains_content_length_range_and_signed_metadata() -> None:
    calls: list[dict[str, object]] = []
    store = object.__new__(S3ObjectStore)
    store.bucket = "podcasts"
    store._public_client = SimpleNamespace(  # type: ignore[attr-defined]
        generate_presigned_post=lambda **kwargs: (
            calls.append(kwargs)
            or {
                "url": "https://storage.example/podcasts",
                "fields": {
                    "key": kwargs["Key"],
                    "Content-Type": "audio/mpeg",
                    "x-amz-meta-expected-size": "123",
                },
            }
        )
    )

    result = store.presign_post("workspace/uploads/id/file.mp3", "audio/mpeg", 123)

    assert result["url"] == "https://storage.example/podcasts"
    assert ["content-length-range", 123, 123] in calls[0]["Conditions"]
    assert {"Content-Type": "audio/mpeg"} in calls[0]["Conditions"]
    assert {"x-amz-meta-expected-size": "123"} in calls[0]["Conditions"]


@pytest.mark.parametrize(
    ("head", "message"),
    [
        ({"content_length": 0, "metadata": {"expected-size": "0"}}, "empty"),
        ({"content_length": 101, "metadata": {"expected-size": "101"}}, "exceeds"),
        ({"content_length": 50, "metadata": {}}, "signed size metadata"),
        (
            {"content_length": 50, "metadata": {"expected-size": "51"}},
            "does not match",
        ),
    ],
)
def test_pipeline_rejects_uploads_outside_signed_policy(
    head: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(MediaValidationError, match=message):
        _validated_upload_head(head, 100)


def test_pipeline_accepts_object_matching_signed_policy() -> None:
    result = _validated_upload_head(
        {
            "content_length": 50,
            "content_type": "audio/mpeg",
            "metadata": {"expected-size": "50"},
        },
        100,
    )

    assert result == (50, "audio/mpeg")
