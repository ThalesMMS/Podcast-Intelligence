# Deployment and operations

## Development

```bash
cp .env.example .env
docker compose up --build
docker compose run --rm api python -m podcast_intelligence.cli seed-demo
```

## Process separation

- API: light CPU usage and low latency.
- Worker: CPU/GPU and long jobs; scale by queue and provider type.
- MCP: low latency, streamable HTTP, and independent authentication.
- Frontend: static/standalone build.
- PostgreSQL, Redis, and S3: managed services in production.

## Mandatory controls before public exposure

- `APP_ENV=production` and `AUTH_MODE=oidc`;
- random secrets and a secret manager;
- TLS and private networking for the database, Redis, and storage;
- restricted CORS;
- private bucket and short-lived presigned URLs;
- retention and cascading deletion;
- size, duration, rate, and concurrency limits;
- auditing of speaker changes and deletions;
- tested backups;
- queue, latency, failure, and cost observability;
- a data policy for voice and protected content.

## Scalability

Worker concurrency should reflect the actual bottleneck. For external APIs, use
per-provider queues and rate limits. For local models, separate GPU workers.
Redis is not the source of truth; jobs and artifacts remain in PostgreSQL/S3.
Each job holds a PostgreSQL connection while it owns its advisory lock, so size
`pool_size + max_overflow` to at least each Celery process's concurrency.
Exhaustion or transient pool unavailability retries the job with backoff without
starting providers before a connection is acquired.

## Durable job dispatch

Creating or retrying a job writes a row to `job_dispatches` in the same
transaction as the `queued` state. Every five seconds, Celery Beat asks a worker
to publish pending rows. The dispatcher uses `FOR UPDATE SKIP LOCKED`, limits
each batch, and applies backoff while the broker is unavailable. After
`DISPATCH_MAX_ATTEMPTS` failures (10 by default), the row receives
`dead_lettered_at` and no longer occupies batches. A manual retry clears that
terminal state and restarts the counter.

Each publish attempt also uses five-second connection and socket timeouts and at
most three short producer retries. A broker partition therefore cannot hold a
single publication indefinitely. The dispatcher selects, publishes, and
confirms one row per short transaction up to the batch limit, checking the
`DISPATCH_RUN_TIME_BUDGET_SECONDS` budget (30 seconds by default) before each
selection. Once exhausted, no unprocessed rows are held; they remain available
to another dispatcher or the next Beat cycle.

A failure after publication but before commit can publish the same job more
than once. This is intentional: the job's advisory lock prevents concurrent
execution, and completed steps remain idempotent. Monitor pending-row count,
`attempts`, `available_at`, `dead_lettered_at`, and `last_error`; a growing
backlog indicates broker unavailability or a missing `beat` service.
Dead-letter rows require investigation and an explicit retry after the cause is
fixed. `last_error` records only the publication exception category, never raw
text that could contain a DSN or broker credentials.

## Migrations

The API runs `alembic upgrade head` in local Compose. In production, run
migrations as a single release job before updating API replicas.

## Observability

- `/health/live`: active process.
- `/health/ready`: PostgreSQL, S3, and Redis.
- `/metrics`: Prometheus HTTP metrics.
- structured JSON logs.
- `provider_runs`: latency and metadata per call.

## Lexical-search benchmark

Before promoting retrieval changes, load at least 100,000 `knowledge_chunks`
distributed across 100 episodes in one workspace and run
`EXPLAIN (ANALYZE, BUFFERS)` after `ANALYZE knowledge_chunks`. The query should:

- filter by workspace and, when supplied, episode;
- use `to_tsvector('simple'::regconfig, text) @@
  websearch_to_tsquery('simple'::regconfig, :query)`;
- show `Bitmap Index Scan` or `Index Scan` on `ix_knowledge_chunks_fts`;
- keep p95 below 150 ms across 20 warmed queries on PostgreSQL 16 with 4 vCPU
  and enough cache for the index.

The opt-in test `backend/tests/test_retrieval_postgres.py` validates correctness
and the GIN plan with 10,000 rows. Set `TEST_POSTGRES_URL` to a disposable test
PostgreSQL database; the test uses only a temporary table.

Distributed OpenTelemetry is the recommended extension for correlating the API,
Celery, providers, and storage.
