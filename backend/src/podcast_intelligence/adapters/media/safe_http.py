from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from podcast_intelligence.config import Settings
from podcast_intelligence.domain.errors import (
    MediaValidationError,
    PodcastIntelligenceError,
    SourceResolutionError,
    UnsafeRemoteURLError,
)
from podcast_intelligence.domain.types import DownloadedMedia


class _ContentLengthTooLargeError(ValueError):
    pass


def _parse_content_length(value: str | None, max_bytes: int) -> int | None:
    if value is None:
        return None
    if not value or not value.isascii() or not value.isdigit():
        raise ValueError("Content-Length must contain only ASCII digits")
    normalized = value.lstrip("0") or "0"
    maximum = str(max_bytes)
    if len(normalized) > len(maximum) or (len(normalized) == len(maximum) and normalized > maximum):
        raise _ContentLengthTooLargeError("Content-Length exceeds the configured limit")
    return int(normalized)


def _validate_declared_content_length(
    value: str | None,
    max_bytes: int,
    *,
    error_type: type[PodcastIntelligenceError],
    too_large_message: str,
    invalid_message: str,
) -> None:
    try:
        _parse_content_length(value, max_bytes)
    except _ContentLengthTooLargeError as exc:
        raise error_type(too_large_message) from exc
    except ValueError as exc:
        raise error_type(invalid_message) from exc


class SafeHTTPClient:
    """HTTP helper with conservative SSRF and response-size controls.

    This blocks obvious internal destinations and revalidates every redirect.
    Production deployments should additionally enforce egress policy at the
    network layer because application-only DNS checks cannot eliminate every
    DNS-rebinding race.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.Client(
            timeout=httpx.Timeout(settings.download_timeout_seconds, connect=20.0),
            follow_redirects=False,
            headers={"User-Agent": settings.http_user_agent, "Accept": "*/*"},
        )

    def close(self) -> None:
        """Release the underlying HTTP transport.

        ``httpx.Client.close`` is idempotent, which makes this safe to call from
        lifecycle cleanup paths even when an earlier shutdown step already ran.
        """

        self.client.close()

    @staticmethod
    def _is_public_ip(address: str | int) -> bool:
        ip = ipaddress.ip_address(address)
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )

    def validate_url(self, url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise UnsafeRemoteURLError("Only http and https URLs are accepted")
        if parsed.username or parsed.password:
            raise UnsafeRemoteURLError("URLs containing user information are rejected")
        if not parsed.hostname:
            raise UnsafeRemoteURLError("URL has no hostname")
        if parsed.port not in {None, 80, 443}:
            raise UnsafeRemoteURLError("Only ports 80 and 443 are allowed")

        host = parsed.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            raise UnsafeRemoteURLError("Local hostnames are rejected")

        try:
            infos = socket.getaddrinfo(
                host, parsed.port or (443 if parsed.scheme == "https" else 80)
            )
        except socket.gaierror as exc:
            raise UnsafeRemoteURLError(f"Could not resolve remote hostname: {host}") from exc

        addresses = {info[4][0] for info in infos}
        if not addresses or any(not self._is_public_ip(address) for address in addresses):
            raise UnsafeRemoteURLError("Remote hostname resolves to a non-public address")
        return url

    def _request_with_redirects(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        max_redirects: int = 5,
    ) -> httpx.Response:
        current = self.validate_url(url)
        for _ in range(max_redirects + 1):
            response = self.client.request(method, current, headers=headers, data=data)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                response.close()
                if not location:
                    raise SourceResolutionError("Remote redirect did not include a location")
                current = self.validate_url(urljoin(current, location))
                if response.status_code == 303:
                    method = "GET"
                    data = None
                continue
            return response
        raise SourceResolutionError("Remote URL exceeded the redirect limit")

    def fetch_bytes(self, url: str, *, max_bytes: int = 10 * 1024 * 1024) -> bytes:
        current = self.validate_url(url)
        for _ in range(6):
            with self.client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise SourceResolutionError("Remote redirect did not include a location")
                    current = self.validate_url(urljoin(current, location))
                    continue

                response.raise_for_status()
                _validate_declared_content_length(
                    response.headers.get("content-length"),
                    max_bytes,
                    error_type=SourceResolutionError,
                    too_large_message="Remote response is larger than the configured limit",
                    invalid_message="Remote response returned an invalid Content-Length header",
                )

                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=256 * 1024):
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise SourceResolutionError(
                            "Remote response is larger than the configured limit"
                        )
                return bytes(content)
        raise SourceResolutionError("Remote URL exceeded the redirect limit")

    def fetch_text(self, url: str, *, max_bytes: int = 10 * 1024 * 1024) -> str:
        raw = self.fetch_bytes(url, max_bytes=max_bytes)
        return raw.decode("utf-8", errors="replace")

    def fetch_json(self, url: str, *, max_bytes: int = 10 * 1024 * 1024) -> dict[str, Any]:
        raw = self.fetch_bytes(url, max_bytes=max_bytes)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SourceResolutionError("Remote endpoint did not return valid JSON") from exc
        if not isinstance(parsed, dict):
            raise SourceResolutionError("Remote JSON response was not an object")
        return parsed

    def post_form_json(
        self,
        url: str,
        data: dict[str, str],
        *,
        headers: dict[str, str] | None = None,
        max_bytes: int = 2 * 1024 * 1024,
    ) -> dict[str, Any]:
        response = self._request_with_redirects("POST", url, headers=headers, data=data)
        try:
            response.raise_for_status()
            if len(response.content) > max_bytes:
                raise SourceResolutionError("Remote JSON response was too large")
            parsed = response.json()
            if not isinstance(parsed, dict):
                raise SourceResolutionError("Remote JSON response was not an object")
            return parsed
        finally:
            response.close()

    def download(self, url: str, destination_dir: Path | None = None) -> DownloadedMedia:
        current = self.validate_url(url)
        destination_dir = destination_dir or Path(tempfile.mkdtemp(prefix="podcast-download-"))
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / "source-media"

        for _ in range(6):
            with self.client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise SourceResolutionError("Remote redirect did not include a location")
                    current = self.validate_url(urljoin(current, location))
                    continue

                response.raise_for_status()
                _validate_declared_content_length(
                    response.headers.get("content-length"),
                    self.settings.max_remote_file_bytes,
                    error_type=MediaValidationError,
                    too_large_message="Remote media exceeds MAX_REMOTE_FILE_BYTES",
                    invalid_message="Remote media returned an invalid Content-Length header",
                )

                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                allowed_prefixes = ("audio/", "video/", "application/octet-stream")
                if content_type and not content_type.startswith(allowed_prefixes):
                    raise MediaValidationError(
                        f"Remote URL returned unsupported content type: {content_type}"
                    )

                digest = hashlib.sha256()
                total = 0
                with destination.open("wb") as output:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        total += len(chunk)
                        if total > self.settings.max_remote_file_bytes:
                            output.close()
                            destination.unlink(missing_ok=True)
                            raise MediaValidationError("Remote media exceeded the size limit")
                        digest.update(chunk)
                        output.write(chunk)

                if total == 0:
                    destination.unlink(missing_ok=True)
                    raise MediaValidationError("Remote media was empty")

                return DownloadedMedia(
                    path=destination,
                    content_type=content_type or None,
                    size_bytes=total,
                    sha256=digest.hexdigest(),
                    final_url=current,
                )

        raise SourceResolutionError("Remote media exceeded the redirect limit")
