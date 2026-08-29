# ADR-0004 — Langfuse v3, self-hosted, on shared infrastructure

**Status:** accepted (M1)

## Context
We need full LLM observability (cost / latency / I/O per agent call, trace tree
per pipeline run). Langfuse v2 is EOL. Langfuse v4 existed at build time (Aug
2026) but ships a different self-host topology and a migration path from v3.

## Decision
Run **Langfuse v3** (`langfuse/langfuse:3` + `langfuse/langfuse-worker:3`),
self-hosted. It is still fully supported (not EOL) and its self-host topology is
the one CLAUDE.md specifies. It **reuses the app's infrastructure**:
- Postgres: separate logical DB `langfuse` (same server).
- Redis: separate DB index (`/4`).
- MinIO: separate bucket `returnguard-langfuse-events`.
- ClickHouse: the one component Langfuse v3 adds, memory-capped ~2 GB via
  `infra/clickhouse/low-mem.xml`.

Python SDK pinned to `langfuse==3.0.4` (matches server v3 exactly).

## Consequences
- One Postgres, one Redis, one MinIO to operate — no duplicate datastores.
- ClickHouse is the only extra stateful service for observability.
- If we later move to v4, it's a deliberate migration, not a silent bump.
