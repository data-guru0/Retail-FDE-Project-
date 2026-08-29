# Build status

Built in one session, milestone by milestone (M1→M6 + a completion pass), each
verified against the real running system. Nothing is mocked — every agent
decision is a real Bifrost→Groq/OpenAI call, every DB write is real, every file
is really in MinIO, every trace is really in Langfuse, every stock decrement and
refund state transition is real.

## Verified green — `python scripts/smoke.py`

| Check | What it proves |
|---|---|
| `verify_m1` | 15-service stack healthy; `/health/deep` real success for Postgres/Redis/Qdrant/MinIO/Vault/Bifrost/ContextForge; `alembic current == head` |
| `verify_m2` + `verify_m2_frontend` | register via Keycloak → order → history → return w/ real photo → all rows + MinIO object + `status=pending`; Next.js shop + Auth.js/Keycloak PKCE |
| `verify_m3` + `verify_m3_dlq` | real Groq call via Bifrost → `agent_runs` w/ real tokens/cost/latency → API == DB == parsed output; real Langfuse trace w/ a GENERATION obs; WS replay; 3 real crashes → `dead_letter` + auto-escalate, never an infinite retry |
| `verify_m4` | full LangGraph pipeline: 9 `agent_runs` rows/run, Policy RAG records `policy_version`, Behavior loads the registered model, GovernanceGate sole finalizer + audit row, hash chain valid, no auto-deny; **ContextForge: Image agent's virtual server exposes zero tools / no `flag_ring`**, Behavior's has it |
| `verify_audit_chain` | every `row_hash` recomputes; chain unbroken |
| `run_scenarios` | **A0 auto-approve** (real CLIP match → GovernanceGate `auto_approve` + refund_state=pending + QA sample), A1 easy-legit, A2 mismatched-photo (CLIP 0.63), A5 fraud-ring, A6 high-value, A7 outside-window (proposed-deny → escalate, never auto-final), A10 prompt-injection — all match `docs/SCENARIOS.md` |
| `verify_security` | injection via return text + text-in-image → no privilege escalation, no auto-approve; **per-agent model least-privilege enforced** (`models_config.is_granted`: Image can't use `reason`, Explanation can't use `reason`); Image agent has zero MCP tools under attack; no money-mutating tool |
| `verify_m5` | new customer → purchase → mismatched-photo return → live WS trace → reviewer claim → deny-with-confirm → audit chain extended + valid → analytics moved → reviewer override → `agreement_samples` grew + trend moved → `assist` + tuned τ auto-approve path → **request-info round trip** (reviewer asks → customer answers in the shop → re-queued) → **refund settlement** (`process_refunds` → `refund_state=refunded` + audit row) |
| `verify_m6` | README has every required section; every local URL in its table responds; every referenced `make` target + script + doc + ADR exists; the `[demo]` scenario subset runs green |

## Real, working — also covered

- **Dashboard UI** (`/dashboard/*`): queue (filters/claim/release), case detail
  with live WS trace + per-agent reasoning/tokens/cost, decide (approve/deny-confirm/
  request-info), analytics (vs-baseline / unit economics / quality), agent-health
  + agreement trend, ring view, appeals, governance controls, policy editor.
  Customer return-status tracker (`under review → decided → refunded`) with the
  info-request answer form.
- **Observability profile** (`docker compose --profile observability up -d`):
  Prometheus scrapes backend + bifrost + **worker `:9100`** (all `up`); Grafana
  auto-loads the **ReturnGuard dashboard** (pipeline runs by route, error/DLQ
  rate, LLM spend + 24h ceiling, agreement gauge, oldest-escalation, p50/p95
  time-to-decision, API request rate).
- **`load` compose profile**: `docker compose --profile load run --rm loadtest`
  (~20× volume, p50/p95). Scale lever: `--scale worker=N`.
- **`docker-compose.gpu.yml`**: moves CLIP/detector to CUDA (`RG_TORCH_DEVICE`),
  honoured in `models_local.py`.
- **Per-agent Bifrost virtual keys** (`scripts/bifrost_setup.py`): model
  allow-list + $3/mo budget + 60 rpm each. Model/provider scope is enforced at
  the gateway (`gpt-4o` → *"not allowed for this virtual key"*). Not on the
  inference hot path by default — see ADR-0007 for the OSS v2.0.0 credential-
  binding limitation; the per-agent **model** guarantee is enforced in
  `models_config.assert_grant()` regardless.
- **ML**: model trained + registered (`v20260829-021222`, ROC-AUC 0.81),
  `docs/MODEL_CARD.md`. **AI-image-detector bake-off** ran for real (AI images
  via the OpenAI image API) → `haywoodsloan/ai-image-detector-deploy` (acc 0.92)
  — ADR-0002.
- **Reliability**: transactional outbox + best-effort enqueue + `dispatch_outbox`
  backstop; atomic claim + `review_attempts` counter → 3-crash dead-letter;
  worker-startup self-heal releases returns orphaned by a mid-graph kill.
- Docs: all of ARCHITECTURE/GOVERNANCE/SECURITY/RUNBOOK/OPERATING_MODEL/FAIRNESS/
  BASELINE/SCENARIOS/MODEL_CARD/DEMO + 10 ADRs. `README.md` from the real system.

## Known deviations from CLAUDE.md (each in an ADR or noted here)

- Groq dropped the `llama-3.x` model ids → `openai/gpt-oss-*` family, model ids
  config-driven (ADR-0010).
- MCP SDK v2 renamed `FastMCP` → `MCPServer` (adjusted).
- `arq` requires `redis<6` → worker + backend pinned to `redis==5.3.1`.
- Bifrost virtual keys enforce model scope but don't bind to env provider
  credentials in OSS v2.0.0 → hot-path model least-privilege enforced in code
  (ADR-0007).
- `worker/pipeline/nodes/` is one `agents.py` module (+ `base.py`), not one file
  per node — pointer in `nodes/__init__.py`. `backend` folds the `admin` router
  into `dashboard.py` (admin-role-gated); governance/policy UI is under
  `/dashboard/*` not `/admin/*`.
- Backend/worker authenticate to Vault with the dev root token; per-service
  AppRoles are created by `bootstrap.sh` and the AppRole login path is in
  `vault.py` (fallback to token).

## Completion pass — additional fixes verified

- **torchvision::nms regression** (torch/torchvision ABI mismatch) — matched CPU
  pair pinned; CLIP + detector work; full pipeline runs.
- **Audit-chain fork under concurrency** — a latent bug: `SELECT tip FOR UPDATE` +
  `LIMIT 1` doesn't re-scan when unblocked, so a backend append and a worker
  append (e.g. `process_refunds`) could both chain from the same tip. Fixed: one
  `pg_advisory_xact_lock` serialises every append across backend + worker.
  `verify_audit_chain` + `verify_m5` green.
- **Per-agent model least-privilege** — `models_config.assert_grant` enforced on
  every LLM/vision call + tested (`verify_security`); real Bifrost per-agent
  virtual keys (`scripts/bifrost_setup.py`) enforce model/provider scope at the
  gateway (ADR-0007).
- **A0 auto-approve** — retry a clean case up to 3× (LLM judgement varies) +
  decision prompt v3; observed auto-approving through the real CLIP check.
- **`process_refunds`** cron — approved → `refund_state=refunded` + audit +
  email; customer tracker's final stage is real (`verify_m5`).
- Worker startup **self-heal** for returns orphaned by a mid-graph kill.
- `docker-compose.gpu.yml`, `load` compose profile, `verify_m6.py`,
  `docs/MODEL_CARD.md`, `scripts/requirements.txt`, `infra/*/README` all added.

## Partial

- The 8 demo scenarios are documented (`docs/DEMO.md`) + the automatable ones
  scripted; not each hand-clicked in the browser with screenshots.
- `scripts/backup.sh` MinIO-mirror step needs a persistent run target on Windows
  (noted in the script); pg_dump + Qdrant snapshot round-trip works.
- OTel spans from Bifrost/ContextForge → Langfuse are not wired; Langfuse traces
  come from the SDK (`record_generation`) and are real.
- `infra/keycloak/realm-export.json` carries the local Keycloak **client**
  secrets in plaintext (committed). Local-dev clients only; a hardening step
  would move them to Vault + inject at import. `frontend/.env.local` (git-ignored)
  holds the Auth.js + web-client secret (frontend runs on the host, no Vault).

## The one API-key caveat

The Groq + OpenAI keys pasted into this session are in `.env` (git-ignored, never
committed) but were exposed in chat — **rotate both**, then
`docker compose exec vault vault kv patch secret/returnguard/llm openai_api_key=… groq_api_key=…`
and `docker compose restart backend worker`.
