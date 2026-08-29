# ADR-0006 — Qdrant as the vector store, not pgvector

**Status:** accepted (M1)

## Context
The Policy agent does RAG over versioned return-policy documents. We already run
Postgres, so pgvector is the zero-new-service option.

## Decision
Use **Qdrant** (dedicated container). Reasons that actually matter here:
- Policy docs are re-embedded on every `admin` policy edit → we want named
  collections we can snapshot / swap per `policy_docs` version without touching
  the app DB or its migrations.
- Payload filtering (by policy version, category) is first-class in Qdrant and
  keeps "which policy version was in force" queries clean.
- Keeps embedding-index churn off the transactional DB's autovacuum path.

pgvector stays explicitly unused (CLAUDE.md).

## Consequences
- One more container + named volume + healthcheck.
- `scripts/backup.sh` must snapshot Qdrant alongside `pg_dump`.
