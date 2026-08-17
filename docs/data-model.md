# Data model

## Identity and isolation

- `workspaces`: data-isolation boundary.
- `users`: normalized external identity.
- `memberships`: user association and role in a workspace.

Every episode, conversation, and chunk query must carry or validate
`workspace_id`. Development mode uses fixed IDs; OIDC mode requires a JWT and an
existing membership.

## Catalog and media

- `shows`: show and canonical feed.
- `episodes`: the product's primary unit.
- `episode_sources`: supplied source and resolution result.
- `media_assets`: original, processing, playback, or published transcript.

`episode_sources.resolved_media_url` records provenance but should not be
exposed unnecessarily. Private URLs and tokens must not appear in logs.

## Processing

- `processing_jobs`: global state, progress, and options.
- `processing_steps`: idempotent state for each step.
- `provider_runs`: provider, model, request ID, latency, units, and cost.

Cost fields exist, but the scaffold does not calculate prices; that function
should be implemented with a versioned table per provider.

## Knowledge

- `transcripts`: transcript versions.
- `speakers`: voice clusters and name attributions.
- `transcript_segments`: text, speaker, and millisecond range.
- `knowledge_chunks`: semantic groups with segment IDs and a vector.
- `summaries`: versioned structured outputs.

The initial vector dimension is 1536. Changing to a model with another dimension
requires a new migration and reindexing.

## Conversations

- `conversations`: scope of a chat session.
- `messages`: content, exact citations, and retrieval snapshot.

Conversation memory is not documentary evidence. The service sends history as
auxiliary context and keeps the retrieved transcript in a separate block.
