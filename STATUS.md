# Build status

Built in one session, milestone by milestone, each verified against the real
running system before moving on. Nothing is mocked — every agent decision is a
real Bifrost→Groq/OpenAI call, every DB write is real, every file is really in
MinIO, every trace is really in Langfuse.

## Verified green

| Check | What it proves |
|---|---|
| `scripts/verify_m1.py` | 14-service stack healthy; `/health/deep` real success for Postgres/Redis/Qdrant/MinIO/Vault/Bifrost/ContextForge; `alembic current == head` |
| `scripts/verify_m2.py` | register via Keycloak → order → order history → return w/ real photo → `orders`/`order_items`/`returns`/`return_photos`/`outbox` rows + MinIO object + `status=pending` |
| `scripts/verify_m2_frontend.py` | Next.js shop renders; Auth.js Keycloak provider + PKCE authorize accepted |
| `scripts/verify_m3.py` | one real Groq call via Bifrost → `agent_runs` row (real tokens/cost/latency) → decision on API == returns row == parsed output; Langfuse trace with a GENERATION obs really exists; WS replayed the trace |
| `scripts/verify_m3_dlq.py` | 3 real crashes → `dead_letter` + auto-escalate; never an infinite retry |
| `scripts/verify_m4.py` | full LangGraph pipeline: 9 agent_runs rows for one graph run, Policy RAG records `policy_version`, Behavior loads the registered model, GovernanceGate is the sole finalizer + writes audit_log, hash chain validates, no auto-deny; **ContextForge: Image agent's virtual server exposes zero tools / no flag_ring**, Behavior's has flag_ring |
| `scripts/verify_audit_chain.py` | every `row_hash` recomputes; chain unbroken |
| `scripts/run_scenarios.py` | A1 easy-legit, A2 mismatched-photo (CLIP 0.63), A5 fraud-ring (linked accounts), A6 high-value, A7 outside-window (proposed-deny → escalate, never auto-final), A10 prompt-injection — all match `docs/SCENARIOS.md` |
| `scripts/verify_security.py` | injection via return text + text-in-image → no privilege escalation, no auto-approve; least privilege holds; no money-mutating tool |
| `scripts/verify_m5.py` | new customer → purchase → mismatched-photo return → live WS trace → reviewer claim → deny-with-confirm → audit chain extended + valid → analytics number moved → override → `agreement_samples` grew + trend has data → `assist` + tuned τ path exercised |

Run all: `python scripts/smoke.py`

## Real, working, not yet in a dedicated verify

- The **dashboard UI** (Next.js `/dashboard/*`) — pages compile and call the
  verified backend endpoints; fully exercising them needs a browser OAuth login
  (the backend paths themselves are covered by `verify_m5`).
- **AI-image-detector bake-off** ran for real (`ml/detector_bakeoff/`): AI images
  generated via the OpenAI image API, 3 detectors scored,
  `haywoodsloan/ai-image-detector-deploy` chosen (acc 0.92) — see ADR-0002.
- **ML model** trained + registered (`v20260829-021222`, ROC-AUC 0.81),
  `docs/MODEL_CARD.md` written, loaded by the Behavior agent by version.

## Done

- All 8 verify scripts + `run_scenarios.py` + `verify_audit_chain.py` +
  `verify_security.py` pass (see the table above). `scripts/smoke.py` runs the lot.
- `docs/`: ARCHITECTURE, GOVERNANCE, SECURITY, RUNBOOK, OPERATING_MODEL, FAIRNESS,
  BASELINE, SCENARIOS, MODEL_CARD — all written. All 10 ADRs present.
- `README.md` written from the real running system (setup commands were all run;
  troubleshooting is the real list of things that broke).

## Partial / not exercised

- **M6 demo walkthrough** — `README.md` documents the 8 `[demo]` scenarios and
  `run_scenarios.py` covers the automatable decision-behaviour ones; they are not
  each hand-walked in the browser UI with screenshots.
- **`scripts/loadtest.py`** — written (concurrent submit + p50/p95), not driven at
  full 20× yet. The scaling lever (`--scale worker=N`) is real.
- **`scripts/backup.sh` / `restore.sh`** — written, `pg_dump` + Qdrant snapshot
  paths tested piecemeal, not a full round trip.
- **Observability profile** — Prometheus/Grafana compose services + Grafana
  datasource/dashboard provisioning exist; the worker `/metrics` endpoint and the
  dashboard JSON are not wired. Langfuse (the primary observability surface) is
  fully working.
- **Auto-approve happy path** — the code + `assist`/`auto` gating + threshold
  tuning are verified; seeing the pipeline actually emit `auto_approve` needs a
  fixture photo that CLIP matches to its product (the current fixtures are
  deliberately mismatched, so easy cases escalate on the image check).

## Known deviations from CLAUDE.md (each recorded in an ADR)

- Groq dropped the `llama-3.x` model ids → switched to the served `openai/gpt-oss-*`
  family, model ids config-driven (ADR-0010).
- MCP SDK v2 renamed `FastMCP` → `MCPServer` (adjusted).
- `arq` requires `redis<6` → worker + backend pinned to `redis==5.3.1`.
- `torch` installed as the CUDA build (runs fine on CPU) — the CPU-index install
  was overridden by a transitive dep; not worth another long rebuild.

## The one API-key caveat

The Groq + OpenAI keys the user pasted are in this session's `.env` (gitignored,
never committed). **Rotate both** after reviewing — they were exposed in the chat.
