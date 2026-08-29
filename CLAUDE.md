# ReturnGuard — project context for Claude Code

## What this is

ReturnGuard is a small e-commerce app (shop + checkout + order history) wired to a
**governed multi-agent AI system** that reviews every return/refund request, auto-clears
the obviously legitimate ones, and routes anything risky, unclear, or high-value to a
human reviewer through a real fraud-review dashboard.

It's a portfolio project built to demonstrate Forward Deployed Engineer (FDE) work: one
company, one real operational process (return/refund review), replaced with a properly
governed agent system — not a chatbot demo. The emphasis is on the hard parts of FDE
work: **governed autonomy, full observability, per-agent identity, scenario-driven
validation of real behaviour, a business case, and a clean handoff** — not just "an
agent that answers".

This project is **local-only**. It is never deployed anywhere. There is no CI/CD and no
requirement to push to a remote — everything runs on the developer's own machine via
Docker Compose. The only paid dependencies are the Groq and OpenAI API calls themselves.

## Non-negotiables — read this before writing any code

1. **Nothing is mocked, stubbed, faked, or hardcoded, ever, at any point.** Every agent
   call is a real API call routed through the Bifrost gateway to Groq or OpenAI. Every
   DB write is a real write to Postgres. Every "AI decision" comes from an actual model
   response, not an if/else pretending to be one. Every uploaded file is really stored
   to MinIO. If a feature can't be built for real yet, it does not exist yet — it is
   never faked as a placeholder that returns a canned response. No `TODO: mock this
   later`, no `return {"status": "approved"} # fake for now`, no lorem-ipsum data
   standing in for real generated content.
2. Every action a person takes in the dashboard (approve / deny / request info / claim /
   appeal / edit policy / change automation level) must actually write to the database
   and actually show up in the append-only audit log — not just update the UI locally.
3. Every agent decision is traceable: which agent, which model, what input (hashed),
   what output, what confidence, what prompt version, which policy version, tokens,
   cost, latency — logged to Langfuse **and** to the Postgres `agent_runs` table.
4. **Auto-deny never ships without a human confirming.** Auto-approve is fine, but only
   for low-risk, high-confidence cases and only when the current `automation_level`
   permits it. The pipeline starts life in `shadow` mode (agent decides, human still
   acts) and is only moved up the autonomy ladder deliberately.
5. Nothing runs on a paid cloud service and nothing is deployed anywhere. Everything
   runs locally via Docker Compose. This explicitly rules out hosted inference for the
   local models (CLIP, the AI-image detector, the scikit-learn model) — they run on the
   local CPU. The only paid dependencies are the Groq and OpenAI API calls.
6. Secrets (`OPENAI_API_KEY`, `GROQ_API_KEY`, generated DB/MinIO/Keycloak creds) live in
   **HashiCorp Vault** (dev-mode container, KV v2, one policy + AppRole per service).
   `pydantic-settings` reads Vault at boot. `.env` exists only to bootstrap Vault
   itself and is git-ignored; `.env.example` documents the required keys with empty
   values. Secrets are never hardcoded, never committed, never logged.
7. Use the latest stable release of every dependency at the point you actually scaffold
   it — check `pip index versions <pkg>`, `npm view <pkg> version`, or the tool's own
   site rather than trusting a version number from memory. The stack table below records
   versions verified in Aug 2026; re-verify at scaffold time and bump if newer stable
   exists.
8. If you hit a step you can't complete for real — missing credential, ambiguous
   requirement, a library that doesn't do what's assumed — **stop and ask.** Don't paper
   over it with a fake implementation. The "known unknowns" section of INSTRUCTIONS.md
   lists the few things expected to need a decision mid-build.
9. Write `README.md` yourself, once you have something real to document. Never write a
   setup instruction for a command you haven't actually run, and never describe a demo
   scenario you haven't actually walked through and confirmed. See INSTRUCTIONS.md's
   Milestone 6 for exactly what it needs to contain.
10. **No pytest, no Playwright, no eval-metric harness.** Verification is done by running
    the real app and reading real output — plain `scripts/verify_mN.py` scripts that
    drive the live system over HTTP/WS and assert against real DB/MinIO/Langfuse state,
    plus the **scenario catalog** in `docs/SCENARIOS.md` (see below): every scenario is
    run for real and confirmed to behave exactly as documented. Non-trivial logic still
    leaves one runnable check behind (a `__main__` self-check or its `verify_*` /
    scenario coverage).

## Machine / environment (verified on the target host)

| Component | Actual | What it means for the build |
|---|---|---|
| OS | Windows 11 Home, build 26200 | `wmic` is removed — use PowerShell / CIM for any host inspection. Shell is PowerShell (primary) + Bash tool for POSIX scripts. |
| CPU | AMD Ryzen 5 7235HS — 4 cores / 8 threads, ~3.2–4.2 GHz | CLIP ViT-B/32 CPU inference ≈ 150–250 ms/image. Returns are human-paced (one at a time) so this is fine. `scripts/run_scenarios.py` runs scenarios at concurrency 3–4. |
| RAM | ~24 GB total; **WSL2 already allocated 20 GB** (`~/.wslconfig`: `memory=20GB`, `processors=8`) | Full stack peaks ~8–9 GB. Comfortable including the observability profile. No aggressive trimming needed. |
| GPU | NVIDIA RTX 3050 6 GB Laptop (CUDA-capable) | Not required. `docker-compose.gpu.yml` is an optional override to move CLIP/detector onto CUDA if image checks ever feel slow. Default = CPU. |
| Docker | Docker Desktop + WSL2 backend, installed | May be stopped — `make up` runs `scripts/preflight.sh` first and tells the user to start Docker Desktop. |
| Node | v24.13.0 on host | Frontend runs on the host (not in Docker). |
| Python (host) | 3.14.2 default; 3.12 + 3.11 present; **no 3.13** | Backend + worker run **in Docker on `python:3.13-slim`** so host Python is irrelevant. The thin `scripts/verify_*.py` / `scripts/run_scenarios.py` need only `httpx` + `psycopg` + `qdrant-client` and run on host 3.14 (or via `docker compose run`). |

## Tech stack (versions verified Aug 2026 — re-check at scaffold time)

| Layer | Tool | Notes |
|---|---|---|
| Frontend | Next.js 16.3.x (App Router) + TypeScript strict + Tailwind + shadcn/ui | Shop + dashboard, one app, role-gated routes. Auth.js with the Keycloak OIDC provider (Auth Code + PKCE). Runs on the host. |
| Backend | FastAPI 0.141.x (Python 3.13-slim, in Docker) + Uvicorn | REST API + WebSocket for the live agent trace. SQLAlchemy 2.x async + Alembic migrations + `pydantic-settings`. |
| Worker | `arq` (latest) on Redis, Python 3.13-slim in Docker | Async processing of the return-review pipeline. |
| Database | PostgreSQL 18 (Docker) | App schema below. Also hosts separate logical DBs for Langfuse, Bifrost, and ContextForge. `pgvector` is **not** used — Qdrant is the vector store. |
| Queue / cache | Redis 7 (Docker) | `arq` queue + app cache + Langfuse/ContextForge logical DBs. |
| Agent orchestration | LangGraph 1.2.x (open-source library, **not** the paid cloud platform) + Postgres checkpointer | State graph — Planner branches to whichever agents a case needs. Runs are resumable and inspectable. |
| LLM gateway | **Bifrost** (`maximhq/bifrost`, Apache-2.0 core, Go, Docker) | All model traffic. One OpenAI-compatible endpoint for Groq + OpenAI; automatic fallback chains, load balancing, retries, semantic cache, per-virtual-key budgets + rate limits + model-access scoping, Prometheus + OpenTelemetry + its own dashboard. Replaces any hand-rolled retry/fallback/circuit-breaker code. (Bifrost's per-key *MCP* tool filtering + immutable audit are Enterprise-only — not used; MCP governance is ContextForge's job.) |
| Fast LLM calls (via Bifrost) | Groq — `llama-3.3-70b-versatile` (policy/behavior), `llama-3.1-8b-instant` (intake); Bifrost fallback chain → `openai/gpt-oss-120b` → `gpt-4o-mini` | Intake, Policy, Behavior agents — high volume, speed over depth. Model ids are config-driven. |
| Deep-reasoning LLM calls (via Bifrost) | OpenAI — `gpt-4o-mini` default, `gpt-4o` for borderline vision | Decision, Critic, Explanation agents; borderline vision checks. |
| Embeddings (via Bifrost) | OpenAI `text-embedding-3-small` | Policy-doc + query embeddings for the Policy agent's RAG. |
| Local vision | `open-clip-torch` 3.3.0, ViT-B/32, CPU, lazy-loaded in the worker | Fast first-pass photo-similarity check, zero API cost, ~0 RAM until the first image check. |
| AI-image detection | Open-source detector — a **one-time** bake-off of 2–3 on a small labeled sample (`ml/detector_bakeoff/`), keep the best performer, record numbers + choice in `docs/decisions/ADR-0002`. Candidates: `Organika/sdxl-detector`, `umm-maybe/AI-image-detector`, a CvT-13 detector. | Flags AI-generated "damage" photos. One signal into escalation — never a lone auto-deny. |
| Local ML | scikit-learn (latest) — gradient-boosted classifier + isotonic calibration | Numeric risk-scoring model on tabular features. |
| Vector DB | Qdrant (latest, Docker) | Return-policy documents for the Policy agent. |
| Observability | **Langfuse v3** self-hosted (v2 is EOL), Docker | `langfuse-web` + `langfuse-worker` + ClickHouse (capped ~2 GB); **reuses the app's Postgres / Redis / MinIO** (separate DB / logical DB / bucket). Traces every agent call — cost, latency, I/O. Powers the agent-health dashboard and the scenario runs. Bifrost feeds LLM spans, ContextForge feeds tool-call spans, both via OTel. |
| Metrics | Prometheus + Grafana (Docker, `observability` compose profile) | `/metrics` on backend + worker; Grafana datasource + dashboards provisioned as code. |
| Identity/auth | Keycloak 26.7.x (Docker, JVM heap capped 512 MB) | `customer` / `reviewer` / `admin` realm roles, plus one distinct scoped **service account per agent**. |
| MCP gateway | **IBM ContextForge MCP Gateway** (Apache-2.0, Python/FastAPI, Docker) | Single governed `/mcp` endpoint in front of the tools backend. Validates each agent's Keycloak service-account JWT, exposes a per-agent **virtual server** listing only that agent's allowed tools, rejects out-of-scope `call_tool`, audits every `list_tools` / `call_tool`. Per-virtual-server tool scoping is OSS-core. |
| MCP tools backend | Custom server, MCP Python SDK v2.0.0 (`mcp>=2,<3`) | Exposes `get_order`, `check_policy`, `get_customer_history`, `flag_ring` as real MCP tools. Plain tools server — auth/authz lives in the gateway. |
| Object storage | MinIO (S3-compatible, Docker) | Return photos (app bucket) + Langfuse blobs (separate bucket). No discarded uploads. |
| Email | MailHog (Docker) | Local SMTP catcher — order/return/decision emails, reviewer escalation emails. Fully local. |
| Secrets | HashiCorp Vault (Docker, dev mode) | KV v2, one policy + AppRole per service, secrets fetched at boot. |
| Local infra | Docker Compose | `make up` = full stack; `make up-lite` = skip the observability profile. Every stateful service has a named volume and a healthcheck. |

## Repository layout

```
returnguard/
  docker-compose.yml               # full stack
  docker-compose.gpu.yml           # optional override: CLIP/detector on CUDA
  docker-compose.override.yml      # local dev tweaks (bind mounts, reload)
  # compose profiles: observability (prometheus, grafana), load (loadtest)
  .env.example  .env (gitignored)
  Makefile                         # up, up-lite, down, seed, migrate, scenarios, demo,
                                   # smoke, logs, backup, restore, vault-init, train,
                                   # dataset, loadtest, help
  infra/
    postgres/init.sql              # roles, extensions, extra DBs (app, langfuse, bifrost, mcpgw)
    keycloak/realm-export.json     # realm, roles, clients, one service account per agent
    vault/bootstrap.sh             # KV v2, per-service policies + AppRoles, load keys
    qdrant/                        # collection config
    grafana/provisioning/          # datasources + dashboards as code
    prometheus/prometheus.yml  prometheus/alerts.yml
    clickhouse/                    # memory-capped config for Langfuse
    bifrost/config.json            # providers (Groq/OpenAI), fallback chains, one virtual
                                   # key per agent + per service, budgets, rate limits
    mcp-gateway/                   # ContextForge: per-agent virtual servers, tool->scope, JWKS
  backend/                         # FastAPI app — Docker python:3.13-slim
    app/
      main.py  settings.py  db.py  telemetry.py  logging.py  security/
      routers/ (shop, orders, returns, dashboard, appeals, admin, ws, health, metrics)
      models/  schemas/  services/
    alembic/ (versions/)
    Dockerfile  pyproject.toml
  worker/                          # arq worker + LangGraph pipeline — Docker python:3.13-slim
    pipeline/
      graph.py                     # LangGraph state graph
      nodes/ (data_quality, planner, intake, policy, image, behavior,
              decision, critic, explanation, governance)
      governance.py                # GovernanceGate — enforces the non-negotiables
      prompts/                     # versioned .md prompts + registry.py (hash logged per run)
      llm.py                       # thin: OpenAI SDK pointed at Bifrost
      guardrails.py                # JSON-schema validate + repair LLM output
      models_local.py              # lazy-loaded CLIP + AI-image detector
    replay.py                      # deterministic single-node replay
    reprocess.py                   # batch re-run: --since --until --policy-version
    Dockerfile  pyproject.toml
  mcp-server/                      # MCP Python SDK v2 tools backend
  ml/
    generate_dataset.py            # thousands of rows, injected fraud rings + cohorts
    train.py                       # reproducible, seeded; writes model + card + metrics
    registry/                      # versioned model artifacts + MODEL_CARD.md
    detector_bakeoff/              # small one-time labeled AI-vs-real image sample (ADR-0002)
  scenarios/
    fixtures/                      # seeded data + photos each scenario needs
    # the behaviour catalogue itself lives in docs/SCENARIOS.md;
    # scripts/run_scenarios.py drives every automatable entry
  frontend/                        # Next.js 16 — runs on host
    app/ (shop/*, dashboard/*, admin/*, api/auth/*)
    lib/api/ (generated from OpenAPI)  components/ui/ (shadcn)
  seed/  (products.json  seed.py  images/)
  scripts/
    verify_m1.py ... verify_m6.py  verify_audit_chain.py  verify_security.py
    run_scenarios.py  smoke.py  loadtest.py  preflight.sh  backup.sh  restore.sh
  docs/
    ARCHITECTURE.md  GOVERNANCE.md  RUNBOOK.md  SCENARIOS.md  SECURITY.md
    BASELINE.md  OPERATING_MODEL.md  FAIRNESS.md  MODEL_CARD.md
    decisions/ (ADR-0001-python-313-in-docker.md, ADR-0002-ai-image-detector.md,
                ADR-0003-hash-chain-audit.md, ADR-0004-langfuse-v3-shared-infra.md,
                ADR-0005-outbox.md, ADR-0006-qdrant-vs-pgvector.md,
                ADR-0007-llm-gateway-bifrost.md, ADR-0008-graduated-autonomy.md,
                ADR-0009-mcp-gateway-contextforge.md)
  README.md                        # written in Milestone 6 from a real, running system
```

## The agent pipeline (LangGraph)

```
return submitted
  -> Data-quality gate  missing product image / corrupt photo / malformed address
                         -> escalate "insufficient data" (never guess)
  -> Planner       decides which of the steps below actually apply to this case
  -> Intake        validates the request is complete
  -> Policy        checks against return-window / category rules (Qdrant RAG);
                    records the policy_docs version that was in force
  -> Image         CLIP similarity first; borderline cases -> vision LLM;
                    also screens for AI-generated damage photos
  -> Behavior      scikit-learn risk score + LLM read on qualitative pattern +
                    ring-detection check (shared address/device/payment across accounts)
  -> Decision      combines all signals into approve / deny / escalate
  -> Critic        reviews the Decision agent's reasoning, can force escalation
  -> Explanation   plain-English reason, stored for the audit log, the reviewer,
                    and the customer's return-status page / any appeal
  -> GovernanceGate  the ONLY place a decision is finalized. Reads automation_level
                      (+ per-category flags + kill switch). Rules:
                        - auto-deny  => always escalate with proposed=deny
                        - auto-approve => only if risk < tau_risk AND confidence >
                          tau_conf AND no Critic veto AND automation_level allows it
                        - everything else => escalate
                      In assist mode, a random X% of auto-approvals are still sampled
                      into the human queue for QA.
  -> [escalated]    human review via dashboard
  -> [overridden]   logged to audit_log + agreement_samples and surfaced in the
                     dashboard's agent-vs-human agreement trend; if it exposes a
                     behaviour not already covered, a new entry is added to
                     docs/SCENARIOS.md
```

Every node writes a row to `agent_runs` (agent name, Keycloak SA subject, model used,
input hash, prompt-version hash, policy version, raw response, parsed output, confidence,
tokens in/out, USD cost, latency, Langfuse trace id, graph run id) and streams the same
event over the WebSocket that powers the dashboard's live trace.

### Graduated autonomy (`automation_level`)

The pipeline runs at one of four levels, stored in `feature_flags`, read per run,
settable globally and per category by an `admin`:

- **`shadow`** — pipeline runs, decision logged only, humans still do everything. This is
  the default and where every deployment starts. Agreement data accrues from day one.
- **`suggest`** — the agent decision pre-fills the reviewer's screen; humans still act.
- **`assist`** — auto-approve low-risk / high-confidence; everything else to humans; X%
  of auto-approvals sampled into the queue for QA. This is the `CLAUDE.md` target state.
- **`auto`** — as `assist` without the QA sampling.

A global **kill switch** (`admin`) forces every case to human review regardless of level.

## Scenario catalog (how the finished system behaves)

`docs/SCENARIOS.md` is the single source of truth for what ReturnGuard does in every
situation it's meant to handle. It is **not** a metric harness — there is no
accuracy/precision/recall score, no labelled test file, no regression gate. It is a
catalogue of real end-to-end situations, each written as: **seeded setup → exact steps →
expected observable outcome** (the decision, the route taken — auto-approve / escalate /
human-confirm — which agents fired, the resulting `returns` + `audit_log` state, and
what shows in the live trace).

Every scenario is run against the real, running system and confirmed to match its
description. `scripts/run_scenarios.py` drives the automatable ones; the rest are a
runnable manual checklist. The catalogue has three groups:

- **Decision behaviour** — easy-legit / matching photo (auto-approves), mismatched
  photo, AI-faked damage photo, serial returner, fraud ring, high-value-within-policy,
  outside the return window, ambiguous / worn item, incomplete request (data-quality
  gate), prompt-injection in the return reason.
- **Governance controls** — kill switch on, each `automation_level`
  (`shadow`/`suggest`/`assist`/`auto`), an `admin` policy edit + re-embed applied to a
  later case, a reviewer override, an appeal routed to a different reviewer with the COI
  guard, the request-info round trip.
- **Operational** — a case that crashes the pipeline 3× → dead-letter → auto-escalate,
  a Groq error → Bifrost fallback to OpenAI (decision still real), ~20× return volume
  → queue holds, p95 measured.

A subset is marked **[demo]** — those are the ones walked through when showing the
project to an audience (see Milestone 6 in INSTRUCTIONS.md).

## Data model (Alembic migrations, never `create_all`)

Core tables: `users`, `products`, `orders`, `order_items`,
`returns` (+ `claimed_by`, `claimed_at`, `refund_state`),
`return_photos`, `policy_docs` (versioned),
`agent_runs` (+ `automation_level`, `policy_version`), `agent_run_events`,
`audit_log` (append-only, hash-chained), `outbox`, `dead_letter`,
`feature_flags` (automation level + kill switch, per-category), `appeals`,
`reviewers`, `fingerprints` (address/device/payment), `model_registry`,
`info_requests` (reviewer↔customer round trip), `agreement_samples` (agent-vs-human).

All tables get FKs, CHECK constraints, enums, sensible indexes, and
`created_at` / `updated_at` triggers.

**Hash-chained audit log:** each `audit_log` row stores `prev_hash` + `row_hash`
(SHA-256 over a canonical serialization of the row). `scripts/verify_audit_chain.py`
re-walks the chain and fails on any tamper. This is the immutable governance record.

**Outbox pattern:** a submitted return writes an `outbox` row in the same transaction as
the `returns` row; a dispatcher enqueues it to Redis. No review job is ever lost.

**Dead-letter:** a case that crashes the pipeline 3× goes to `dead_letter` → auto-
escalate + alert. Never an infinite retry.

## Governance model — how the non-negotiables are enforced in code

| Non-negotiable | Enforcement point |
|---|---|
| No faking | `scripts/verify_*` and `scripts/run_scenarios.py` compare live API/UI output to real DB rows and real traces; the final pass greps the codebase. |
| Human action → DB + audit | Every dashboard mutation goes through a service that writes `returns` + an `audit_log` row in one transaction; UI refetches, never patches local state. |
| Every decision traceable | Each graph node writes `agent_runs` + streams `agent_run_events`; Bifrost + ContextForge emit OTel spans to Langfuse. |
| Auto-deny needs a human | `GovernanceGate` cannot emit a final `deny` — only `escalate(proposed=deny)`. The reviewer's confirm step is the only path to a denied `returns` row. |
| Auto-approve is bounded | `GovernanceGate` checks `risk < tau_risk`, `confidence > tau_conf`, no Critic veto, and `automation_level`. Thresholds live in `feature_flags`, tuned by an `admin`; their effect is shown by the decision-behaviour scenarios and the agreement trend. |
| Per-agent least privilege | Keycloak SA ↔ ContextForge virtual server (tool allow-list) ↔ Bifrost virtual key (model + budget). Verified: the Image agent cannot see or call `flag_ring`. |
| No money-mutating tool reachable by an agent | Refunds are a human-only action. No MCP tool mutates payment state. `scripts/verify_security.py` proves a prompt-injection payload can't escalate privilege or auto-approve. |
| Conflict of interest | A reviewer can't action their own appeal or a case they previously decided; appeals route to a different reviewer. |

## Security model

- **Frontend auth:** Auth.js Keycloak provider, Auth Code + PKCE. Routes role-gated
  server-side and client-side (`customer` → `/shop/*`, `reviewer`+`admin` →
  `/dashboard/*`, `admin` → `/admin/*`).
- **API auth:** FastAPI verifies the Keycloak JWT via JWKS on every request.
- **Per-agent identity:** one Keycloak service account per agent. It maps 1:1 to (a) a
  ContextForge virtual server exposing only that agent's tools, and (b) a Bifrost
  virtual key capping models + spend.
- **Uploads:** magic-byte sniff, size cap, Pillow re-encode to strip EXIF/payloads,
  stored to MinIO with per-object keys + presigned GET.
- **Transport:** `slowapi` rate limiting, locked CORS, security headers, CSRF on form
  posts.
- **Secrets:** Vault only. `structlog` has a redaction processor so secrets never land
  in logs.
- **Threat model** is written up in `docs/SECURITY.md` (prompt injection via return
  free-text or text inside an uploaded image, tool-call exfil, privileged-tool
  coercion) with the mitigations above.

## Conventions

- **Migrations, not `create_all`.** Every schema change is a real Alembic migration.
  A pre-commit hook checks the alembic head is current.
- **Prompts are versioned files** under `worker/pipeline/prompts/`. The content hash is
  logged with every `agent_runs` row. Changing a prompt without bumping its version
  fails a pre-commit hook.
- **One task entrypoint:** the `Makefile`. Every operation is a `make` target.
- **Structured logging:** `structlog`, JSON, a correlation id minted at the API edge and
  propagated through the outbox into the worker and every graph node.
- **Verification:** `scripts/verify_mN.py` + `scripts/run_scenarios.py` (plain runnable
  checks, no framework) + `scripts/smoke.py`, plus the `docs/SCENARIOS.md` catalogue.
  No pytest, no Playwright, no eval-metric harness.
- **Style:** `ruff` (lint + format) + `mypy` for Python, `eslint` + `prettier` for TS,
  `gitleaks` for secrets — all in pre-commit.
- **Laziness with a ceiling:** prefer stdlib and already-present deps; mark deliberate
  shortcuts with a `ponytail:` comment naming the ceiling and the upgrade path. Never
  simplify away input validation, error handling that prevents data loss, security, or
  anything a non-negotiable requires.
- **ADRs** in `docs/decisions/` for every real architectural choice.

## What is deliberately NOT built (scope discipline)

Langfuse v2 (EOL), GPU passthrough by default, Loki/Tempo/Jaeger (Langfuse +
Prometheus/Grafana cover tracing + metrics), Sentry/GlitchTip, k8s/Terraform, i18n,
multi-env config, a custom cache/ORM/DI framework, hosted inference for the local
models, a customer BI webhook stream, disparate-impact monitoring *code* (no
protected-attribute data — the approach is documented in `docs/FAIRNESS.md` only),
a shift-handoff UI. This is a local, single-node portfolio system — it demonstrates
production-grade *practices*, not a live production deployment.
