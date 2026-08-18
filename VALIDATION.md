# Validation report

Validation date: August 17, 2026.

## Scope

This report covers the migration from the original multi-container web service
to the desktop architecture in this repository: a Tauri host, a React/Vite
interface, and a PyInstaller-packaged Python engine using SQLite, local files,
and an in-process durable job executor.

The objective of the validation was to establish that the migrated source is
internally coherent and that its principal desktop workflow works end to end in
the available Linux environment. It was not possible to produce or execute the
native Windows and macOS bundles in this environment.

## Available validation environment

- Linux x86-64 container;
- Python 3.13.5;
- pre-provisioned Python environment at `/opt/pyvenv` containing the principal
  runtime packages used by the engine;
- Node.js 22.16.0;
- npm 10.9.2;
- TypeScript 5.8.3 available globally;
- FFmpeg 7.1.5;
- Go 1.23.2, present but not used by the selected Tauri architecture.

The following were unavailable:

- Rust and Cargo;
- Docker;
- Windows or macOS build hosts;
- working access to npm, PyPI, Rust, or release-download registries.

Because package registries were unavailable, this validation did not claim a
fresh dependency installation. A small set of temporary import stubs was used
outside the repository only where the pre-provisioned Python environment lacked
optional server-only packages such as pgvector. No stub, credential, generated
database, test audio, or validation-only dependency is included in the source
archive.

## Checks completed successfully

### Desktop engine and backend

- Python bytecode compilation completed for all package, test, build, and
  support scripts.
- JSON-backed vector storage compiled for SQLite while retaining the
  PostgreSQL/pgvector type on the server profile.
- Local object-store tests passed, including path confinement, signed upload and
  download tokens, expiry, size validation, and MIME validation.
- Settings tests passed for desktop defaults, profile expansion, local paths,
  and provider validation.
- Retrieval tests passed for the SQLite implementation, including lexical
  ranking, cosine similarity, model isolation, workspace isolation, episode
  filtering, weighting, and result limits.
- SQLite startup configuration was exercised with foreign-key enforcement, WAL,
  busy timeout, and cross-process job locking.
- The local worker recovered durable dispatch rows and completed the existing
  idempotent seven-step pipeline without Redis or Celery.

### End-to-end desktop workflow

A real WAV fixture was generated locally and processed through the running
FastAPI desktop engine. The following operations completed successfully:

1. engine startup on a random loopback port;
2. authenticated health check;
3. signed local upload;
4. episode and durable job creation;
5. source resolution and media acquisition;
6. FFmpeg normalization to processing WAV and M4A playback media;
7. demo transcription;
8. speaker-aware chunking and SQLite indexing;
9. structured summary creation;
10. hybrid search;
11. grounded chat with materialized transcript citations;
12. JSON, Markdown, SRT, and VTT export;
13. graceful shutdown.

Every pipeline step ended in `completed`:

```text
resolve_source
acquire_media
normalize_audio
transcribe
index
summarize
finalize
```

A second engine process was then started against the same application-data
directory. The episode remained available with status `ready`, confirming
persistence across restarts. Playback was requested with
`Range: bytes=0-127`; the local file endpoint returned HTTP `206` and exactly
128 bytes, which verifies byte-range support required for seekable audio.

### Frontend and repository structure

- Every TypeScript and TSX source file passed a TypeScript transpilation syntax
  pass: 54 files.
- The local frontend import graph resolved successfully: 56 files.
- The English and Brazilian Portuguese catalogs have matching sets of 232 keys.
- Next.js runtime imports and build commands were removed from application
  source; routing now uses React Router and the build entry point is Vite.
- JSON configuration files parsed successfully, including `package.json`,
  `tsconfig.json`, Tauri configuration, and Tauri capabilities.
- YAML parsed successfully for Docker Compose and the native desktop GitHub
  Actions workflow.
- Shell scripts passed `bash -n`.
- The PowerShell build script passed a structural delimiter check.
- `git diff --check` found no whitespace errors.
- The static Vite production-server helper was exercised for index delivery,
  SPA fallback, `HEAD`, immutable asset caching, and rejection of unsupported
  methods.

### Packaging logic

- The source-packaging script creates a deterministic archive layout.
- It excludes virtual environments, package caches, build output, databases,
  installers, sidecar binaries, macOS metadata, and validation artifacts.
- It generates `FILE_MANIFEST.sha256` inside the archive and a separate SHA-256
  file for the ZIP itself.
- The FFmpeg acquisition script pins a release, selects the platform-specific
  archive, computes SHA-256, and verifies a published checksum when one is
  supplied by the release.

## Checks not run in this environment

The following require dependency registries, native target hosts, credentials,
or external services and therefore were not represented as completed:

- `npm install` and a Vite production bundle using freshly installed project
  dependencies;
- the complete Vitest, ESLint, Prettier, and TypeScript project checks against a
  newly installed `node_modules` tree;
- `cargo fmt`, `cargo check`, and `tauri build`;
- a complete PyInstaller sidecar build from a freshly synchronized Python
  environment;
- creation or launch of `.app`, `.dmg`, `.exe`, `.msi`, or NSIS artifacts;
- Apple code signing, Windows Authenticode signing, or Apple notarization;
- real OpenAI-compatible transcription, embedding, or language-model requests;
- real streaming-WebSocket transcription;
- Spotify credential flow, Apple Podcasts resolution, arbitrary public RSS
  feeds, and remote-media downloads;
- Docker Compose expansion, image build, or runtime integration;
- connection of the MCP endpoint from ChatGPT or Codex.

The repository includes native Windows and macOS build scripts and a GitHub
Actions matrix so these checks can be completed on their respective operating
systems. The first trusted, connected build should also regenerate and commit
the npm and uv lock data after installing the migrated dependency graph.

## Interpretation

The available evidence verifies the source migration, SQLite/local-storage
substitutions, internal job execution, desktop HTTP contracts, media processing,
persistence, range playback, and principal product workflow. It does not certify
native installer behavior, production security, provider compatibility,
notarization, or public deployment. Those remain release gates on real macOS and
Windows hosts.
