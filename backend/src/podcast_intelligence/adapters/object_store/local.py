from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import mimetypes
import shutil
import time
from pathlib import Path
from typing import Any, Literal

from podcast_intelligence.config import Settings
from podcast_intelligence.domain.errors import MediaValidationError, NotFoundError


class LocalObjectStore:
    """Filesystem-backed object store used by packaged desktop builds.

    Signed URLs preserve the existing upload/playback contract without exposing
    arbitrary paths. Object keys are always resolved below the application data
    directory and metadata is stored in a small adjacent JSON file.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.local_storage_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self._secret = settings.app_secret_key.encode("utf-8")
        self._base_url = settings.desktop_api_base_url.rstrip("/")

    def health(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        probe = self.root / ".health"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)

    def ensure_bucket(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, object_key: str) -> Path:
        if not object_key or object_key.startswith(("/", "\\")):
            raise MediaValidationError("Invalid local object key")
        candidate = (self.root / object_key).resolve()
        root = self.root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise MediaValidationError("Object key escapes local storage") from exc
        return candidate

    def _metadata_path(self, object_key: str) -> Path:
        path = self._path(object_key)
        return path.with_name(path.name + ".metadata.json")

    def _sign(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
        signature = hmac.new(self._secret, encoded, hashlib.sha256).digest()
        return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    def verify_token(self, token: str, operation: Literal["get", "put"]) -> dict[str, Any]:
        try:
            encoded_text, signature_text = token.split(".", 1)
            encoded = encoded_text.encode("ascii")
            expected = hmac.new(self._secret, encoded, hashlib.sha256).digest()
            signature = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
            if base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii") != signature_text:
                raise ValueError("non-canonical signature")
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature")
            raw = base64.urlsafe_b64decode(encoded_text + "=" * (-len(encoded_text) % 4))
            if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != encoded_text:
                raise ValueError("non-canonical payload")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("payload")
            if payload.get("op") != operation:
                raise ValueError("operation")
            if int(payload.get("exp", 0)) < int(time.time()):
                raise ValueError("expired")
            key = payload.get("key")
            if not isinstance(key, str):
                raise ValueError("key")
            self._path(key)
            return payload
        except (binascii.Error, ValueError, TypeError, json.JSONDecodeError, UnicodeError) as exc:
            raise MediaValidationError("Invalid or expired local storage token") from exc

    def presign_post(
        self,
        object_key: str,
        content_type: str,
        expected_size_bytes: int,
        expires_seconds: int = 900,
    ) -> dict[str, Any]:
        self._path(object_key)
        token = self._sign(
            {
                "op": "put",
                "key": object_key,
                "content_type": content_type,
                "size": expected_size_bytes,
                "exp": int(time.time()) + expires_seconds,
            }
        )
        return {
            "url": f"{self._base_url}/v1/desktop-storage/upload/{token}",
            "fields": {},
        }

    def presign_get(self, object_key: str, expires_seconds: int = 900) -> str:
        self._path(object_key)
        token = self._sign(
            {
                "op": "get",
                "key": object_key,
                "exp": int(time.time()) + expires_seconds,
            }
        )
        return f"{self._base_url}/v1/desktop-storage/files/{token}"

    def write_uploaded_file(
        self,
        *,
        object_key: str,
        source: Path,
        content_type: str,
        expected_size_bytes: int,
    ) -> None:
        actual_size = source.stat().st_size
        if actual_size != expected_size_bytes:
            raise MediaValidationError(
                f"Uploaded file size {actual_size} does not match declared size {expected_size_bytes}"
            )
        destination = self._path(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), destination)
        self._write_metadata(
            object_key,
            {
                "content_type": content_type,
                "expected-size": str(expected_size_bytes),
            },
        )

    def _write_metadata(self, object_key: str, metadata: dict[str, Any]) -> None:
        path = self._metadata_path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    def _read_metadata(self, object_key: str) -> dict[str, Any]:
        path = self._metadata_path(object_key)
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def upload_file(self, source: Path, object_key: str, content_type: str | None = None) -> None:
        destination = self._path(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        resolved_content_type = content_type or mimetypes.guess_type(destination.name)[0]
        self._write_metadata(
            object_key,
            {
                "content_type": resolved_content_type,
                "expected-size": str(destination.stat().st_size),
            },
        )

    def download_file(self, object_key: str, destination: Path) -> None:
        source = self._path(object_key)
        if not source.is_file():
            raise NotFoundError("Stored media object not found")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    def head(self, object_key: str) -> dict[str, Any]:
        path = self._path(object_key)
        if not path.is_file():
            raise NotFoundError("Stored media object not found")
        metadata = self._read_metadata(object_key)
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return {
            "content_length": path.stat().st_size,
            "content_type": metadata.get("content_type") or mimetypes.guess_type(path.name)[0],
            "etag": digest.hexdigest(),
            "metadata": {
                "expected-size": str(metadata.get("expected-size", path.stat().st_size)),
            },
        }

    def delete(self, object_key: str) -> None:
        self._path(object_key).unlink(missing_ok=True)
        self._metadata_path(object_key).unlink(missing_ok=True)

    def local_path_for_token(self, token: str) -> tuple[Path, dict[str, Any]]:
        payload = self.verify_token(token, "get")
        path = self._path(str(payload["key"]))
        if not path.is_file():
            raise NotFoundError("Stored media object not found")
        return path, self._read_metadata(str(payload["key"]))
