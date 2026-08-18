# Known limitations

## Desktop

- The delivered source has a complete native build pipeline, but installers must
  still be built and tested on native macOS and Windows runners.
- Bundles are unsigned unless Apple/Windows signing credentials are configured;
  unsigned software can trigger Gatekeeper or SmartScreen warnings.
- Provider and Spotify credentials are stored in a private settings file, not an
  OS keychain.
- SQLite schema creation is idempotent, but versioned desktop migrations are not
  yet implemented for future destructive schema changes.
- Desktop hybrid search scores at most 10,000 candidate chunks per query and has
  no approximate vector index or reranker.
- Desktop lexical ranking is intentionally portable and will not be numerically
  identical to PostgreSQL full-text search.
- Windows ARM64 is not included in the build matrix.
- There is no automatic application updater.
- Engine logs are not yet exposed through a bounded, redacted diagnostics UI.
- A hard process kill during a provider request can leave the external request
  running remotely even though the local job is recovered on restart.

## Product behavior

- The Demo profile does not transcribe real speech.
- Published RSS transcripts are consumed when they use VTT, SRT, or segmented
  JSON; proprietary or untimed formats use the configured STT service.
- Apple/Spotify episode matching uses title heuristics and, when available,
  duration. Ambiguous matches should receive human review.
- The manual summary-generation endpoint is synchronous; high-scale server
  deployments should move it to a dedicated job.
- There is no transcript text editor, cluster merge/split, or persistent voice
  profile support.
- Provider cost is not calculated automatically.
- Hybrid search uses fixed configurable weights and no reranker.
- The interface has no complete deletion, legal-hold, or retention workflow.
- Cancellation is cooperative between steps; an in-progress external STT/LLM
  call is not aborted immediately.
- There is no global cross-episode content-hash deduplication.

## MCP and multi-user deployment

- Desktop MCP uses one fixed local workspace and is not suitable for publication
  without OAuth and per-tool authorization.
- The delivered MCP server is tool-only; an Apps SDK widget and public app
  submission are outside this repository.
- The server frontend does not yet implement OIDC login/token injection; OIDC
  backend mode requires a client authentication layer before multi-user use.

## Server operations

- Compose is intended for development, not high availability.
- Direct browser exports in server OIDC mode require an authenticated client
  download flow; the Tauri path already performs authenticated fetches.
