from __future__ import annotations

import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = BACKEND_DIR.parent
TAURI_BIN_DIR = REPOSITORY_DIR / "frontend" / "src-tauri" / "binaries"
SPEC_PATH = BACKEND_DIR / "packaging" / "podcast_engine.spec"


def default_target() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        return "aarch64-apple-darwin" if machine in {"arm64", "aarch64"} else "x86_64-apple-darwin"
    if system == "windows":
        return "x86_64-pc-windows-msvc" if machine in {"amd64", "x86_64"} else "aarch64-pc-windows-msvc"
    if system == "linux":
        return "aarch64-unknown-linux-gnu" if machine in {"arm64", "aarch64"} else "x86_64-unknown-linux-gnu"
    raise RuntimeError(f"Unsupported build host: {platform.system()} {platform.machine()}")


def executable_suffix(target: str) -> str:
    return ".exe" if "windows" in target else ""


def require_file(path: str | None, description: str) -> Path:
    if not path:
        discovered = shutil.which(description)
        if discovered:
            return Path(discovered).resolve()
        raise FileNotFoundError(
            f"{description} was not supplied and is not on PATH. Use --{description}."
        )
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{description} not found: {resolved}")
    return resolved


def make_executable(path: Path) -> None:
    if os.name != "nt":
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def copy_sidecar(source: Path, logical_name: str, target: str) -> Path:
    TAURI_BIN_DIR.mkdir(parents=True, exist_ok=True)
    destination = TAURI_BIN_DIR / f"{logical_name}-{target}{executable_suffix(target)}"
    shutil.copy2(source, destination)
    make_executable(destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the PyInstaller engine and stage all Tauri external binaries."
    )
    parser.add_argument("--target", default=default_target())
    parser.add_argument("--ffmpeg", default=os.getenv("PODCAST_FFMPEG_BINARY"))
    parser.add_argument("--ffprobe", default=os.getenv("PODCAST_FFPROBE_BINARY"))
    parser.add_argument("--skip-pyinstaller", action="store_true")
    args = parser.parse_args()

    target = args.target
    ffmpeg = require_file(args.ffmpeg, "ffmpeg")
    ffprobe = require_file(args.ffprobe, "ffprobe")

    build_root = BACKEND_DIR / "build" / "pyinstaller" / target
    dist_dir = build_root / "dist"
    work_dir = build_root / "work"
    dist_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_pyinstaller:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--clean",
                "--noconfirm",
                "--distpath",
                str(dist_dir),
                "--workpath",
                str(work_dir),
                str(SPEC_PATH),
            ],
            cwd=BACKEND_DIR,
            check=True,
        )

    built_engine = dist_dir / f"podcast-intelligence-engine{executable_suffix(target)}"
    if not built_engine.is_file():
        raise FileNotFoundError(f"PyInstaller output was not found: {built_engine}")

    staged = [
        copy_sidecar(built_engine, "podcast-intelligence-engine", target),
        copy_sidecar(ffmpeg, "ffmpeg", target),
        copy_sidecar(ffprobe, "ffprobe", target),
    ]
    for path in staged:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
