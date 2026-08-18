from __future__ import annotations

import argparse
import atexit
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

_USER_SETTING_NAMES = {
    "AI_PROFILE",
    "TRANSCRIPTION_PROVIDER",
    "EMBEDDING_PROVIDER",
    "LLM_PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_TRANSCRIPTION_BASE_URL",
    "OPENAI_EMBEDDING_BASE_URL",
    "OPENAI_LLM_BASE_URL",
    "OPENAI_TRANSCRIPTION_API_KEY",
    "OPENAI_EMBEDDING_API_KEY",
    "OPENAI_LLM_API_KEY",
    "OPENAI_TRANSCRIPTION_MODEL",
    "OPENAI_EMBEDDING_MODEL",
    "OPENAI_LLM_MODEL",
    "OPENAI_LLM_API",
    "OPENAI_EMBEDDING_SEND_DIMENSIONS",
    "OPENAI_REASONING_EFFORT",
    "OPENAI_MAX_UPLOAD_BYTES",
    "TRANSCRIPTION_CHUNK_SECONDS",
    "TRANSCRIPTION_CHUNK_BITRATE",
    "EMBEDDING_DIMENSION",
    "EMBEDDING_BATCH_SIZE",
    "STREAMING_STT_URL",
    "STREAMING_STT_API_KEY",
    "STREAMING_STT_MODEL",
    "STREAMING_STT_LANGUAGE",
    "STREAMING_STT_FRAME_SECONDS",
    "STREAMING_STT_BATCH_SECONDS",
    "STREAMING_STT_OPEN_TIMEOUT_SECONDS",
    "STREAMING_STT_CLOSE_TIMEOUT_SECONDS",
    "CODEX_BINARY",
    "CODEX_MODEL",
    "CODEX_TIMEOUT_SECONDS",
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_CLIENT_SECRET",
    "MAX_REMOTE_FILE_BYTES",
    "MAX_AUDIO_DURATION_SECONDS",
    "DOWNLOAD_TIMEOUT_SECONDS",
    "AUDIO_SAMPLE_RATE",
    "AUDIO_CHANNELS",
    "CHUNK_TARGET_TOKENS",
    "CHUNK_OVERLAP_TOKENS",
    "RETRIEVAL_TOP_K",
    "RETRIEVAL_LEXICAL_WEIGHT",
    "RETRIEVAL_VECTOR_WEIGHT",
    "DESKTOP_JOB_WORKERS",
    "PLAYBACK_URL_EXPIRES_SECONDS",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Podcast Intelligence packaged desktop engine")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--api-token", default="")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--mcp-port", type=int, default=0)
    parser.add_argument("--disable-mcp", action="store_true")
    parser.add_argument("--mcp-only", action="store_true")
    parser.add_argument("--log-level", default="info")
    return parser


def _json_event(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)


def _setting_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _load_user_settings(path: Path) -> None:
    if not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read desktop settings: {exc}") from exc
    if not isinstance(raw, dict):
        raise RuntimeError("Desktop settings must contain a JSON object")
    for key, value in raw.items():
        normalized = str(key).upper()
        if normalized not in _USER_SETTING_NAMES or value is None:
            continue
        os.environ[normalized] = _setting_value(value)


def _secret_file(data_dir: Path) -> str:
    path = data_dir / "engine-secret"
    if path.exists():
        secret = path.read_text(encoding="utf-8").strip()
        if len(secret) >= 32:
            return secret
    secret = secrets.token_urlsafe(64)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(secret, encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    if os.name == "nt":
        path.unlink(missing_ok=True)
    temporary.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return secret


def _bundled_binary(name: str) -> str | None:
    executable_name = f"{name}.exe" if os.name == "nt" else name
    roots: list[Path] = []
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        roots.append(Path(frozen_root))
    roots.extend([Path(sys.executable).resolve().parent, Path(__file__).resolve().parents[4]])
    for root in roots:
        for candidate in (root / "bin" / executable_name, root / executable_name):
            if candidate.is_file():
                return str(candidate)
    return None


def _configure_environment(args: argparse.Namespace, *, port: int, mcp_port: int) -> Path:
    data_dir = args.data_dir.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    storage_dir = data_dir / "objects"
    temp_dir = data_dir / "tmp"
    codex_dir = data_dir / "codex"
    storage_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    codex_dir.mkdir(parents=True, exist_ok=True)

    _load_user_settings(data_dir / "settings.json")
    database_path = data_dir / "podcast-intelligence.sqlite3"
    os.environ.update(
        {
            "DESKTOP_MODE": "true",
            "DESKTOP_DATA_DIR": str(data_dir),
            "DESKTOP_API_TOKEN": args.api_token,
            "DESKTOP_API_BASE_URL": f"http://127.0.0.1:{port}",
            "DESKTOP_MCP_ENABLED": "false" if args.disable_mcp else "true",
            "APP_ENV": "production",
            "APP_DEBUG": "false",
            "APP_SECRET_KEY": _secret_file(data_dir),
            "APP_ALLOWED_ORIGINS": ",".join(
                [
                    "tauri://localhost",
                    "http://tauri.localhost",
                    "https://tauri.localhost",
                    "http://localhost",
                    "http://127.0.0.1",
                    "http://localhost:1420",
                    "http://127.0.0.1:1420",
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                ]
            ),
            "AUTH_MODE": "dev",
            "DATABASE_URL": f"sqlite+pysqlite:///{database_path.as_posix()}",
            "JOB_BACKEND": "local",
            "OBJECT_STORE_PROVIDER": "local",
            "LOCAL_STORAGE_DIR": str(storage_dir),
            "PROCESSING_TEMP_DIR": str(temp_dir),
            "CODEX_WORKDIR": str(codex_dir),
            "MCP_HOST": "127.0.0.1",
            "MCP_PORT": str(mcp_port),
        }
    )
    ffmpeg = _bundled_binary("ffmpeg")
    ffprobe = _bundled_binary("ffprobe")
    if ffmpeg:
        os.environ["FFMPEG_BINARY"] = ffmpeg
    if ffprobe:
        os.environ["FFPROBE_BINARY"] = ffprobe
    return data_dir


def _listening_socket(port: int) -> tuple[socket.socket, int]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(2048)
    return listener, int(listener.getsockname()[1])


def _available_port(requested: int) -> int:
    try:
        probe, selected = _listening_socket(requested)
    except OSError:
        if requested == 0:
            raise
        probe, selected = _listening_socket(0)
    probe.close()
    return selected


def _self_command(args: argparse.Namespace, mcp_port: int) -> list[str]:
    common = [
        "--data-dir",
        str(args.data_dir),
        "--api-token",
        args.api_token,
        "--port",
        "0",
        "--mcp-port",
        str(mcp_port),
        "--mcp-only",
        "--log-level",
        args.log_level,
    ]
    if getattr(sys, "frozen", False):
        return [sys.executable, *common]
    return [sys.executable, "-m", "podcast_intelligence.desktop.engine", *common]


def _bootstrap_database() -> None:
    from podcast_intelligence.config import get_settings
    from podcast_intelligence.database import SessionLocal, create_database_schema
    from podcast_intelligence.services.bootstrap import bootstrap_infrastructure
    from podcast_intelligence.services.providers import build_registry

    create_database_schema()
    settings = get_settings()
    registry = build_registry(settings)
    try:
        with SessionLocal() as session:
            bootstrap_infrastructure(session, settings, registry)
    finally:
        registry.http.close()


def _run_mcp_only() -> int:
    _bootstrap_database()
    from podcast_intelligence.mcp_server import mcp, registry

    try:
        mcp.run(transport="streamable-http")
    finally:
        registry.http.close()
    return 0


def _spawn_mcp(args: argparse.Namespace, mcp_port: int) -> subprocess.Popen[bytes] | None:
    if args.disable_mcp:
        return None
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        _self_command(args, mcp_port),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=None,
        creationflags=creation_flags,
    )


def _terminate_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    args = _parser().parse_args()
    api_socket: socket.socket | None = None
    mcp_process: subprocess.Popen[bytes] | None = None
    try:
        if args.mcp_only:
            selected_mcp_port = args.mcp_port or 8001
            _configure_environment(args, port=0, mcp_port=selected_mcp_port)
            return _run_mcp_only()

        api_socket, api_port = _listening_socket(args.port)
        mcp_port = _available_port(args.mcp_port) if not args.disable_mcp else 0
        data_dir = _configure_environment(args, port=api_port, mcp_port=mcp_port)
        _bootstrap_database()
        mcp_process = _spawn_mcp(args, mcp_port)
        atexit.register(_terminate_process, mcp_process)

        from podcast_intelligence.main import app
        import uvicorn

        _json_event(
            "listening",
            api_url=f"http://127.0.0.1:{api_port}",
            mcp_url=(f"http://127.0.0.1:{mcp_port}/mcp" if mcp_process else None),
            data_dir=str(data_dir),
            pid=os.getpid(),
        )
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=api_port,
            log_level=args.log_level,
            access_log=False,
            lifespan="on",
        )
        server = uvicorn.Server(config)
        from podcast_intelligence.desktop.runtime import register_shutdown_callback

        register_shutdown_callback(lambda: setattr(server, "should_exit", True))
        server.run(sockets=[api_socket])
        api_socket = None
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        _json_event("fatal", message=str(exc), error_type=type(exc).__name__)
        return 1
    finally:
        if api_socket is not None:
            api_socket.close()
        _terminate_process(mcp_process)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.default_int_handler)
    raise SystemExit(main())
