# Getting started

This guide starts Podcast Intelligence with the credential-free demo profile.
It also explains where to configure an optional real AI provider without
assuming a particular private network, gateway, or model catalog.

## 1. Requirements

Install:

- Git;
- Docker Engine or Docker Desktop with the Compose v2 plugin;
- Python 3 for the host-side REST smoke script.

On macOS, Colima can provide the Docker engine without Docker Desktop. One
Homebrew setup is:

```bash
brew install docker colima docker-compose docker-buildx
mkdir -p "${HOME}/.docker/cli-plugins"
ln -sfn "$(brew --prefix)/lib/docker/cli-plugins/docker-compose" \
  "${HOME}/.docker/cli-plugins/docker-compose"
ln -sfn "$(brew --prefix)/lib/docker/cli-plugins/docker-buildx" \
  "${HOME}/.docker/cli-plugins/docker-buildx"
colima start --cpu 4 --memory 8 --disk 60
```

Colima keeps this machine configuration for later starts. Use `colima start`
after a restart and `colima stop` when the local Docker engine is not needed.

Confirm that both the daemon and Compose are available:

```bash
git --version
docker version
docker compose version
docker buildx version
```

The application Python runtime, Node.js, FFmpeg, PostgreSQL, Redis, and MinIO
are included in the development containers.

## 2. Clone and configure

```bash
git clone https://github.com/ThalesMMS/Podcast-Intelligence-dev.git
cd Podcast-Intelligence-dev
cp .env.example .env
```

The default `.env.example` uses `AI_PROFILE=demo` and requires no external
credentials. The `.env` file is ignored by Git and must never be committed.

Validate the expanded Compose configuration before building:

```bash
docker compose config --quiet
```

## 3. Start the development stack

```bash
docker compose up -d --build
docker compose ps
```

The API runs database migrations and initializes the local workspace during
startup. Check readiness:

```bash
curl -fsS http://localhost:8000/health/ready
curl -fsS http://localhost:8000/v1/providers
```

The expected readiness response reports `database`, `object_store`, and
`redis` as `ok`.

Local services:

- application: <http://localhost:3000>;
- REST API and OpenAPI: <http://localhost:8000/docs>;
- MCP: <http://localhost:8001/mcp>;
- MinIO console: <http://localhost:9001>.

Compose binds these development ports to `127.0.0.1` by default. To make a
service reachable from another machine, set `HOST_BIND_ADDRESS` deliberately
and first replace the development credentials and authentication mode. Never
bind the default configuration to an untrusted network.

## 4. Create and inspect demo data

Create a complete demo episode:

```bash
docker compose run --rm api python -m podcast_intelligence.cli seed-demo
```

Open <http://localhost:3000>, select the demo episode, and inspect its summary,
transcript, speakers, and grounded chat.

The demo transcript is synthetic and explicitly marked. It validates the
application flow but does not represent speech from an imported audio file.

Run the REST smoke checks:

```bash
./scripts/smoke_test.sh
```

## 5. Import content

The interface accepts:

- a local audio upload;
- a direct media URL;
- an RSS feed or episode URL;
- an Apple Podcasts episode URL;
- a Spotify episode URL when it can be matched to a public RSS enclosure.

Use content you are authorized to process. The project does not bypass DRM,
subscriptions, or access controls.

With the demo profile, importing a real audio file still produces synthetic
text. Configure a real transcription provider before evaluating transcript
accuracy.

## 6. Configure an optional AI provider

The built-in OpenAI profile uses one shared credential:

```dotenv
AI_PROFILE=openai
OPENAI_API_KEY=replace-with-a-secret-from-your-password-manager
```

OpenAI-compatible gateways can use separate credentials and a custom base URL.
The following endpoints use the reserved `example.com` domain and must be
replaced with values from the provider:

```dotenv
AI_PROFILE=custom
TRANSCRIPTION_PROVIDER=streaming_ws
EMBEDDING_PROVIDER=openai
LLM_PROVIDER=openai

OPENAI_BASE_URL=https://ai.example.com/v1
OPENAI_EMBEDDING_API_KEY=replace-with-your-embedding-key
OPENAI_LLM_API_KEY=replace-with-your-llm-key
OPENAI_EMBEDDING_MODEL=replace-with-your-embedding-model
OPENAI_LLM_MODEL=replace-with-your-llm-model

STREAMING_STT_URL=wss://ai.example.com/v1/audio/transcriptions/stream
STREAMING_STT_API_KEY=replace-with-your-transcription-key
STREAMING_STT_MODEL=replace-with-your-transcription-model
```

Provider-specific limits determine whether you must also change embedding
dimensions, batch sizes, transcription chunking, or the LLM API mode. See
[AI providers](docs/providers.md) and the comments in [`.env.example`](.env.example)
before importing long media.

After changing provider configuration, recreate the affected services:

```bash
docker compose up -d --build --force-recreate api worker beat mcp
curl -fsS http://localhost:8000/v1/providers
```

The provider response must match the intended transcription, embedding, and LLM
configuration before processing valuable or long-running content.

## 7. Development checks

The local quality gates require Python 3.12 with
[uv](https://docs.astral.sh/uv/) and a supported Node.js version:

```bash
make check
```

`make check` runs formatting verification, lint, type checks, and both test
suites. Run it before pushing because GitHub-hosted CI is intentionally not
configured for this repository.

The integrated smoke check additionally requires the Compose stack:

```bash
make smoke
```

## 8. Everyday operations

```bash
# Start or rebuild
docker compose up -d --build

# View state
docker compose ps

# Follow application logs
docker compose logs -f --tail=200 api worker

# Stop without deleting persistent data
docker compose down --remove-orphans
```

Do not use `docker compose down -v` when you need to preserve local episodes,
database rows, or stored audio. The `-v` option removes the project volumes.

## 9. Moving to another computer

A Git clone contains code, migrations, and documentation. It does not contain:

- `.env` or provider credentials;
- PostgreSQL data;
- audio stored in MinIO;
- Redis data;
- imported episodes, transcripts, embeddings, or summaries.

For a new installation, configure a new `.env` and import the content again.
To preserve an existing installation, back up and restore PostgreSQL and MinIO
separately.

## 10. Production boundary

The Compose stack is for local development. Before deploying the service on a
public or shared network, follow [Deployment and operations](docs/deployment.md),
[Security](SECURITY.md), and [Known limitations](docs/known-limitations.md).

Additional documentation:

- [README](README.md)
- [Architecture](docs/architecture.md)
- [Data model](docs/data-model.md)
- [MCP and Codex](docs/mcp-and-codex.md)
