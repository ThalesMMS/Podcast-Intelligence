# ADR 0001 — Modular monolith with independent workers

**Status:** accepted

## Context

The product requires transactions across catalog data, jobs, transcripts,
chunks, and summaries, while media processing must scale independently.

## Decision

Keep one repository and domain model. The API, worker, and MCP server are
separate processes that share Python packages and PostgreSQL.

## Consequences

- lower initial coordination and migration cost;
- local transactions and straightforward traceability;
- workers can scale horizontally;
- module boundaries must be enforced by ports/adapters;
- microservices will be extracted only after operational evidence.
