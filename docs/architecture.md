# Architecture

## Goals

Podcast Intelligence receives authorized podcast/audio sources, preserves media
and transcripts as primary evidence, produces traceable knowledge artifacts,
and exposes them through a desktop interface, REST, and MCP. The architecture
must:

1. keep summaries and answers linked to timed transcript segments;
2. allow STT, embedding, and LLM providers to be replaced independently;
3. make long jobs idempotent and resumable;
4. isolate stored data by workspace;
5. reject unsafe remote-media fetches;
6. run as a self-contained single-user desktop application;
7. retain a scalable server deployment without forking domain logic.

## One domain layer, two runtime profiles

The repository is a modular monolith with two composition roots.

### Desktop profile

```text
┌───────────────────────────────────────────────────────────┐
│ Tauri process (Rust)                                      │
│  native window · lifecycle · dialogs · opener · app paths │
│                         │                                 │
│               per-launch loopback token                   │
│                         ▼                                 │
│ React/Vite assets ──HTTP──► packaged FastAPI engine       │
│                                  │                        │
│                 ┌────────────────┼────────────────┐       │
│                 ▼                ▼                ▼       │
│              SQLite       local object store   job pool   │
│                 │                │                │       │
│                 └──────────── existing pipeline ─┘       │
│                                  │                        │
│                           FFmpeg/FFprobe                   │
│                                  │                        │
│                    STT / embeddings / LLM ports           │
│                                  │                        │
│                        optional local MCP process          │
└───────────────────────────────────────────────────────────┘
```

Tauri starts the engine sidecar, reads a structured `listening` event from its
stdout, waits for `/health/ready`, and only then exposes the API address to the
frontend. The API binds to a random loopback port. MCP prefers loopback port 8001 and falls back to an available port. The REST API requires a
random per-launch `X-Desktop-Token`; upload/playback routes use short-lived HMAC
URLs instead.

### Server profile

```text
Browser / REST client / ChatGPT / Codex
                │
        ┌───────┴────────┐
        │                │
   Vite web UI       MCP server
        │                │
        └───────┬────────┘
                │
          FastAPI API
                │
       commands + queries
                │
       PostgreSQL + pgvector
                │
         Celery / Redis
                │
  ┌─────────────┼──────────────────┐
  │             │                  │
resolvers     FFmpeg         AI provider ports
  │             │          STT / embeddings / LLM
  └─────────────┼──────────────────┘
                │
              S3/MinIO
```

API, worker, beat, and MCP remain separate processes in server mode. Both modes
reuse the same models, services, adapters, API contracts, and tests wherever the
storage/backend difference does not require a dialect-specific implementation.

## Module boundaries

- `domain`: provider-neutral types, ports, and errors.
- `adapters/resolvers`: upload, direct media, RSS, Apple, and Spotify.
- `adapters/media`: safe HTTP downloads, transcript loading, and FFmpeg.
- `adapters/object_store`: S3-compatible and signed local-filesystem stores.
- `adapters/ai`: demo, OpenAI-compatible, streaming STT, and Codex CLI.
- `services/imports`: episode/job creation and durable dispatch outbox.
- `services/pipeline`: idempotent processing state machine.
- `services/chunking`: speaker-aware transcript segmentation.
- `services/retrieval`: PostgreSQL and portable desktop hybrid search.
- `services/summarization`: validated hierarchical synthesis.
- `services/chat`: conversations, retrieval, answers, and citations.
- `api`: stable HTTP contracts and authorization.
- `worker`: Celery server runtime.
- `desktop`: packaged engine entrypoint and in-process worker runtime.
- `mcp_server`: streamable-HTTP tools.
- `frontend/src-tauri`: native host, bundle, permissions, and sidecars.

## Pipeline and durability

```text
resolve_source
  → acquire_media
  → normalize_audio
  → transcribe
  → index
  → summarize
  → finalize
```

Every step stores status, attempts, timestamps, error text, and metrics. A step
is skipped when compatible output already exists. Compatibility includes
transcript versions and embedding models where relevant.

### Server locking

PostgreSQL advisory locks serialize a job by ID. The lock belongs to the
connection, so a crashed worker releases it automatically. Celery redelivery is
safe because completed steps are reused.

### Desktop locking and recovery

SQLite stores the same job and dispatch rows. A bounded thread pool executes the
pipeline, while a poller claims durable outbox rows. Process-local job locks
prevent duplicate execution. At startup, jobs left in `running` or `retrying`
are changed back to `queued`, running steps return to `pending`, and dispatch
rows become available again. Transient provider/network failures use bounded
exponential retry; exhausted rows are dead-lettered while preserving the
pipeline's failure context.

## Media storage

### Desktop

Object keys retain the original workspace/episode layout but resolve beneath a
single private `objects/` root. Path traversal is rejected. Upload and playback
URLs contain signed JSON claims with operation, object key, expiry, and expected
upload metadata. The upload endpoint verifies exact byte count and MIME type.
The player receives an expiring signed URL and renews it as needed.

### Server

The S3 adapter uses presigned POST and GET URLs and can target MinIO or another
S3-compatible service.

## Database and vector representation

The SQLAlchemy model uses PostgreSQL `vector` in server mode and JSON arrays in
SQLite. This preserves the same embedding values and model metadata.

### PostgreSQL retrieval

- pgvector cosine distance;
- `websearch_to_tsquery` and `ts_rank_cd` using the `simple` configuration;
- model-aware vector filtering;
- weighted lexical/vector merge.

### SQLite retrieval

- deterministic Unicode token coverage and exact-phrase bonus;
- cosine similarity calculated in Python;
- same configurable lexical/vector weights;
- latest ready transcript and workspace filtering;
- safety cap of 10,000 candidate chunks per query.

The desktop fallback deliberately avoids optional SQLite native extensions, so
packaged behavior is identical on Windows and macOS. PostgreSQL remains the
preferred profile for very large multi-user collections.

## Immutable and derived artifacts

- **Original**: file supplied or downloaded from an authorized source.
- **Processing**: mono PCM WAV, 16 kHz by default.
- **Playback**: M4A/AAC for the player.
- **Transcript**: versioned full text and timed speaker segments.
- **KnowledgeChunk**: text, segment IDs, speakers, token count, and vector.
- **Summary**: structured document bound to a transcript version.
- **Message**: answer, retrieved context, and materialized citations.

Generated summaries and answers do not become evidence. Literal citation text
is read from stored transcript segments after model output is validated.

## Provider isolation

`ProviderRegistry` composes independent ports for:

- transcription;
- embeddings;
- language-model generation;
- source resolution;
- object storage;
- media processing.

The desktop settings dialog writes supported provider values to `settings.json`
and restarts the engine. The engine converts allowed values to environment
settings before importing application modules, preserving the existing
Pydantic configuration and provider validation.

## MCP

Desktop mode can start a second instance of the packaged engine in MCP-only
mode. It shares the same SQLite database and provider configuration, prefers loopback port 8001, falls back when necessary, and exposes the existing tools:

- `search`;
- `fetch`;
- `list_episodes`;
- `ask_episode`;
- `create_summary`.

This local MCP service is intended for a trusted user on the same computer. It
is not a public multi-user OAuth deployment.

## Frontend

The prior Next.js application was migrated to React 19 + Vite + HashRouter.
Existing components, CSS, polling behavior, transcript virtualization,
localization, playback recovery, and accessibility helpers were retained.

A runtime adapter separates browser/server behavior from Tauri behavior:

- browser mode reads `VITE_API_URL` and uses normal downloads/links;
- Tauri mode receives the dynamic API URL/token through an invoke command;
- exports use native save dialogs;
- external HTTP(S) links use the opener plugin;
- invalid engine settings expose a recovery screen.

## Packaging boundary

PyInstaller creates one engine executable per operating system/architecture.
Tauri requires external sidecars named with the target triple and bundles the
engine, FFmpeg, and FFprobe alongside the native host. The pipeline therefore
builds natively on each target rather than attempting unsupported universal
cross-compilation.

See [Desktop packaging](desktop-packaging.md).
