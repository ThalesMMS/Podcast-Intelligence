# Security policy

## Desktop profile

The desktop application is designed for one trusted operating-system user. It
adds several controls around its local HTTP boundary:

- API and MCP bind to `127.0.0.1` on random ports;
- the REST API requires a random per-launch `X-Desktop-Token`;
- uploads and playback use short-lived HMAC-signed URLs;
- local object keys are resolved beneath one storage root and path traversal is
  rejected;
- uploads verify declared MIME type and exact byte count;
- Tauri limits native save/open operations to explicit commands and HTTP(S)
  links;
- the webview CSP permits loopback API/media access and approved remote artwork,
  not arbitrary native filesystem access;
- Unix settings and engine-secret files are written with mode `0600`.

These controls do not protect against malware already running as the same OS
user. The app-data directory contains sensitive audio, transcripts, embeddings,
questions, and summaries.

Provider keys and Spotify secrets are currently stored in `settings.json`.
Unix permissions are restricted; Windows uses inherited user profile ACLs. This
is **not equivalent to macOS Keychain or Windows Credential Manager**. Treat the
file and backups as secrets, or add an OS-keychain integration before deployment
where local credential-at-rest protection is required.

The local MCP endpoint is for a trusted same-computer client and does not
implement public OAuth or multi-user workspace authorization.

## Server profile

Before exposing the service on a public or shared network:

- replace all development secrets and disable `AUTH_MODE=dev`;
- configure an OIDC issuer, audience, and JWKS endpoint;
- terminate TLS at a trusted reverse proxy;
- restrict MinIO/PostgreSQL/Redis to private networks;
- use a managed secret store and encrypted provider credentials;
- review URL ingestion controls against SSRF and DNS-rebinding attacks;
- configure retention, deletion, and audit requirements for audio and voice data;
- run dependency, container, and infrastructure scanning;
- perform an application threat model and penetration test.

## Third-party media tools

Native bundles include separately licensed FFmpeg/FFprobe binaries. Builds copy
source metadata, notices, and applicable GPL text into the application
resources. Verify licensing obligations and exact binary provenance before
redistribution.

## Reporting

Report vulnerabilities privately to the repository owner. Do not include API
keys, private podcast URLs, audio recordings, transcripts, or personal data in
reports.
