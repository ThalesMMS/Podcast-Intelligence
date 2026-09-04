# AI providers

In the native application these values are edited under **Settings** and saved
to the private application-data directory. Saving restarts the packaged engine.
Server mode uses the equivalent environment variables shown below.

## Demo profile

The `demo` profile uses no external key. It provides:

- explicitly marked synthetic transcription that is not derived from real speech;
- deterministic feature-hashing embeddings;
- extractive summaries and answers;
- complete pipeline execution for development and architecture review.

Do not use demo transcription for decisions or acoustic-quality evaluation.

## OpenAI profile

`AI_PROFILE=openai` selects:

- `gpt-4o-transcribe-diarize` by default for speaker-attributed segments;
- `text-embedding-3-small` with dimension 1536;
- Chat Completions with Structured Outputs for summaries and answers.

By default, all three clients use `OPENAI_API_KEY`. Gateways with separate
credentials can set `OPENAI_TRANSCRIPTION_API_KEY`,
`OPENAI_EMBEDDING_API_KEY`, and `OPENAI_LLM_API_KEY`; a specific key takes
precedence over the shared key. `OPENAI_BASE_URL` is the shared URL fallback.
Set `OPENAI_TRANSCRIPTION_BASE_URL`, `OPENAI_EMBEDDING_BASE_URL`, or
`OPENAI_LLM_BASE_URL` when the clients use different HTTP-compatible gateways.

Chat Completions is the compatibility default. Set `OPENAI_LLM_API=responses`
only when the gateway implements Structured Outputs correctly in Responses.
The embedding request omits `dimensions` by default; configure
`EMBEDDING_DIMENSION` with the model's native dimension. Set
`OPENAI_EMBEDDING_SEND_DIMENSIONS=true` only for models that support selecting
an output size. The database accepts dimensions by model, and vector search
filters by the active model; vectors above the HNSW indexing limit use exact
search.

The adapter validates outputs with Pydantic models and restricts cited IDs to
the supplied segments. Audio above the configured limit is converted to MP3,
split into parts with global offsets, and can reuse up to four voice samples
between parts. The application must still run its own WER, DER, retrieval, and
faithfulness evaluations.

## PCM WebSocket STT

`TRANSCRIPTION_PROVIDER=streaming_ws` connects to a service that receives an
initial JSON message, mono 16-bit PCM frames at 16 kHz, and a final `stop`
message. Configure `STREAMING_STT_URL` and `STREAMING_STT_MODEL`; an API key is
optional inside a trusted tailnet. The adapter opens sequential sessions limited by
`STREAMING_STT_BATCH_SECONDS`, preventing inference from exceeding streaming
gateway heartbeats. When the gateway returns timestamped segments, they are
preserved; otherwise each batch becomes one segment with approximate bounds.
The adapter does not claim neural diarization.

## Published RSS transcripts

Before STT, the pipeline attempts to consume Podcast Namespace references in
VTT, SRT, or segmented JSON. Timestamps and speaker names are preserved. Parse
failures or unsupported formats are recorded in metadata and fall back to the
configured transcriber.

## Custom profile

With `AI_PROFILE=custom`, configure providers individually:

```dotenv
TRANSCRIPTION_PROVIDER=streaming_ws
STREAMING_STT_URL=ws://gateway.example/v1/audio/transcriptions/stream
STREAMING_STT_MODEL=whisper-large-v3-turbo
EMBEDDING_PROVIDER=openai
OPENAI_EMBEDDING_BASE_URL=http://gateway.example/v1
LLM_PROVIDER=openai
OPENAI_LLM_BASE_URL=http://gateway.example/v1
```

HTTP-compatible base URLs must use `http://` or `https://`; streaming
transcription must use `ws://` or `wss://`. For compatibility with desktop
settings saved by earlier builds, a WebSocket URL found in
`OPENAI_TRANSCRIPTION_BASE_URL` is migrated at startup to the streaming
transcriber together with its transcription key and model.

## Local Codex CLI

The `codex_cli` adapter is exclusive to a trusted local process. It calls
`codex exec` in a read-only sandbox, supplies JSON Schema, and reads the final
structured result. It must not be enabled in a SaaS worker or receive ChatGPT
sessions/cookies.

## Adding a provider

Implement one of the ports in `domain/ports.py`, register the adapter in
`services/providers.py`, expose capabilities, and add contract tests. The
domain service must not import the new provider's SDK.
