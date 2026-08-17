# Known scaffold limitations

- The demo profile does not transcribe real speech.
- Published RSS transcripts are consumed when they use VTT, SRT, or segmented
  JSON; proprietary or untimed formats use the configured STT service.
- Apple/Spotify episode matching uses title heuristics and, when available,
  duration. Ambiguous cases should require human confirmation.
- The local MCP server uses a fixed workspace and is not ready for publication
  without per-user OAuth.
- The manual summary-generation endpoint is synchronous; create a dedicated job
  for high scale.
- There is no transcript text editor, cluster merge/split, or persistent voice
  profile support.
- Provider cost is not calculated automatically.
- Hybrid search combines scores with fixed weights; there is no reranker yet.
- The interface has no deletion/retention workflow.
- Compose is intended for development, not high availability.
- The frontend does not yet implement OIDC login or inject a bearer token; the
  backend's OIDC mode requires a client authentication layer before multi-user
  exposure.
- Direct frontend download/export links must be adapted to attach authorization
  in OIDC mode.
- Cancellation is cooperative between steps; an in-progress external STT/LLM
  call is not aborted immediately.
- There is no global cross-episode hash deduplication.
- The delivered MCP server is tool-only; an Apps SDK widget, CSP, and public
  submission are outside this scaffold.
