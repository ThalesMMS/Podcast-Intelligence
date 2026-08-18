# Desktop migration report

## Objective

Convert the original container-oriented Podcast Intelligence project into a
native application that can be packaged for Windows and macOS while preserving
its ingestion, media, AI, transcript, summary, search, chat, citation, export,
and MCP behavior.

## Result

The project now builds as a Tauri 2 application with a React/Vite interface and
a packaged Python engine. End users do not need Docker, Python, Node.js,
PostgreSQL, Redis, MinIO, or FFmpeg installed. Native sidecars are built per
operating system and architecture.

## Major changes

| Area | Before | After |
|---|---|---|
| UI runtime | Next.js server | Vite assets embedded in Tauri; same UI also served statically in Docker |
| Native shell | none | Tauri/Rust window, lifecycle, dialogs, opener, app paths |
| Backend delivery | Python source/container | PyInstaller engine sidecar |
| Database | PostgreSQL only in normal operation | SQLite desktop; PostgreSQL retained for server |
| Vector storage | pgvector | JSON vectors in SQLite; pgvector retained in server |
| Search | PostgreSQL FTS + pgvector | portable token/phrase + local cosine desktop fallback |
| Jobs | Redis, Celery worker and beat | durable in-process worker pool in desktop |
| Object storage | MinIO/S3 | signed local filesystem in desktop |
| Ports | fixed 3000/8000/8001 | random loopback API port; MCP prefers 8001 with fallback |
| Configuration | `.env` | desktop settings dialog + engine restart; `.env` retained for server |
| Export | browser link | authenticated fetch + native save dialog |
| External links | browser anchor | allowlisted HTTP(S) opener plugin |
| Packaging | Docker images | `.app/.dmg` and Windows installers via native build matrix |

## Preserved domain behavior

The migration reuses, rather than replaces:

- source resolver contracts and Apple/RSS/Spotify matching;
- safe HTTP and media validation;
- FFmpeg normalization and metadata extraction;
- published transcript parsing;
- demo, OpenAI-compatible, streaming STT, and Codex adapters;
- processing step state machine and compatibility checks;
- speaker and segment data model;
- chunking and embeddings;
- structured summary schemas;
- grounded chat and citation materialization;
- JSON/Markdown/SRT/VTT exports;
- REST schemas and MCP tools;
- English/Portuguese interface behavior.

## Desktop-specific additions

- application-data directory isolation;
- stable local HMAC secret and ephemeral API token;
- signed local upload/playback URLs;
- SQLite WAL, foreign keys, busy timeout, and local lock behavior;
- interrupted-job recovery and bounded transient retries;
- provider settings UI and startup recovery to Demo;
- dynamic runtime bridge between Tauri and frontend;
- native save dialog and external-link opener;
- sidecar staging, FFmpeg acquisition, and native CI matrix;
- GPL/source attribution resources for packaged FFmpeg.

## Intentional differences

1. Desktop lexical ranking is deterministic token coverage with phrase bonus,
   not PostgreSQL `ts_rank_cd`.
2. Desktop cosine scoring is performed in Python and scans at most 10,000
   candidate chunks per query.
3. Desktop is a trusted single-user workspace and forces development identity
   internally; it is not an OIDC multi-user service.
4. Desktop settings restart the engine instead of hot-swapping provider objects
   inside a running pipeline.
5. Native builds are target-specific. The project does not claim cross-OS
   PyInstaller/Tauri builds.

## Remaining release work

- regenerate and commit Python/JavaScript locks on a connected trusted machine;
- run the complete native CI matrix;
- test real provider credentials and long media;
- configure Apple signing/notarization and Windows Authenticode;
- decide whether to replace plaintext settings with OS keychain integration;
- add versioned SQLite migrations before changing existing desktop schema;
- add deletion/retention controls and diagnostics/log rotation.

See [VALIDATION.md](VALIDATION.md) for checks completed in the conversion
environment and checks deferred to native connected runners.
