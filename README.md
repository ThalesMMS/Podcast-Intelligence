# Podcast Intelligence

A modular platform for importing podcasts or audio files, normalizing media,
transcribing with optional diarization, creating time-aware summaries, indexing
semantic chunks, and answering questions with clickable citations.

## Stack

- **Frontend:** Next.js 16, React 19, and TypeScript.
- **API:** Python 3.12, FastAPI, Pydantic, and SQLAlchemy.
- **Processing:** Celery, Redis, and FFmpeg.
- **Data:** PostgreSQL 17 with pgvector and S3/MinIO storage.
- **AI:** independent ports with demo, OpenAI, and local Codex CLI adapters.
- **ChatGPT/Codex:** streamable HTTP MCP server.
- **Architecture:** modular monolith with API, worker, and MCP in separate processes.

## Implemented flows

1. Direct upload through a presigned URL, media URL, RSS, Apple Podcasts, or
   Spotify.
2. Catalog-link resolution to a public RSS enclosure when available.
3. Remote download with scheme, DNS, IP, redirect, MIME, and size validation.
4. Preservation of the original, a processing WAV, and an M4A for playback.
5. Reuse of published VTT/SRT/JSON transcripts or provider-based diarized transcription.
6. Human speaker renaming and confirmation.
7. Speaker-aware chunking and pgvector embeddings.
8. Hybrid lexical/vector retrieval by workspace and episode.
9. Hierarchical structured JSON summaries linked to segment IDs.
10. Grounded chat; literal citations come from the database, not the LLM.
11. JSON, Markdown, SRT, and VTT exports.
12. MCP tools: `search`, `fetch`, `list_episodes`, `ask_episode`, and
    `create_summary`.

## Quick start

Requirement: Docker with Compose v2.

```bash
cp .env.example .env
docker compose up --build
```

Services:

- Web: `http://localhost:3000`
- REST/OpenAPI: `http://localhost:8000/docs`
- MCP: `http://localhost:8001/mcp`
- MinIO: `http://localhost:9001`

Create a complete demo episode:

```bash
docker compose run --rm api python -m podcast_intelligence.cli seed-demo
```

The seed includes a transcript, speakers, chunks, embeddings, a summary, and a
completed job. It does not include an audio file.

## Interface languages

The interface supports `en-US` and `pt-BR`. On first use, a browser language
starting with `pt` selects `pt-BR`; every other browser language selects
`en-US`. The toggle persists the selection in local storage under
`podcast-intelligence.locale` and updates the document's `lang` attribute.

Interface locale is independent from the transcription-language option. Changing
the toggle never changes the language sent to transcription or translates
episode content, transcripts, summaries, questions, answers, or citations.

## Demo profile

The default `AI_PROFILE=demo` requires no key. It exercises storage, the
pipeline, indexing, summaries, search, and chat. For a real file, the demo
transcript is **synthetic and explicitly marked**; it does not represent the
audio's speech.

## OpenAI profile

In `.env`:

```dotenv
AI_PROFILE=openai
OPENAI_API_KEY=...
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-transcribe-diarize
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_LLM_MODEL=gpt-5.6-luna
```

OpenAI-compatible gateways that issue separate credentials can also use
`OPENAI_TRANSCRIPTION_API_KEY`, `OPENAI_EMBEDDING_API_KEY`, and
`OPENAI_LLM_API_KEY`. Each provider-specific key takes precedence over
`OPENAI_API_KEY`; `OPENAI_BASE_URL` remains shared by all three clients.

Gateways that offer Structured Outputs only through Chat Completions can use
`OPENAI_LLM_API=chat_completions`. Fixed-dimension embedding models should set
`OPENAI_EMBEDDING_SEND_DIMENSIONS=false` and declare their actual dimension in
`EMBEDDING_DIMENSION`. Adjust `EMBEDDING_BATCH_SIZE` when the gateway limits the
number of inputs per request.

For PCM WebSocket STT, use the `custom` profile, select
`TRANSCRIPTION_PROVIDER=streaming_ws`, and configure `STREAMING_STT_URL`,
`STREAMING_STT_API_KEY`, and `STREAMING_STT_MODEL`. Long sessions are divided
into batches of `STREAMING_STT_BATCH_SECONDS` to tolerate gateways with short
heartbeats. This protocol produces a real transcript but does not invent
diarization or internal timestamps that the server does not provide.

The adapter uses diarized transcription with automatic splitting for long
audio, 1536-dimensional embeddings, and the Responses API with Pydantic-validated
structured outputs.

## Local Codex CLI and MCP

`LLM_PROVIDER=codex_cli` uses `codex exec` only on a trusted local host after
`codex login`. Compose does not mount Codex credentials. To use the product from
Codex:

```bash
codex mcp add podcast-intelligence --url http://localhost:8001/mcp
```

Read [`docs/mcp-and-codex.md`](docs/mcp-and-codex.md) for ChatGPT Developer
Mode, production OAuth, and security boundaries.

## Development without Docker

Backend:

```bash
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run python -m podcast_intelligence.cli bootstrap
uv run uvicorn podcast_intelligence.main:app --reload
```

Worker:

```bash
cd backend
uv run celery -A podcast_intelligence.worker.celery_app:celery_app worker --loglevel=INFO
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The optional local diarization/ASR stack is listed in
`backend/requirements-local-speech.txt` and should be installed for the
environment's CUDA/CPU configuration.

## Validation

```bash
make lint
make test
make smoke
```

## Documentation

- [Personal getting-started guide](GETTING_STARTED.md)
- [Architecture](docs/architecture.md)
- [Data model](docs/data-model.md)
- [API](docs/api.md)
- [Providers](docs/providers.md)
- [MCP and Codex](docs/mcp-and-codex.md)
- [Deployment](docs/deployment.md)
- [Known limitations](docs/known-limitations.md)
- [Security](SECURITY.md)
- [Validation report](VALIDATION.md)

## License

MIT. Users are responsible for having authorization to process supplied
content. The code does not attempt to bypass DRM, subscriptions, or access
controls.
