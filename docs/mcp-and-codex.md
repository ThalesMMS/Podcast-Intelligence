# MCP, ChatGPT, and Codex

## Selected form

The server is a **tool-only** MCP application. It reuses the product domain and
database; it does not contain a second index or duplicate widget.

Tools:

- `search`: standard reusable search;
- `fetch`: retrieves an episode, chunk, or segment;
- `list_episodes`: lists the library;
- `ask_episode`: grounded answer without persisting a conversation;
- `create_summary`: idempotent write operation.

The local endpoint is `http://localhost:8001/mcp`.

## Codex

After starting the project:

```bash
codex mcp add podcast-intelligence --url http://localhost:8001/mcp
codex mcp list
```

For a remote server with OAuth:

```bash
codex mcp add podcast-intelligence --url https://podcasts.example.com/mcp
codex mcp login podcast-intelligence
```

## ChatGPT Developer Mode

For local testing, expose MCP through an HTTPS tunnel and register the public
URL ending in `/mcp` under **Settings → Apps & Connectors → Advanced settings**.
Refresh the connection after changing tool descriptors.

## Production authentication

The local scaffold uses a fixed workspace in the MCP process. Before publishing:

1. place MCP behind stable HTTPS;
2. implement OAuth 2.1 and protected-resource discovery;
3. derive the workspace from the authenticated identity;
4. validate authorization in every tool;
5. define CSP and app metadata when a widget exists;
6. keep provider credentials out of MCP results.

## Codex as a local LLM

To use the existing Codex authentication as a local engine:

```bash
codex login
cd backend
LLM_PROVIDER=codex_cli uv run celery \
  -A podcast_intelligence.worker.celery_app:celery_app worker --loglevel=INFO
```

This flow must run on the user's trusted host. Compose does not mount the Codex
authentication directory and does not attempt to turn a ChatGPT login into a
generic API key.
