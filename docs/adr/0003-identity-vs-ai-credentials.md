# ADR 0003 — Separate user identity from AI credentials

**Status:** accepted

## Decision

Product login uses a development identity or OIDC. AI calls use backend
credentials, future BYOK, or a local Codex adapter. A ChatGPT session is not
stored or reused by the shared backend.

## Consequences

- clear isolation and billing;
- MCP/OAuth is the primary ChatGPT/Codex integration;
- authenticated Codex CLI is supported only on a trusted local host;
- BYOK requires a vault, rotation, and auditing before implementation.
