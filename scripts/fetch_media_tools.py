from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPOSITORY = "descriptinc/ffmpeg-ffprobe-static"
RELEASE_TAG = "b6.1.2-rc.1"
PLATFORM_BY_TARGET = {
    "aarch64-apple-darwin": "darwin-arm64",
    "x86_64-apple-darwin": "darwin-x64",
    "x86_64-pc-windows-msvc": "win32-x64",
    "x86_64-unknown-linux-gnu": "linux-x64",
    "aarch64-unknown-linux-gnu": "linux-arm64",
}


def request(url: str) -> urllib.request.Request:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Podcast-Intelligence-desktop-build",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(request(url), timeout=60) as response:
        return json.load(response)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(asset: dict[str, Any], destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(request(str(asset["browser_download_url"])), timeout=300) as response:
        with temporary.open("wb") as target:
            while block := response.read(1024 * 1024):
                target.write(block)
    actual = sha256(temporary)
    expected = str(asset.get("digest") or "")
    if expected.startswith("sha256:") and actual.lower() != expected[7:].lower():
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Checksum mismatch for {asset['name']}")
    temporary.replace(destination)
    return actual


def make_executable(path: Path) -> None:
    if os.name != "nt":
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download pinned FFmpeg and FFprobe sidecars.")
    parser.add_argument("--target", required=True, choices=sorted(PLATFORM_BY_TARGET))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--release", default=RELEASE_TAG)
    args = parser.parse_args()

    platform_name = PLATFORM_BY_TARGET[args.target]
    suffix = ".exe" if "windows" in args.target else ""
    required_assets = {
        f"ffmpeg-{platform_name}": args.output_dir / f"ffmpeg{suffix}",
        f"ffprobe-{platform_name}": args.output_dir / f"ffprobe{suffix}",
    }
    optional_assets = {
        f"{platform_name}.LICENSE": args.output_dir / "UPSTREAM-LICENSE.txt",
        f"{platform_name}.README": args.output_dir / "UPSTREAM-README.txt",
    }

    release_url = f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{args.release}"
    metadata = fetch_json(release_url)
    assets = {str(asset["name"]): asset for asset in metadata.get("assets", [])}
    missing = sorted(name for name in required_assets if name not in assets)
    if missing:
        raise RuntimeError(f"Release {args.release} is missing required assets: {', '.join(missing)}")

    manifest: dict[str, Any] = {
        "repository": REPOSITORY,
        "release_tag": args.release,
        "release_id": metadata.get("id"),
        "target": args.target,
        "platform_asset": platform_name,
        "files": {},
    }
    for name, destination in required_assets.items():
        digest = download(assets[name], destination)
        make_executable(destination)
        manifest["files"][destination.name] = {
            "release_asset": name,
            "sha256": digest,
        }
        print(destination.resolve())

    for name, destination in optional_assets.items():
        asset = assets.get(name)
        if asset is None:
            continue
        digest = download(asset, destination)
        manifest["files"][destination.name] = {
            "release_asset": name,
            "sha256": digest,
        }

    manifest_path = args.output_dir / "SOURCE.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
