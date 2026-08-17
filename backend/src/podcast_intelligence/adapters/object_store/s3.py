from __future__ import annotations

from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from podcast_intelligence.config import Settings


class S3ObjectStore:
    def __init__(self, settings: Settings) -> None:
        common: dict[str, Any] = {
            "aws_access_key_id": settings.s3_access_key,
            "aws_secret_access_key": settings.s3_secret_key,
            "region_name": settings.s3_region,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            use_ssl=settings.s3_secure,
            **common,
        )
        self._public_client = boto3.client(
            "s3",
            endpoint_url=settings.s3_public_endpoint_url,
            use_ssl=settings.s3_public_endpoint_url.startswith("https://"),
            **common,
        )
        self.bucket = settings.s3_bucket

    def health(self) -> None:
        self._client.head_bucket(Bucket=self.bucket)

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self.bucket)

    def presign_post(
        self,
        object_key: str,
        content_type: str,
        expected_size_bytes: int,
        expires_seconds: int = 900,
    ) -> dict[str, Any]:
        expected_size = str(expected_size_bytes)
        result = self._public_client.generate_presigned_post(
            Bucket=self.bucket,
            Key=object_key,
            Fields={
                "Content-Type": content_type,
                "x-amz-meta-expected-size": expected_size,
            },
            Conditions=[
                {"Content-Type": content_type},
                {"x-amz-meta-expected-size": expected_size},
                ["content-length-range", expected_size_bytes, expected_size_bytes],
            ],
            ExpiresIn=expires_seconds,
        )
        return {
            "url": str(result["url"]),
            "fields": {str(key): str(value) for key, value in result["fields"].items()},
        }

    def presign_get(self, object_key: str, expires_seconds: int = 900) -> str:
        return str(
            self._public_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket, "Key": object_key},
                ExpiresIn=expires_seconds,
            )
        )

    def upload_file(self, source: Path, object_key: str, content_type: str | None = None) -> None:
        extra_args = {"ContentType": content_type} if content_type else None
        self._client.upload_file(str(source), self.bucket, object_key, ExtraArgs=extra_args or {})

    def download_file(self, object_key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(self.bucket, object_key, str(destination))

    def head(self, object_key: str) -> dict[str, Any]:
        result = self._client.head_object(Bucket=self.bucket, Key=object_key)
        return {
            "content_length": int(result.get("ContentLength", 0)),
            "content_type": result.get("ContentType"),
            "etag": str(result.get("ETag", "")).strip('"'),
            "metadata": result.get("Metadata", {}),
        }

    def delete(self, object_key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=object_key)
