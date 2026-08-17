# Architecture

## Goals

The system receives episode files or references, produces traceable knowledge
artifacts, and exposes them through REST, the web interface, and MCP. Its primary
architectural requirements are:

1. preserve audio and transcripts as primary sources;
2. keep every synthesis linked to segments and timestamps;
3. allow providers to be replaced independently;
4. run long jobs idempotently and resumably;
5. isolate data by workspace;
6. never turn catalog links into unauthorized download mechanisms.

## System shape

```text
Browser / REST client / ChatGPT / Codex
                │
        ┌───────┴────────┐
        │                │
   Next.js web       MCP server
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

The repository is a **modular monolith**. The API, worker, and MCP server share
the domain, models, and services, but run as independent processes and
containers. This shape keeps transactions and schema evolution simple without
preventing horizontal worker scaling.

## Module boundaries

- `domain`: provider-agnostic types, ports, and errors.
- `adapters/resolvers`: upload, direct media, RSS, Apple, and Spotify.
- `adapters/media`: URL validation, downloads, and FFmpeg.
- `adapters/object_store`: S3-compatible storage.
- `adapters/ai`: demo, OpenAI, and local Codex CLI.
- `services/imports`: episode and job creation.
- `services/pipeline`: idempotent state machine.
- `services/chunking`: speaker-aware segmentation.
- `services/retrieval`: hybrid lexical/vector search.
- `services/summarization`: validated hierarchical synthesis.
- `services/chat`: conversations and citation materialization.
- `api`: HTTP contracts and authorization.
- `worker`: asynchronous execution and retries.
- `mcp_server`: tools for ChatGPT/Codex.

## Pipeline

```text
resolve_source
  → acquire_media
  → normalize_audio
  → transcribe
  → index
  → summarize
  → finalize
```

Every step has a state, attempts, timestamps, error, and metrics. A step is
skipped when a compatible artifact already exists. Where applicable,
compatibility considers the transcript, version, and embedding model.

Every execution acquires a PostgreSQL advisory lock derived from the job ID and
keeps the same connection throughout the pipeline. Duplicate Celery deliveries
return without calling providers. Because the lock belongs to the connection,
PostgreSQL releases it when a worker exits or loses the connection, allowing
redelivery; completed steps remain skipped. SQLite uses a per-process lock only
for tests and local development.

## Immutable and derived artifacts

- Original: object received or downloaded from an authorized source.
- Processing: PCM WAV, mono, 16 kHz by default.
- Playback: M4A/AAC for the player.
- Transcript: a version of the text and timed segments.
- KnowledgeChunk: text, segment IDs, speakers, and vector.
- Summary: structured document tied to a transcript version.
- Message: answer, retrieved context, and materialized citations.

## Retrieval

A query combines:

1. the question embedding;
2. cosine distance in pgvector;
3. PostgreSQL `websearch_to_tsquery` and `ts_rank_cd`;
4. score normalization;
5. configurable weights;
6. a mandatory workspace filter and optional episode filter.

The vector column accepts different dimensions by model. Vector retrieval must
filter by the active model so it never compares incompatible dimensions.
Dimensions above pgvector's approximate-index limit use exact search; lexical
search remains indexed by GIN.

Literal speech displayed in a citation comes from `transcript_segments`. The LLM
only selects allowed IDs; it does not write the final citation.

## Library refresh

The frontend requests the library immediately when the page opens. New requests
are scheduled every five seconds only while episodes are `queued` or
`processing`. Scheduling is recursive and begins after the previous request
finishes, preventing overlap and stale responses.

Polling pauses and cancels the current request when the tab becomes hidden, then
resumes immediately on the visibility event. Failures apply exponential backoff
from ten to sixty seconds. When every item reaches a terminal state, no new
request occurs until an explicit refresh or a new page mount.

## Large transcripts

`GET /v1/episodes/{id}/transcript` returns up to 100 segments by default and
accepts at most 200. The opaque cursor is bound to transcript version, last
ordinal, and normalized query, preserving a stable order. `q` runs server-side
search, and `at_ms` returns a page containing the segment for that timestamp.
Full text remains available for processing and exports but is not repeated in
interface pages.

The frontend loads more pages on demand and virtualizes loaded segments with
dynamic height measurement and overscan. Editing a speaker replaces only that
object in already loaded segments; future pages read the updated value from the
server.

Targets for the reference transcript:

- a page response with at most 200 segments and 256 KiB;
- fewer than 30 segment rows mounted in a 760 px viewport;
- first render and search response within 500 ms in the reference local
  environment;
- no loss of order or precision when opening a page by timestamp.

## Production evolution

Celery can be replaced by Temporal at the orchestration boundary without
changing the domain model. A separate vector database should be introduced only
after metrics demonstrate a real PostgreSQL limit. Local WhisperX/pyannote
processing can be added as new adapters for the same ports.
