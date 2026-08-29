# Build plan

Work through this in one continuous session — build, test for real, fix what fails,
move on. Do not stop between milestones to check in. Only stop for a genuine blocker
(missing credential, ambiguous spec, a library that doesn't behave as assumed — see
CLAUDE.md's non-negotiables, and the "Known unknowns" section at the end). Otherwise:
implement a piece, run it for real, if it's broken fix it and run it again, then move
straight to the next piece.

Do not mark anything done if any part of it is mocked, stubbed, or faked. No pytest, no
Playwright — verify by actually running the app and reading real output. Each milestone
has a `scripts/verify_mN.py` that must pass before moving on; it drives the live system
and asserts against real DB / MinIO / Langfuse state.

The milestones below are an order to build in, not checkpoints to wait at.

Before starting: re-verify the latest stable version of every dependency in CLAUDE.md's
stack table (`pip index versions`, `npm view`, the tool's site). The recorded versions
are from Aug 2026 — bump to newer stable where it exists.

---

## Milestone 1 — Infra & project setup

- [ ] Scaffold the repo structure from CLAUDE.md. `pyproject.toml` for `backend/` and
      `worker/`, `package.json` for `frontend/`, all pinned to verified-latest.
- [ ] `docker-compose.yml` with named volumes and healthchecks on every stateful
      service, `depends_on: condition: service_healthy` where it matters:
      Postgres 18, Redis 7, Qdrant, Keycloak 26.7.x (heap capped 512 MB),
      Vault (dev mode), MinIO, MailHog, ClickHouse (memory-capped ~2 GB),
      `langfuse-web`, `langfuse-worker`, `bifrost` (LLM gateway),
      `mcp-gateway` (ContextForge), `backend`, `worker`, `mcp-server`.
      Langfuse / Bifrost / ContextForge reuse the app's Postgres (separate logical DBs),
      Redis (separate DB index), and MinIO (separate bucket) — do not stand up
      duplicates.
- [ ] `observability` compose profile: Prometheus + Grafana with datasource + dashboards
      provisioned as code. `load` profile: the loadtest tooling.
- [ ] `docker-compose.gpu.yml` override (CLIP/detector on CUDA) — present but not the
      default.
- [ ] `scripts/preflight.sh` (Docker daemon up? ports free? disk space?) wired into
      `make up`.
- [ ] `infra/vault/bootstrap.sh`: enable KV v2, write one policy + AppRole per service,
      load `GROQ_API_KEY` + `OPENAI_API_KEY` (from `.env`) and generated
      DB/MinIO/Keycloak credentials. `backend`/`worker` read Vault at boot via
      `pydantic-settings`.
- [ ] `.env.example` with empty `OPENAI_API_KEY`, `GROQ_API_KEY`, `DATABASE_URL`,
      `REDIS_URL`, `QDRANT_URL`, `MINIO_*`, `LANGFUSE_*`, `KEYCLOAK_*`, `VAULT_*`,
      `BIFROST_URL`, `MCP_GATEWAY_URL`.
- [ ] `infra/bifrost/config.json`: Groq + OpenAI providers, the fallback chain
      (`llama-3.3-70b-versatile` → `openai/gpt-oss-120b` → `gpt-4o-mini`), one virtual
      key per agent + one per service, per-key budgets + rate limits.
- [ ] Alembic **baseline migration** creating the full schema from CLAUDE.md's data
      model (all core tables + constraints + enums + indexes + `created_at/updated_at`
      triggers + the `audit_log` hash-chain columns).
- [ ] `backend/app/health.py` — `/health/deep` runs **real** queries: Postgres
      (`SELECT 1` + a table count), Redis (`PING` + set/get), Qdrant (list collections),
      MinIO (bucket exists), Vault (token lookup), Bifrost (`/health`), ContextForge
      (`/health`). No health-check stub.
- [ ] `structlog` JSON logging + OpenTelemetry wiring (`backend/app/telemetry.py`),
      correlation id minted at the API edge.
- [ ] Pre-commit: `ruff`, `mypy`, `eslint`, `prettier`, `gitleaks`, prompt-version
      check, alembic-head check.
- [ ] `Makefile` with `up`, `up-lite`, `down`, `seed`, `migrate`, `smoke`, `logs`,
      `vault-init`, `help` (more targets land in later milestones).
- [ ] `docs/decisions/ADR-0001` (Python 3.13 in Docker), `ADR-0004` (Langfuse v3 shared
      infra), `ADR-0006` (Qdrant vs pgvector), `ADR-0007` (Bifrost as LLM gateway only).

**Self-check (`verify_m1.py`):** `docker compose up -d` → poll until every container is
healthy → `GET /health/deep` → assert every dependency reports real success → assert
`alembic current` equals head. Resolve the ContextForge auth question here (see Known
unknowns) and record it in `ADR-0009`.

---

## Milestone 2 — The shop

- [ ] `seed/seed.py`: download 25–30 real product images, insert real products (real
      names, descriptions, prices, categories) across ≥3 categories into Postgres +
      MinIO.
- [ ] `infra/keycloak/realm-export.json` imported at boot: `customer` / `reviewer` /
      `admin` realm roles, a frontend OIDC client, a backend confidential client, and
      one service-account client per agent (Planner, Intake, Policy, Image, Behavior,
      Decision, Critic, Explanation).
- [ ] Frontend: Auth.js Keycloak login/register (real tokens, not a fake session);
      product listing with filter + sort; product detail; cart (persisted); checkout
      with a **mock-payment step** (Luhn-validated fake card — no real money moves) that
      creates a **real** `orders` + `order_items` row.
- [ ] Order-history page reading the logged-in user's real orders (JWT-scoped).
- [ ] Return-request wizard: pick item → pick reason → upload a real photo (magic-byte
      sniff, size cap, Pillow re-encode to strip EXIF, stored to MinIO, row in
      `return_photos`) → submit → `returns` row `status=pending` + `outbox` row in one
      transaction.
- [ ] MailHog emails on order-placed and return-submitted.
- [ ] `openapi-typescript` generates `frontend/lib/api/` from the live FastAPI schema.

**Self-check (`verify_m2.py`):** register a fresh account via Keycloak, log in, list
products, place an order, read it back from order history, submit a return with a real
uploaded image file. Then assert: the matching `orders` / `order_items` / `returns` /
`return_photos` / `outbox` rows exist in Postgres, the object exists in MinIO, and the
return status is `pending`.

---

## Milestone 3 — Single-agent return flow (get the pipe working end to end)

- [ ] `arq` worker consumes the outbox/queue.
- [ ] One real Groq call **via Bifrost** (OpenAI-compatible endpoint) reads the return
      (order + item + reason + customer context) and produces an actual structured
      decision + reasoning — guardrail-validated JSON with a real repair-retry on bad
      output. No hardcoded branch anywhere. Bifrost's fallback chain is active.
- [ ] Decision written to `returns` + a real `agent_runs` row (agent, model, tokens,
      cost, latency, `automation_level`). `automation_level` defaults to `shadow` — the
      agent decides but the human still acts, so agreement data accrues from day one.
- [ ] WebSocket event pushed; the customer sees the real result on the return-status
      page.
- [ ] Real Langfuse trace linked from the `agent_runs` row.
- [ ] Dead-letter: 3 crashes on one case → `dead_letter` row + escalate + log, never an
      infinite retry.

**Self-check (`verify_m3.py`):** submit a return; confirm via Bifrost's dashboard/logs
that a real upstream call went to Groq; then assert the result shown by the API equals
the `returns` row equals the `agent_runs` parsed output (tokens/cost populated from
Bifrost), and a Langfuse trace exists for it.

---

## Milestone 4 — Full multi-agent pipeline

- [ ] Build the LangGraph graph exactly as specified in CLAUDE.md: Data-quality gate →
      Planner → Intake → Policy → Image → Behavior → Decision → Critic → Explanation →
      `GovernanceGate`, with a Postgres checkpointer, every node writing `agent_runs`
      and streaming `agent_run_events`. Data-quality gate: missing/corrupt inputs →
      escalate "insufficient data", never guess.
- [ ] `GovernanceGate`: the only place a decision is finalized. Reads `automation_level`
      + per-category flags + kill switch. Auto-deny → always `escalate(proposed=deny)`.
      Auto-approve → only if `risk < tau_risk` and `confidence > tau_conf` and no Critic
      veto and the level allows it. Everything else → escalate. In `assist`, X% of
      auto-approvals are still sampled into the human queue.
- [ ] Policy agent: write real return-policy text (return windows, category exceptions,
      condition rules), embed with `text-embedding-3-small` via Bifrost, load into
      Qdrant, do real retrieval per case, record the `policy_docs` version in force.
- [ ] Image agent: real CLIP similarity (product photo vs return photo); route borderline
      scores to a real OpenAI vision call via Bifrost; run a **one-time** bake-off of
      2–3 AI-image detectors on a small labeled sample in `ml/detector_bakeoff/` and
      wire in whichever performs best. Record the numbers and the choice in
      `docs/decisions/ADR-0002`. (This is a one-off component pick, not an ongoing eval
      harness.)
- [ ] `ml/generate_dataset.py`: a realistic synthetic dataset (thousands of rows, not
      tens) of customers/orders/returns with genuine statistical patterns — a high-
      return cohort, ≥2 fraud rings sharing address/device/payment fingerprints,
      seasonal noise, no label leakage.
- [ ] `ml/train.py`: fixed seed, train/val/test split, isotonic calibration, metrics
      JSON, feature importance, `docs/MODEL_CARD.md` (intended use, data, metrics,
      limitations, ethics), dataset snapshot hash. Versioned artifacts in
      `ml/registry/`. The Behavior agent loads the registered model by version and logs
      the version per run.
- [ ] Behavior agent = model risk score + real LLM read of the qualitative pattern +
      ring-detection query.
- [ ] Ring detection: a real SQL query over `fingerprints` for shared
      address/device/payment fingerprint across accounts. Feeds the Behavior agent and
      the dashboard's Ring view.
- [ ] Stand up the MCP tools backend (`mcp-server`) exposing `get_order`,
      `check_policy`, `get_customer_history`, `flag_ring` as real MCP tools. Put
      ContextForge in front: one **virtual server per agent** exposing only that agent's
      allowed tools, Keycloak SA JWT validation, per-call audit → ContextForge +
      OTel/Langfuse + our `audit_log`. Agents reach tools only through the gateway; each
      LLM call in every node goes through Bifrost with the agent's virtual key.
- [ ] Write the **scenario catalog** (`docs/SCENARIOS.md`) — ~20 real end-to-end
      situations describing how the finished system behaves, each as
      **seeded setup → exact steps → expected observable outcome** (decision, route,
      which agents fired, resulting `returns` + `audit_log` state, live trace). Three
      groups:
      - *Decision behaviour:* easy-legit / matching photo (auto-approves), mismatched
        photo, AI-faked damage photo, serial returner, fraud ring,
        high-value-within-policy, outside the return window, ambiguous / worn item,
        incomplete request (data-quality gate), prompt-injection in the return reason.
      - *Governance controls:* kill switch on, each `automation_level`, an `admin`
        policy edit + re-embed applied to a later case, a reviewer override, an appeal
        routed to a different reviewer with the COI guard, the request-info round trip.
      - *Operational:* pipeline crash 3× → dead-letter → auto-escalate, Groq error →
        Bifrost fallback to OpenAI (decision still real), ~20× return volume → queue
        holds, p95 measured.
      Mark the audience-facing subset **[demo]**.
- [ ] `scenarios/fixtures/` — the seeded data + photos each scenario needs.
- [ ] `scripts/run_scenarios.py` — drives every automatable scenario through the **real**
      pipeline and asserts each behaves exactly as `docs/SCENARIOS.md` documents. No
      score, no pass-rate — each scenario either matches its description or it doesn't.
- [ ] `worker/replay.py` (deterministic single-node replay) and `worker/reprocess.py`
      (`--since --until --policy-version` batch re-run).
- [ ] `docs/decisions/ADR-0002`, `ADR-0003` (hash-chain audit), `ADR-0005` (outbox),
      `ADR-0008` (graduated autonomy).

**Self-check (`verify_m4.py` + `scripts/run_scenarios.py`):** every *decision behaviour*
scenario in `docs/SCENARIOS.md` runs through the real pipeline and produces exactly the
documented outcome — right decision, right route (auto-approve / escalate /
human-confirm), right agents firing, right audit trail, real Langfuse trace. Separately
assert the Image agent's ContextForge virtual server has **no** `flag_ring` in its
`list_tools` response and a direct `call_tool` with the Image agent's credentials
returns a real 403.

---

## Milestone 5 — Dashboard, governance, polish

- [ ] Build all six dashboard sections against real backend data:
      - **Queue** — filters, sort, SLA timers, case **claim/release** (`claimed_by` /
        `claimed_at`, auto-release after inactivity), bulk-approve selected low-risk
        escalations (each still writes its own audit row), canned decision-reason
        templates.
      - **Case detail** — live agent trace over WebSocket, streaming each node's **real**
        output as the graph executes (with tokens / cost / latency per node) — not a
        canned animation. Evidence panel, agent-by-agent reasoning, action bar.
      - **Analytics** — computed from real aggregate queries + real Langfuse spend:
        fraud caught, false-positive rate from actual override history, **vs-baseline**
        (reviewer-hours saved, $ saved, p50/p95 time-to-decision), **unit economics**
        (cost-per-decision broken out by model, monthly projection, all-human vs current
        vs full-auto). Baseline assumptions live in `docs/BASELINE.md` and are read by
        the Analytics code.
      - **Agent health** — from Langfuse + `agent_runs`; includes the rolling
        agent-vs-human agreement trend per agent / decision type.
      - **Ring detection** — the shared-fingerprint account graph.
      - **Appeals** — plus an appeal-overturn-rate-by-category/agent panel.
- [ ] **Governance controls** (`admin`): `automation_level` selector
      (shadow/suggest/assist/auto) global + per-category, kill switch, QA-sampling %,
      threshold knobs — all stored in `feature_flags`, read per run.
- [ ] **Policy editor** (`admin`): edit policy text → re-embed to Qdrant → new
      `policy_docs` version; `agent_runs.policy_version` records what applied.
- [ ] Approve / Deny / Request-info actually write to `returns` + the hash-chained
      `audit_log` — not just the UI. Deny requires the human confirm step.
- [ ] **Request-info round trip**: reviewer question → customer email (MailHog) →
      customer answers in the shop (`info_requests`) → case re-enters the queue with the
      response attached.
- [ ] Appeal flow: a denied return can be contested → creates a new review task routed
      to a **different** reviewer account; the conflict-of-interest guard blocks a
      reviewer from actioning their own appeal or a case they previously decided.
- [ ] When a reviewer overrides an agent decision, log it to `audit_log` +
      `agreement_samples`; it feeds the agent-vs-human agreement trend on the
      Agent-health page. If the override exposes a behaviour not already in
      `docs/SCENARIOS.md`, add a new scenario for it.
- [ ] **Customer return-status tracker** page: `under review → approved/denied →
      refunded` (a real `refund_state` + row + email; no money moves).
- [ ] **Auditor case export** endpoint: a single signed bundle for one case (all
      `agent_runs` + prompts & versions + model ids + inputs + tool calls + human
      actions + timestamps + policy version) as JSON + rendered HTML, plus canned
      compliance queries ("every auto-approved return > $500 in March").
- [ ] Wire Langfuse fully — every `agent_runs` row has a matching real trace.
- [ ] Grafana dashboards live; Prometheus alert rules loaded (queue SLA breach, cost/day
      ceiling, error-rate spike, agreement drift).
- [ ] `scripts/verify_security.py`: fires a prompt-injection return reason + text inside
      an uploaded image and asserts no privilege escalation and no auto-approve.
- [ ] `docs/GOVERNANCE.md`, `docs/SECURITY.md` (incl. threat model), `docs/FAIRNESS.md`,
      `docs/RUNBOOK.md` (kill-switch drill, queue drain, DLQ handling, key rotation),
      `docs/OPERATING_MODEL.md`, `docs/ARCHITECTURE.md`.
- [ ] Backup: `scripts/backup.sh` (`pg_dump` + Qdrant snapshot + MinIO mirror →
      `backups/`) and `scripts/restore.sh`. `Makefile` targets `scenarios`, `demo`,
      `train`, `dataset`, `loadtest`, `backup`, `restore`.

**Self-check (`verify_m5.py`):** a full scripted walkthrough — new customer → real
purchase → real return with a mismatched photo → confirm live trace events streamed over
WebSocket → reviewer account claims it in the queue → deny with the confirm step →
assert the `audit_log` hash chain extended and still validates → assert a vs-baseline
analytics number moved → override a different case → assert `agreement_samples` grew and
the agreement trend moved → flip `automation_level` to `assist`, submit an easy case,
assert it auto-approves and a QA sample lands in the queue. Then `verify_security.py`
passes.

---

## Milestone 6 — Demo walkthrough + README.md

The demo scenarios below are the **[demo]**-marked subset of `docs/SCENARIOS.md` — the
ones you show to an audience. First, seed whatever accounts / data each needs (into
`scenarios/fixtures/`), and walk through every one yourself until it actually behaves as
described. Run one real `loadtest.py` at ~20× normal return volume and record p95
time-to-decision + the worker-replica scaling lever in `docs/RUNBOOK.md`. Confirm
`scripts/run_scenarios.py` is green across the whole catalog, not just the demo subset.

Then write `README.md` from scratch — you're documenting a real, working system at this
point, not describing a plan, so every command and every scenario in it must be
something you personally just ran and confirmed. Write it so a complete beginner —
someone who has never touched this codebase — can follow it with no extra help.

`README.md` must contain:

- A plain-language explanation of the problem this solves and why it's built the way it
  is (the FDE framing: one company, one real process, replaced with a governed agent
  system, not a chatbot) — no jargon, written for someone non-technical.
- A simple, non-technical walkthrough of how it works (the agent pipeline, in plain
  words, not architecture-speak), including what "shadow / suggest / assist / auto"
  means and why the system starts in shadow.
- Prerequisites and full setup, from a completely clean checkout, as exact
  copy-pasteable commands — verify this by actually deleting `node_modules` and
  rebuilding the backend/worker images and following your own instructions from nothing.
- A table of every local URL (shop, dashboard, API docs, Langfuse, Keycloak, Qdrant,
  Grafana, Prometheus, Bifrost, ContextForge, MinIO, MailHog, Vault) and what each is
  for.
- Every demo scenario below: exact steps to trigger it, what the reader should see
  happen, and a one-line "why this matters" talking point connecting it to AI
  governance — written for someone showing this to students who've never seen the
  project. (Point to `docs/SCENARIOS.md` for the full behaviour catalog.)
- A troubleshooting section for whatever actually went wrong while you were building
  and testing it.

Demo scenarios to seed, verify, and document (the **[demo]** subset of
`docs/SCENARIOS.md`):

1. **The easy case** — a return clearly within policy with a matching photo,
   auto-approved in seconds.
2. **The mismatched photo** — a return photo that doesn't match what was sold, caught by
   the Image agent.
3. **The AI-faked damage photo** — an AI-generated "damage" photo, caught by the
   AI-image detector.
4. **The serial returner** — a seeded high-return-history account, flagged by the
   Behavior agent even when one return looks fine alone.
5. **Ring detection** — two seeded accounts sharing an address, flagged together.
6. **The appeal** — a denied return, appealed, routed to a different reviewer.
7. **Watching an agent think** — the live trace populating step by step in the dashboard
   as a real case runs through the graph.
8. **The rollout story** — the same easy case in `shadow` (agent decides, human still
   acts, agreement logged) vs `assist` (auto-approved), with the agreement trend and
   vs-baseline numbers that justify moving up the ladder. Talking point: trust is
   earned, not toggled.

**Self-check:** hand `README.md` to yourself as if you'd never seen this repo — follow
the setup from scratch and run every scenario exactly as written. If anything in the doc
doesn't match reality, fix the doc.

---

## Final pass

- [ ] `make smoke` green — all `verify_m1..m6` + `verify_audit_chain.py` +
      `verify_security.py` + `scripts/run_scenarios.py` (every scenario in
      `docs/SCENARIOS.md` behaves exactly as documented).
- [ ] Confirm `README.md`'s setup commands work on a truly clean checkout.
- [ ] Full pass over the whole codebase looking specifically for anything mocked,
      stubbed, faked, or hardcoded, and fix it — check against every non-negotiable in
      CLAUDE.md one more time.
- [ ] `docs/OPERATING_MODEL.md`, `docs/BASELINE.md`, `docs/FAIRNESS.md`, and all nine
      ADRs are complete and match what was actually built.

---

## Known unknowns to resolve during the build (don't fake past these)

- **API keys.** `GROQ_API_KEY` + `OPENAI_API_KEY` must be in `.env` before Milestone 3
  (Milestones 1–2 need neither). If they're absent when M3 starts, stop and ask.
- **ContextForge ↔ Keycloak JWKS.** Confirm at M1 whether the OSS ContextForge build
  validates external Keycloak JWTs directly. If it only accepts its own bearer tokens,
  mint a per-agent gateway token from each Keycloak service account at the worker and
  map 1:1. Either way the "Image agent can't call `flag_ring`" requirement must hold.
  Record the outcome in `ADR-0009`.
- **Groq model availability.** `llama-3.3-70b-versatile` carried a mid-2026 deprecation
  notice but is still served. The Bifrost fallback chain
  (`→ openai/gpt-oss-120b → gpt-4o-mini`) covers a 400; a fallback is a real response,
  never a fake one. If Groq is fully unavailable, switch the primary to
  `openai/gpt-oss-120b` and note it.
- **AI-image detector choice.** No universal winner in 2026 benchmarks — the pick is
  made empirically at M4 on a small labeled sample and justified in `ADR-0002`. It is
  always one signal into escalation, never a lone auto-deny.
- **LLM/API spend.** Real money. Pipeline + scenario runs default to `gpt-4o-mini` +
  Groq; per-case cost budget + a daily ceiling alert are wired via Bifrost virtual keys.
