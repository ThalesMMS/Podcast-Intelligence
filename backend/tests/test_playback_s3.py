from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import httpx
import pytest

from podcast_intelligence.adapters.object_store.s3 import S3ObjectStore
from podcast_intelligence.config import Settings

_REQUIRED_ENV = (
    "TEST_S3_ENDPOINT_URL",
    "TEST_S3_ACCESS_KEY",
    "TEST_S3_SECRET_KEY",
    "TEST_S3_BUCKET",
)


@pytest.mark.skipif(
    not all(os.environ.get(name) for name in _REQUIRED_ENV),
    reason="S3 test endpoint and credentials are required for the playback integration test",
)
def test_expired_playback_url_can_be_renewed_for_range_request(tmp_path: Path) -> None:
    endpoint = os.environ["TEST_S3_ENDPOINT_URL"]
    settings = Settings(
        s3_endpoint_url=endpoint,
        s3_public_endpoint_url=os.environ.get("TEST_S3_PUBLIC_ENDPOINT_URL", endpoint),
        s3_access_key=os.environ["TEST_S3_ACCESS_KEY"],
        s3_secret_key=os.environ["TEST_S3_SECRET_KEY"],
        s3_bucket=os.environ["TEST_S3_BUCKET"],
        s3_region=os.environ.get("TEST_S3_REGION", "us-east-1"),
        s3_secure=endpoint.startswith("https://"),
    )
    store = S3ObjectStore(settings)
    store.ensure_bucket()
    object_key = f"playback-renewal-tests/{uuid.uuid4()}.m4a"
    source = tmp_path / "audio.m4a"
    source.write_bytes(b"0123456789")
    store.upload_file(source, object_key, "audio/mp4")

    try:
        expired_url = store.presign_get(object_key, expires_seconds=1)
        initial = httpx.get(expired_url, headers={"Range": "bytes=2-5"})
        assert initial.status_code == 206
        assert initial.content == b"2345"
        assert initial.headers["content-range"] == "bytes 2-5/10"

        time.sleep(2)
        expired = httpx.get(expired_url, headers={"Range": "bytes=6-9"})
        assert expired.status_code in {400, 403}

        renewed_url = store.presign_get(object_key, expires_seconds=60)
        renewed = httpx.get(renewed_url, headers={"Range": "bytes=6-9"})
        assert renewed.status_code == 206
        assert renewed.content == b"6789"
        assert renewed.headers["content-range"] == "bytes 6-9/10"
    finally:
        store.delete(object_key)
