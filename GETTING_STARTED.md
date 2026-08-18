# Getting started

This guide covers the native desktop build first and the Docker/server mode
second. The default Demo profile requires no API key.

## 1. Choose a mode

Use **desktop mode** when one person should install and run the application on a
Mac or Windows PC without PostgreSQL, Redis, MinIO, Docker, or a separately
managed web server.

Use **server mode** when multiple processes, external clients, PostgreSQL
search, object storage, OIDC, or network access are required.

## 2. Build the macOS desktop application

Install:

```bash
xcode-select --install
brew install python@3.12 uv node rustup-init
rustup-init -y
source "$HOME/.cargo/env"
```

Node.js 22 is recommended. Confirm the tools:

```bash
python3.12 --version
uv --version
node --version
npm --version
rustc --version
cargo --version
```

From the repository root:

```bash
./scripts/build-desktop.sh
```

The script performs these operations:

1. resolves the native Rust target;
2. downloads pinned FFmpeg and FFprobe assets for that target;
3. records their SHA-256 values and upstream metadata;
4. creates the Python 3.12 environment;
5. bundles the FastAPI engine with PyInstaller;
6. stages all external binaries using Tauri's target-suffixed naming;
7. installs frontend dependencies;
8. builds the native Tauri bundle.

Open the `.app` or `.dmg` generated under:

```text
frontend/src-tauri/target/<target>/release/bundle/
```

Unsigned local builds may require Control-click → Open on first launch. For
normal distribution, sign and notarize the application instead of asking users
to bypass Gatekeeper.

## 3. Build the Windows desktop application

Install:

- Python 3.12 x64;
- uv;
- Node.js 22 x64;
- Rust using the `stable-x86_64-pc-windows-msvc` toolchain;
- Visual Studio 2022 Build Tools with Desktop development with C++.

In PowerShell from the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build-desktop.ps1
```

Installers are generated under:

```text
frontend\src-tauri\target\x86_64-pc-windows-msvc\release\bundle\
```

## 4. Build all supported targets in GitHub Actions

Open **Actions → Build desktop installers → Run workflow**, or push a version
tag:

```bash
git tag v0.2.0
git push origin v0.2.0
```

Download the three workflow artifacts after completion. Builds are native:
macOS runners produce macOS bundles and the Windows runner produces Windows
installers. The repository does not claim that a Windows installer can be
reliably produced from macOS, or vice versa.

## 5. First desktop launch

The Tauri host starts the packaged engine on a random `127.0.0.1` port and
passes the webview a per-launch token. Startup can take longer on the first run
because the packaged Python runtime initializes and SQLite creates its schema.

The app opens in Demo mode. To use a real provider:

1. open **Settings**;
2. select **OpenAI-compatible** or **Custom**;
3. enter the base URL when using a gateway;
4. enter a shared key or provider-specific keys;
5. confirm model names and embedding dimension;
6. save.

The engine restarts, but the database and media library remain in place.

### OpenAI-compatible profile

Typical fields:

```text
AI profile: OpenAI-compatible
Base URL: empty for the default OpenAI endpoint, otherwise gateway /v1 URL
Shared API key: provider key
Transcription model: provider diarized/audio model
Embedding model: provider embedding model
LLM model: provider structured-output model
LLM API: Responses or Chat Completions
Embedding dimension: exact model dimension
```

Separate transcription, embedding, and LLM keys override the shared key.

### Custom profile

Custom mode allows, for example:

- WebSocket STT + OpenAI-compatible embeddings + OpenAI-compatible LLM;
- OpenAI transcription + deterministic demo embeddings + local Codex CLI;
- demo transcription for interface testing with a real LLM disabled.

The provider capabilities endpoint and settings validation expose configuration
errors rather than silently substituting another provider.

## 6. Import content

The interface accepts:

- local audio or video upload;
- direct media URL;
- RSS feed or episode URL;
- Apple Podcasts episode URL;
- Spotify episode URL, when it can be resolved to an authorized public RSS
  enclosure.

Use content you are authorized to process. Catalog resolution does not bypass
DRM, subscriptions, login walls, or access controls.

A processing job proceeds through:

```text
resolve_source
  → acquire_media
  → normalize_audio
  → transcribe
  → index
  → summarize
  → finalize
```

The local executor stores job state in SQLite. Closing the application between
steps is safe; running steps are returned to pending and resumed on the next
launch. Cancellation is cooperative and cannot forcibly interrupt a provider
request already in progress.

## 7. Use the episode workspace

For a ready episode, the application provides:

- playback with expiring signed local URLs;
- summary chapters and takeaways linked to timestamps;
- paginated transcript search;
- speaker renaming;
- grounded chat with literal transcript citations;
- Markdown, JSON, SRT, and VTT exports.

Exports are fetched with the desktop session token and written only after a
native save destination is selected.

## 8. Back up or move a desktop library

Close the application and copy its complete application-data directory. It
contains the SQLite database and the corresponding object files; copying only
one of them creates an incomplete backup.

The runtime-selected path follows the operating system's standard application
data location for `com.thalesmms.podcast-intelligence`. Common locations are
under:

- macOS: `~/Library/Application Support/`;
- Windows: `%APPDATA%` or the Tauri-resolved application data directory.

Do not depend on a hard-coded path; use the runtime path reported by the app or
inspect Tauri's resolved data directory.

Provider credentials are in `settings.json`. Treat backups as sensitive.

## 9. Recover from invalid settings

If a bad endpoint, unsupported model, or missing key prevents engine startup,
the startup screen offers two safe actions:

- retry after correcting an environmental issue;
- reset provider settings to Demo and restart.

The reset changes provider configuration only. It does not delete the database,
media, transcripts, summaries, or queued jobs.

## 10. Run server mode with Docker

Requirements:

- Docker Engine or Docker Desktop;
- Compose v2;
- Python 3 on the host only for the smoke script.

```bash
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
```

Endpoints:

- application: `http://localhost:3000`;
- REST/OpenAPI: `http://localhost:8000/docs`;
- MCP: `http://localhost:8001/mcp`;
- MinIO console: `http://localhost:9001`.

Create a complete synthetic demo episode:

```bash
docker compose run --rm api python -m podcast_intelligence.cli seed-demo
./scripts/smoke_test.sh
```

Do not run `docker compose down -v` when PostgreSQL or MinIO volumes contain data
that must be retained.

## 11. Development checks

```bash
make check
make desktop-check
```

`make check` runs Python and frontend formatting, linting, typing, and tests.
`make desktop-check` adds Rust formatting/checks and desktop-specific targeted
tests. Native packaging is intentionally separate because each target requires
its own operating system.

More detail:

- [Architecture](docs/architecture.md)
- [Desktop packaging](docs/desktop-packaging.md)
- [Deployment](docs/deployment.md)
- [Security](SECURITY.md)
- [Known limitations](docs/known-limitations.md)
