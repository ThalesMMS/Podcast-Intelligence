# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

BACKEND_DIR = Path(SPECPATH).resolve().parent
SOURCE_DIR = BACKEND_DIR / "src"

hiddenimports = []
for package in (
    "podcast_intelligence",
    "mcp",
    "uvicorn",
    "sqlalchemy.dialects.sqlite",
    "pydantic",
    "pydantic_settings",
):
    hiddenimports.extend(collect_submodules(package))

# Runtime metadata is used by provider SDKs and MCP version checks.
datas = []
for distribution in (
    "podcast-intelligence",
    "fastapi",
    "mcp",
    "openai",
    "pydantic",
    "pydantic-settings",
    "sqlalchemy",
    "uvicorn",
):
    try:
        datas.extend(copy_metadata(distribution, recursive=True))
    except Exception:
        # Editable/local distributions do not always expose metadata to PyInstaller.
        pass

for package in ("certifi", "mcp"):
    try:
        datas.extend(collect_data_files(package))
    except Exception:
        pass

a = Analysis(
    [str(SOURCE_DIR / "podcast_intelligence" / "desktop" / "engine.py")],
    pathex=[str(SOURCE_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="podcast-intelligence-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
