# Validation report

Validation date: August 17, 2026.

## Environment

- Python 3.12.13;
- uv 0.11.32;
- Node.js 22.22.0;
- npm 10.9.4;
- Docker client 29.7.2 and server 29.5.2 on Linux/ARM64;
- Colima 0.10.3 with 4 CPUs, 8 GiB memory, and a 60 GiB disk;
- Docker Compose 5.4.0;
- Docker Buildx 0.36.1 with BuildKit 0.30.0.

Dependencies were synchronized from `backend/uv.lock` with
`uv sync --frozen --extra dev` and from `frontend/package-lock.json` with
`npm ci`.

## Checks completed successfully

### Backend

- Ruff lint: passed.
- Ruff format check: 87 files already formatted.
- mypy strict type check: no issues in 54 source files.
- pytest: 126 tests passed and 2 integration tests skipped.
- pip-audit: no known vulnerabilities in installed third-party packages; the
  local `podcast-intelligence` package was skipped because it is not on PyPI.

The skipped tests require external services:

- S3-compatible endpoint and credentials for playback integration;
- `TEST_POSTGRES_URL` for the PostgreSQL planner integration.

### Frontend

- Prettier format check: passed.
- ESLint: passed.
- Next.js route type generation and TypeScript check: passed.
- Vitest: 21 test files passed, with 102 tests passed.
- Next.js production build: passed.
- `npm audit --audit-level=low`: zero vulnerabilities.

The dependency locks include the first patched releases for the advisories
identified during the public-repository review:

- `brace-expansion` 5.0.9;
- `js-yaml` 4.3.1;
- `nanoid` 3.3.18;
- `cryptography` 50.0.0.

### Repository checks

- `scripts/smoke_test.sh` passed `bash -n`.
- `docker-compose.yml` and `.github/dependabot.yml` parsed as YAML.
- The aggregate local `make check` target covers format checks, lint, typing,
  and both test suites without relying on GitHub-hosted CI.
- The deterministic source archive command passed a dry run.
- GitHub-hosted CI is intentionally not configured. Dependabot remains
  configured for dependency monitoring.

### Docker integration

The local Docker engine was installed and configured with Colima. These checks
completed successfully:

- `docker compose config --quiet`;
- Buildx builds for the API, worker, beat, MCP, and frontend images;
- `docker compose up -d --wait --wait-timeout 240`;
- migrations and health checks for PostgreSQL, Redis, MinIO, and API;
- running-state checks for worker, beat, MCP, and frontend, plus successful
  completion of the one-shot MinIO initializer;
- inspection of the expanded Compose configuration confirming that every
  published development port binds to `127.0.0.1` by default;
- demo seeding, which returned episode
  `00000000-0000-0000-0000-000000000101`;
- the integrated REST smoke test for liveness, readiness, and provider
  discovery;
- frontend HTTP rendering with the title `Podcast Intelligence`.

The smoke script initially exposed a macOS portability defect because it
assumed the executable name `python`. It now selects `python3` first, falls back
to `python`, and exits with a clear error if neither is available. The corrected
script passed `bash -n` and the integrated smoke test.

The verified local flow is:

```bash
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose run --rm api python -m podcast_intelligence.cli seed-demo
./scripts/smoke_test.sh
docker compose ps
```

Do not use `docker compose down -v` when the local volumes contain data that
must be preserved.

## External-provider checks not run

No real calls were made to OpenAI-compatible APIs, WebSocket transcription
providers, Spotify, Apple Podcasts, or external feeds. Those checks require
user-controlled credentials, provider access, and content authorized for
processing.

MCP testing inside ChatGPT also remains environment-specific because it
requires a reachable HTTPS endpoint and authentication appropriate to the
deployment.

## Scope of this report

This report validates the local code gates and records the remaining
environment-dependent checks. It is not a production-readiness, threat-model,
privacy, or penetration-test certification. Review [Security](SECURITY.md),
[Deployment and operations](docs/deployment.md), and
[Known limitations](docs/known-limitations.md) before deploying the service on
a public or shared network.
