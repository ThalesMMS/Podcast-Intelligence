# MCP, ChatGPT, and Codex

## Tools

The MCP server reuses the product database and domain services; it does not
maintain a second transcript index.

- `search`: hybrid knowledge search;
- `fetch`: retrieve an episode, chunk, or segment;
- `list_episodes`: list the current workspace;
- `ask_episode`: grounded answer without persisting a UI conversation;
- `create_summary`: idempotent summary creation/regeneration.

## Desktop endpoint

The desktop engine attempts to bind MCP to:

```text
http://127.0.0.1:8001/mcp
```

If port 8001 is occupied, it selects an available loopback port instead. Open
**Settings → Local runtime** and copy the exact current endpoint. The endpoint
changes only when a fallback port is required or the engine is restarted with a
different runtime allocation.

Register it in Codex:

```bash
codex mcp add podcast-intelligence --url http://127.0.0.1:8001/mcp
codex mcp list
```

When the settings screen reports another port, use that URL. The desktop MCP
process shares SQLite and local media metadata with the application.

This endpoint is unauthenticated and loopback-only. Use it only on a trusted,
single-user computer. A different local process running as the same user can
attempt to call it.

## Server endpoint

Docker/server mode uses:

```text
http://localhost:8001/mcp
```

For a remote deployment with OAuth:

```bash
codex mcp add podcast-intelligence --url https://podcasts.example.com/mcp
codex mcp login podcast-intelligence
```

Before publishing, implement OAuth 2.1/protected-resource discovery and derive
the workspace from the authenticated identity in every tool.

## ChatGPT Developer Mode

A loopback-only endpoint is not directly reachable by ChatGPT's hosted
connector environment. For controlled development, expose MCP through an HTTPS
tunnel and register the public URL ending in `/mcp` under the applicable Apps &
Connectors developer settings. Do not tunnel a private podcast library without
authentication and explicit authorization.

## Codex as the language-model provider

The desktop settings dialog can select `codex_cli` for the LLM port. Requirements:

1. install the Codex CLI on the same machine;
2. run `codex login` as the desktop user;
3. enter `codex` or the absolute executable path in Settings;
4. optionally select a model override;
5. save and restart the engine.

The adapter runs `codex exec` in a read-only sandbox and a dedicated app-data
working directory, supplies a JSON Schema, and validates the structured result.
It is intended only for a trusted local host. It must not receive browser
cookies or be exposed as a SaaS worker.

In server development, the equivalent environment is:

```bash
cd backend
LLM_PROVIDER=codex_cli uv run celery \
  -A podcast_intelligence.worker.celery_app:celery_app worker --loglevel=INFO
```

Compose deliberately does not mount Codex authentication credentials.
