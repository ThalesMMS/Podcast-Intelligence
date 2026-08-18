from __future__ import annotations

import argparse
import hashlib
import os
import stat
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = "Podcast-Intelligence-Desktop"
FIXED_TIMESTAMP = (2026, 8, 17, 12, 0, 0)

EXCLUDED_PARTS = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vite",
    "__MACOSX",
    "__pycache__",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "target",
}
EXCLUDED_PREFIXES = {
    PurePosixPath("backend/build"),
    PurePosixPath("backend/dist"),
    PurePosixPath("build"),
}
EXCLUDED_NAMES = {
    ".DS_Store",
    ".coverage",
    "FILE_MANIFEST.sha256",
    "tsconfig.tsbuildinfo",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".sqlite", ".sqlite3", ".dmg", ".msi"}


def excluded(relative: PurePosixPath) -> bool:
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return True
    if relative.name in EXCLUDED_NAMES or relative.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if any(relative == prefix or prefix in relative.parents for prefix in EXCLUDED_PREFIXES):
        return True
    if relative.parts[:3] == ("frontend", "src-tauri", "binaries"):
        return relative.name != "README.md"
    if relative.parts[:4] == ("frontend", "src-tauri", "third_party", "ffmpeg"):
        return relative.name in {"SOURCE.json", "UPSTREAM-LICENSE.txt", "UPSTREAM-README.txt"}
    return False


def files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not excluded(PurePosixPath(path.relative_to(ROOT).as_posix()))
    )


def archive_info(name: str, source: Path | None = None) -> ZipInfo:
    info = ZipInfo(name, FIXED_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    mode = 0o644
    if source is not None:
        source_mode = source.stat().st_mode
        if source_mode & stat.S_IXUSR or source.suffix in {".sh", ".command"}:
            mode = 0o755
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.create_system = 3
    return info


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a clean Podcast Intelligence source ZIP")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")

    selected = files()
    manifest_lines: list[str] = []
    with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for source in selected:
            relative = PurePosixPath(source.relative_to(ROOT).as_posix())
            data = source.read_bytes()
            manifest_lines.append(f"{sha256(data)}  {relative.as_posix()}")
            name = f"{ARCHIVE_ROOT}/{relative.as_posix()}"
            archive.writestr(archive_info(name, source), data)
        manifest = ("\n".join(manifest_lines) + "\n").encode()
        archive.writestr(
            archive_info(f"{ARCHIVE_ROOT}/FILE_MANIFEST.sha256"),
            manifest,
        )

    os.replace(temporary, output)
    digest = sha256(output.read_bytes())
    checksum_path = output.with_suffix(output.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    print(output)
    print(checksum_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
