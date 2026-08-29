# Architecture

## Request paths

```
Customer (browser)
  └─ Next.js (host) ── Auth.js/Keycloak OIDC+PKCE ──► Keycloak
        │  server-side token proxy (/api/rg/*)
        ▼
     FastAPI backend (Docker)
        ├─ verifies the Keycloak JWT (JWKS), upserts a `users` row
        ├─ shop / orders / returns / dashboard / appeals / analytics / ws
        ├─ submit return  ─►  returns + return_photos + outbox  (one txn)
        │                     + best-effort arq enqueue
        └─ WebSocket /ws/returns/{id}  ◄── Redis pub/sub  rg:events:{id}

Worker (Docker, arq on Redis)
  ├─ dispatch_outbox cron (durability backstop)
  └─ review_return
        └─ LangGraph pipeline (Postgres checkpointer, schema `langgraph`)
             data_quality → planner → intake → policy → [image] → behavior
                → decision → critic → explanation → GovernanceGate
             every node: agent_runs row + agent_run_events (+ Redis publish)
                         + Langfuse generation
             each LLM call ─► Bifrost ─► Groq / OpenAI  (per-agent virtual key)
             tool calls    ─► ContextForge ─► mcp-server ─► Postgres
             GovernanceGate: the only finalizer → returns + hash-chained audit_log
```

## Services

- **postgres** — app DB + separate logical DBs `langfuse` / `bifrost` / `mcpgw`,
  and a `keycloak` schema. `pgvector` is deliberately unused (Qdrant is the
  vector store — ADR-0006).
- **redis** — arq queue, app cache, Langfuse (`/4`) and ContextForge (`/3`)
  logical DBs, the event pub/sub.
- **qdrant** — one collection, `policy_docs`, re-created on every re-embed.
- **minio** — buckets `returnguard` (product images, return photos),
  `returnguard-langfuse-events`.
- **vault** (dev) — every runtime secret under `secret/returnguard/*`;
  per-service policy + AppRole; backend/worker read at boot via `hvac`.
- **keycloak** — realm `returnguard`; `returnguard-web` (confidential, Auth.js),
  `returnguard-cli` (public, scripts), one service-account client per agent.
- **bifrost** — the only path to a model. Fallback chain
  `groq/openai/gpt-oss-120b → openai/gpt-4o-mini` (ADR-0007, ADR-0010).
- **mcp-server** — plain MCP (SDK v2) tools: `get_order`, `check_policy`,
  `get_customer_history`, `flag_ring`. No auth here.
- **mcp-gateway** (ContextForge) — federates mcp-server; 8 per-agent virtual
  servers with tool allow-lists (ADR-0009).
- **langfuse-web / langfuse-worker / clickhouse** — observability (ADR-0004).
- **backend / worker** — `python:3.13-slim` (ADR-0001).

## Data model

Core tables: `users`, `reviewers`, `products`, `orders`, `order_items`,
`returns` (+ `claimed_by/at`, `decided_by/at`, `refund_state`, `review_attempts`),
`return_photos`, `policy_docs` (versioned), `agent_runs` (+ `automation_level`,
`policy_version`, `sa_subject`, tokens/cost/latency, `langfuse_trace_id`),
`agent_run_events`, `audit_log` (append-only, `prev_hash` + `row_hash`),
`outbox`, `dead_letter`, `feature_flags` (per-scope automation level + kill
switch + thresholds), `appeals`, `info_requests`, `agreement_samples`,
`fingerprints`, `model_registry`. Every schema change is an Alembic migration.

## Trust boundaries

1. Browser → Next.js: Auth.js session cookie; tokens never sent to the browser.
2. Next.js → backend: Keycloak access token, verified by JWKS on every request.
3. Backend/worker → Vault: AppRole (dev-token fallback).
4. Agent → tools: Keycloak service-account identity ↔ ContextForge virtual
   server (tool allow-list) ↔ Bifrost virtual key (model + budget).
5. Refunds are a **human-only** action; no MCP tool mutates payment state.
