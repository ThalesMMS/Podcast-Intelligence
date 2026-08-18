# Deployment and operations

Podcast Intelligence supports a native single-user desktop profile and a
networked server profile. Choose one deliberately; they have different security,
scaling, and backup boundaries.

## Desktop deployment

### Intended use

Desktop mode is for a trusted user on one Mac or Windows PC. It requires no
locally installed database, message broker, object store, Python, or Docker after
packaging.

The Tauri host starts its API on a random loopback port; MCP prefers port 8001 and falls back when occupied. Do not configure a
firewall exception or expose those ports to another host. The REST API is
protected by a per-launch token and media routes by short-lived HMAC URLs, but
this is local-process isolation, not multi-user authentication.

### Installation

Distribute the signed/notarized platform bundle produced by the native build
matrix. Do not distribute a source ZIP as though it were an installer. Windows
and each macOS architecture require their own tested output.

### Updates

The current project does not enable an automatic updater. A release should:

1. keep the Tauri identifier unchanged;
2. preserve the operating system application-data directory;
3. create a backup before any future destructive schema migration;
4. test upgrade from the previous released version;
5. replace application binaries without deleting user data.

SQLite tables are currently created idempotently from SQLAlchemy metadata.
Before changing existing columns or constraints, add a versioned desktop
migration mechanism rather than relying on `create_all`.

### Backup and restore

Close the app and copy the complete app data directory. Required components are:

- `podcast-intelligence.sqlite3`;
- `objects/`;
- `settings.json` when provider configuration must be retained;
- `engine-secret` when preserving already issued local-token semantics matters
  (tokens are short-lived, so this is usually relevant only as part of a full
  consistent copy).

Restore all files to the same Tauri-resolved app-data location before launch.
A database without matching objects can reference missing audio; objects without
the database are not indexed or visible.

### Privacy and retention

Audio, transcripts, embeddings, summaries, questions, and provider credentials
remain on disk until manually removed. The interface does not yet implement a
complete deletion/retention workflow. Provider-backed operations transmit the
necessary content to the configured external service; review that provider's
terms and data controls.

### Logs and support

The engine writes operational output to the Tauri process stderr in current
builds. Avoid collecting logs that include private URLs, transcript text, or
credentials. A future production release should add bounded rotating logs with
explicit redaction and a user-controlled diagnostics export.

## Server deployment

The Compose file is suitable for local development, not high availability.
Before network deployment:

1. set `APP_ENV=production`;
2. replace every development secret;
3. configure `AUTH_MODE=oidc` with issuer, audience, and JWKS URL;
4. terminate TLS at a trusted reverse proxy;
5. keep PostgreSQL, Redis, and MinIO on private networks;
6. use managed backups and encryption at rest;
7. restrict CORS to the real frontend origin;
8. configure retention, deletion, and audit policies;
9. scan dependencies and container images;
10. perform threat modeling and penetration testing.

### Database

Use managed PostgreSQL with the `vector` extension. Run Alembic migrations as a
separate release step. Do not let every horizontally scaled API replica race to
migrate the schema.

Back up PostgreSQL and S3/MinIO as one logical dataset. Redis is a queue/cache;
its loss should not delete completed artifacts, but jobs should be reconciled
from the durable dispatch outbox.

### Worker scaling

API and MCP are stateless apart from database/object-store access. Celery
workers can scale independently. PostgreSQL advisory locks and idempotent steps
make duplicate delivery safe, but provider rate limits and cost controls still
need deployment-specific concurrency settings.

### Object storage

Use private buckets, least-privilege credentials, TLS, lifecycle policies, and
server-side encryption. Presigned URLs must remain short-lived. `S3_PUBLIC_ENDPOINT_URL`
must be reachable by the intended browser without exposing an administrative
console.

### MCP

The included MCP server assumes one configured workspace. A public deployment
requires per-user OAuth, workspace authorization on every tool, HTTPS, and
provider/data isolation. Do not publish the local development MCP endpoint as a
multi-user service.

## Health checks

Desktop readiness reports:

```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "object_store": "ok",
    "job_runner": "local"
  }
}
```

Server readiness additionally checks Redis. Object-store and database failures
must fail readiness so the process is removed from service.

## Disaster-recovery testing

A backup is not complete until a restore test verifies:

- episode list and metadata;
- playback of stored media;
- transcript pagination;
- summary retrieval;
- grounded chat/search against matching embeddings;
- queued-job recovery;
- provider settings loaded without exposing credentials in logs.
