# ADR 0002 — Timed segments as the unit of evidence

**Status:** accepted

## Decision

Summaries and answers store segment IDs. Literal citations are materialized
from the database, never copied from LLM-generated text.

## Consequences

- clickable timestamps and auditability;
- text corrections require transcript versioning;
- the model must receive a closed list of allowed IDs;
- evaluations can measure citation precision separately from writing quality.
