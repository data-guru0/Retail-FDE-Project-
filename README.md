# ReturnGuard

**A real e-commerce return/refund process, run by a governed multi-agent AI system.**

Most "AI agent" demos are a chatbot with a nice prompt. ReturnGuard is the
opposite: one company, one real operational process — reviewing every
return/refund request — handed to a system of AI agents that is **watched,
bounded, and reversible**. The agents auto-clear the obviously-legitimate
returns and route anything risky, unclear, or expensive to a human, through a
real fraud-review dashboard. Every decision is traceable to the exact model,
prompt version, policy version, inputs, tokens, and cost that produced it.

It's a portfolio project for Forward Deployed Engineer work — the emphasis is on
the parts that are hard in the field: **governed autonomy, full observability,
per-agent identity, scenario-driven validation, a business case, and a clean
handoff** — not on "an agent that answers".

It runs entirely on one machine via Docker Compose. Nothing is deployed anywhere.
The only things that cost money are the Groq and OpenAI API calls.

---

## The problem this solves, in plain words

A retailer gets a stream of return requests: "it arrived broken", "wrong item",
"changed my mind". Each one needs someone to check the order, check the return
policy, look at the photo, weigh the customer's history, and decide: refund,
deny, or ask a question. It's repetitive, it's judgement-heavy, and a small
fraction of requests are outright fraud (fake damage photos, serial returners,
rings of accounts sharing an address).

Doing this entirely by hand is slow and expensive. Handing it entirely to an AI
is reckless — a model that can silently issue refunds is a model that can be
tricked into issuing refunds. ReturnGuard is the middle path: the AI does the
legwork and proposes an outcome; **the system only acts within limits a human
set, and every denial still needs a human**.

## How it works, in plain words

When a customer submits a return, it goes through a pipeline of small
specialised agents:

1. **Data-quality gate** — is there enough to decide on? (a photo where the
   policy needs one, a readable image, a real product). If not, it stops and
   asks a human. It never guesses.
2. **Planner** — picks which of the checks below this particular case needs.
3. **Intake** — is the request coherent? (reason matches the description,
   amount makes sense).
4. **Policy** — looks up the *actual current return-policy text* (stored,
   versioned, searched with embeddings) and decides eligibility strictly from
   it. Records which policy version it used.
5. **Image** — compares the return photo to the product photo (a local vision
   model), and screens for AI-generated "damage" photos. One signal, never a
   lone rejection.
6. **Behaviour** — a trained risk model scores the numeric pattern (return rate,
   account age, refund size, time since order), a language model reads the
   qualitative pattern, and a database query looks for other accounts sharing
   this one's address / device / payment fingerprint (a fraud "ring").
7. **Decision** — combines everything into: approve / deny / escalate.
8. **Critic** — a second model reviews the Decision's reasoning and can force
   the case to a human.
9. **Explanation** — writes a plain-English reason for the customer, the
   reviewer, and the audit log.
10. **Governance Gate** — the **only** place a decision becomes final. It reads
    the current automation level and the safety thresholds and applies hard
    rules (below). Anything it can't finalise safely goes to a human.

### shadow → suggest → assist → auto

The system runs at one of four **automation levels**, set by an admin, globally
or per product category:

- **shadow** *(the default, where every deployment starts)* — the agents run and
  their decision is logged, but humans still do everything. Agreement data
  accrues from day one at zero risk.
- **suggest** — the reviewer's screen is pre-filled with the agent's decision;
  humans still act.
- **assist** — the system **auto-approves** low-risk, high-confidence returns;
  everything else goes to humans. A percentage of the auto-approvals are still
  sampled into the human queue for quality control.
- **auto** — like assist, without the QA sampling.

Moving up the ladder is a deliberate act, justified by the agent-vs-human
agreement trend and the "hours saved / dollars saved" numbers on the Analytics
page. *Trust is earned, not toggled.*

Hard rules the Governance Gate enforces **regardless of level**:

- A global **kill switch** sends every case to a human.
- **Auto-deny is impossible.** A "deny" proposal always becomes
  *escalate-with-a-proposed-denial*; only a human's explicit confirm step
  produces a denied return.
- **Auto-approve is bounded** — only if risk < threshold, confidence >
  threshold, no Critic veto, no high-value flag, and the level allows it.
- Any refund over the high-value threshold needs human sign-off.

Everything a person does in the dashboard — approve, deny, request info, claim a
case, edit policy, change the automation level — writes to the database and to an
**append-only, hash-chained audit log**. `scripts/verify_audit_chain.py` re-walks
the chain and fails on any tamper.

---

## What's inside (the stack)

| Layer | Tech |
|---|---|
| Shop + dashboard | Next.js 16 (App Router), Auth.js + Keycloak (OIDC + PKCE); API types generated from the backend's OpenAPI schema (`openapi-typescript` + `openapi-fetch`) |
| API + WebSocket | FastAPI (Python 3.13, Docker), SQLAlchemy 2 async, Alembic; `slowapi` rate limiting, `asgi-correlation-id` + `prometheus-fastapi-instrumentator` |
| Worker | `arq` on Redis; **LangGraph** pipeline with a Postgres checkpointer |
| LLM gateway | **Bifrost** — one endpoint for Groq + OpenAI, fallback chains, per-agent virtual keys, cost/latency telemetry |
| MCP governance | **IBM ContextForge** in front of a plain MCP tools server — one virtual server per agent, exposing only that agent's tools |
| Policy engine | **OPA** (Open Policy Agent) — the auto-approve/escalate decision *and* every per-agent tool/model grant are `.rego` policy in `infra/opa/`, not app code |
| Vector store | Qdrant (return-policy RAG) |
| Local ML | scikit-learn risk model; open-clip CLIP; an AI-image detector — all CPU. The trained model's card is written to `ml/registry/<version>/MODEL_CARD.md` by `make train` |
| Observability | **Langfuse v3** (self-hosted, shares Postgres/Redis/MinIO, + ClickHouse) — traces every agent call *and* holds the versioned, trace-linked agent prompts |
| Identity | Keycloak — `customer` / `reviewer` / `admin`, plus one service account per agent |
| Storage / email / secrets | MinIO / MailHog / **HashiCorp Vault** (every runtime secret) |

### How a return flows through it

```
Customer (browser)
  └─ Next.js (host) ── Auth.js/Keycloak OIDC+PKCE ──► Keycloak
        │  server-side token proxy (/api/rg/*)  — the token never reaches the browser
        ▼
     FastAPI backend (Docker) — verifies the Keycloak JWT (JWKS) on every request
        ├─ submit return  ─►  returns + return_photos + outbox  (one transaction)
        │                     + best-effort arq enqueue
        └─ WebSocket /ws/returns/{id}  ◄── Redis pub/sub  rg:events:{id}

Worker (Docker, arq on Redis)
  ├─ dispatch_outbox cron — durability backstop (no review job is ever lost)
  └─ review_return
        └─ LangGraph pipeline (Postgres checkpointer, schema `langgraph`)
             data_quality → planner → intake → policy(RAG) → [image] → behavior
                → decision → critic → explanation → GovernanceGate
             every node: an agent_runs row + agent_run_events (+ Redis publish)
                         + a Langfuse generation
             each LLM call ─► Bifrost ─► Groq / OpenAI   (per-agent virtual key)
             tool calls    ─► ContextForge ─► mcp-server ─► Postgres
             allow/deny    ─► OPA (asked before every tool call, model call, and
                              at the gate; fails closed)
             GovernanceGate — the only finalizer → returns + hash-chained audit_log
```

**Trust boundaries:** browser → Next.js (session cookie only, no token);
Next.js → backend (Keycloak JWT, JWKS-verified per request); backend/worker →
Vault (AppRole, dev-token fallback); agent → tools (OPA `allow_tool` /
`allow_model` on the hot path, mirrored by Keycloak SA ↔ ContextForge virtual
server ↔ Bifrost virtual key); refunds are **human-only** — no MCP tool mutates
payment state; auto-approve vs escalate is **OPA policy**, not app code.

**Postgres** also hosts separate logical DBs for Langfuse / Bifrost / the MCP
gateway and a `keycloak` schema. `pgvector` is deliberately unused (Qdrant is
the vector store).

---

## Run it from a clean checkout

This is written for someone starting with **an empty machine**. Do the steps in
order, top to bottom. Every step says what the command does and how to tell it
worked. First run is ~15–20 min wall-clock, almost all of it Docker downloading
and building images. You need ~9 GB of free RAM while the stack is up.

### Step 0 — install the four prerequisites

You need Git, Docker Desktop, Node.js 20+ (24 recommended), and Python 3.11+.
Pick your OS.

**Windows 11**

```powershell
# run in PowerShell; installs all four via winget
winget install --id Git.Git -e
winget install --id Docker.DockerDesktop -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Python.Python.3.12 -e
```

Then **launch Docker Desktop once** and wait for it to say "Engine running".
Use **Git Bash** (installed with Git) for every `make` command below — `make`
ships with it.

**macOS**

```bash
brew install git node python@3.12
brew install --cask docker      # then open Docker.app once and wait for it to start
# `make` comes with the Xcode command-line tools: xcode-select --install
```

**Debian / Ubuntu**

```bash
sudo apt update && sudo apt install -y git make python3 python3-pip curl
# Docker Engine + compose plugin:
curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker "$USER"   # log out/in after
# Node 24 via nvm:
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
. ~/.nvmrc 2>/dev/null; nvm install 24
```

**Verify all four before continuing** — each must print a version:

```bash
git --version                 # any recent
docker compose version        # any v2+ (the `docker compose` subcommand, not the old `docker-compose`)
node --version                # v20+ (v24 is what this was built on)
python --version              # 3.11+ on the host — only runs the setup/verify scripts;
                              # the app itself runs on 3.13 inside Docker
```

### Step 1 — get the code

```bash
git clone https://github.com/<your-user>/returnguard.git
cd returnguard
```

Everything from here runs **from this `returnguard/` folder** unless a step says
"in the `frontend/` folder".

### Step 2 — install the host-side Python packages

These are only for the setup + verification scripts (`httpx`, `psycopg`,
`websockets`, `PyJWT`). The app itself runs in Docker and needs nothing from your
host Python.

```bash
python -m pip install -r scripts/requirements.txt
```

*Worked if:* `pip` finishes with no red errors. (Optional: make a venv first —
`python -m venv .venv && . .venv/bin/activate` — then run the line above.)

### Step 3 — generate all the secrets

```bash
python scripts/gen_secrets.py
```

This writes **`.env`** and **`frontend/.env.local`** with fresh random values for
every generated credential (Postgres, MinIO, Keycloak admin, Langfuse, Bifrost,
ContextForge, Auth.js). It is safe to re-run — it only fills blanks, never
rotates a value that's already set.

*Worked if:* it prints `.env : 11 generated, …` and then lists **only**
`OPENAI_API_KEY` and `GROQ_API_KEY` as still blank.

### Step 4 — add your two paid API keys

Open **`.env`** in an editor and fill these two lines:

```
OPENAI_API_KEY=sk-...        # from https://platform.openai.com/api-keys
GROQ_API_KEY=gsk_...         # from https://console.groq.com/keys
```

Nothing else in `.env` needs touching. These are the only things that cost money;
budget a few US cents for a full `smoke.py` run.

### Step 5 — bring up the whole stack

```bash
make up
```

Builds + starts ~18 containers: Postgres, Redis, Qdrant, MinIO, MailHog, Vault,
Keycloak, Bifrost, ContextForge, the MCP tools server, OPA, Langfuse + its worker
+ ClickHouse, Prometheus, Grafana, the FastAPI backend, and the arq worker. It
runs a preflight check first (Docker running? ports free?) then blocks until
every container is healthy. (`make up-lite` skips Prometheus + Grafana.)

*Worked if:* the command ends with `all services healthy`. If it complains a port
is in use, stop whatever owns it (common: a local Postgres on 5432) and re-run.

### Step 6 — create the database schema

```bash
make migrate
```

Runs the Alembic migrations inside the backend container (this project never uses
`create_all` — every table is a real, ordered migration).

*Worked if:* the last line is an Alembic `Running upgrade … -> …, <name>` ending
at the current head with no traceback.

### Step 7 — load the seed data

```bash
make seed
```

Inserts 29 real products (with images pushed to MinIO) and the versioned
return-policy documents the Policy agent will search.

*Worked if:* it prints a count of products + policy docs written and exits 0.
Check: open http://localhost:3000 — the shop shows a product grid.

### Step 8 — one-time AI setup

```bash
make m4-setup
```

Runs six things in order, then restarts the worker to pick them all up:
generate the synthetic fraud dataset → train + register the scikit-learn risk
model → embed the policy docs into Qdrant → create one **ContextForge virtual
server per agent** (tool allow-list) → create one **Bifrost virtual key per
agent** (model allow-list + budget) → push the agent prompts to **Langfuse**
(versioned, UI-editable). ~2–3 min.

*Worked if:* it ends with `setup complete (dataset + model + policy index +
ContextForge + Bifrost VKs + prompts)`, with `pushed -> lf v1` for each of the
7 agent prompts just above it.

### Step 9 — start the shop + dashboard

The frontend runs on your host (not in Docker). It stays in the foreground, so
give it its own terminal.

```bash
cd frontend
npm install          # first time only, ~1 min
npm run dev
```

*Worked if:* it prints `Ready` / `Local: http://localhost:3000` and that page
loads. Leave this terminal running.

### Step 10 — prove it all works

Open a **second terminal**, back in the `returnguard/` folder:

```bash
python scripts/smoke.py
```

Runs every `verify_*` script and the scenario catalog against the live system —
it registers test customers, places real orders, submits real returns, drives the
full multi-agent pipeline, and checks the results against real Postgres / MinIO /
Langfuse / audit-chain state. ~8–10 min.

*Worked if:* the final `SMOKE SUMMARY` block is all `PASS` and the process exits
0. Now walk the [scenario catalog](docs/scenarios/README.md) — each file in
`docs/scenarios/` is a guided, click-through tour of one behaviour, meant to be
followed live in the running app (shop → dashboard → Langfuse/Grafana/MinIO),
no commands required.

---

### Logins, reset, and daily use

- **Dashboard logins** (Keycloak): `reviewer1@returnguard.local` / `reviewer1`
  and `admin1@returnguard.local` / `admin1`. Customers self-register at checkout.
- **Start completely over:** `make nuke` (deletes every volume), then re-run from
  Step 5.
- **Day to day:** `make down` stops the stack keeping data · `make up` brings it
  back · `make logs` tails everything · `make smoke` re-runs all verification.

---

## Every command, explained

`make` is the only entrypoint — one target per operation. Run `make help` for the
same list. `a="…"` passes arguments to a target; `m="…"` passes a message.

### Setup / lifecycle

| Command | What it does |
|---|---|
| `python scripts/gen_secrets.py` | Fill `.env` + `frontend/.env.local` with fresh random credentials. Idempotent — never rotates a value that is already set. |
| `make preflight` | Check Docker is running, the required ports are free, and there is enough disk. `make up` runs it first. |
| `make up` | Build images and start the whole stack (18 containers **incl.** Prometheus + Grafana), then block until every container is healthy. |
| `make up-lite` | Same as `make up` but skips the `observability` profile (no Prometheus/Grafana) — lighter on RAM. |
| `make migrate` | Apply the Alembic migrations inside the backend container. This project never uses `create_all`. |
| `make makemigration m="msg"` | Autogenerate a new Alembic migration from model changes. |
| `make seed` | Insert the 29 real products (photos pushed to MinIO) and the versioned return-policy documents. |
| `make m4-setup` | One-time AI wiring: `dataset` → `train` → `reembed-policy` → `mcp-setup` → `bifrost-setup` → `sync-prompts`, then restart the worker. |
| `make vault-init` | Re-run the Vault bootstrap (KV v2, per-service policies + AppRoles, load keys). |
| `make down` | Stop every container. Keeps all named volumes (data survives). |
| `make nuke` | Stop every container **and delete all volumes** — a completely clean slate. Re-run from `make up`. |
| `make logs` | Tail the logs of every container. |

### AI setup pieces (all rolled up by `make m4-setup`)

| Command | What it does |
|---|---|
| `make dataset` | Generate the synthetic fraud dataset (thousands of rows, injected rings + cohorts). |
| `make train` | Train + register the scikit-learn behaviour risk model; writes the model, its card, and metrics to `ml/registry/<version>/`. |
| `make reembed-policy` | Embed the active policy docs into the Qdrant vector collection (re-run after a policy edit). |
| `make mcp-setup` | Configure ContextForge: register the tools gateway and one per-agent virtual server (tool allow-list) each. |
| `make bifrost-setup` | Register one per-agent Bifrost virtual key (model allow-list + monthly budget + rate limit). |
| `make sync-prompts` | Push `worker/pipeline/prompts/*.md` to Langfuse as versioned, UI-editable prompts. |

### Verify / test

| Command | What it does |
|---|---|
| `make smoke` | Run every `scripts/verify_*.py` against the live system, in sequence. The full automated proof. ~10 min. |
| `make opa-test` | Run the OPA policy unit tests (`infra/opa/*_test.rego`). |
| `python scripts/verify_m1.py` … `verify_m6.py` | Individual milestone checks — stack health, shop+auth, single-agent pipe, full agent graph, reviewer workflow, docs. Run one directly instead of the whole `smoke`. |
| `python scripts/verify_audit_chain.py` | Re-walk the hash-chained `audit_log` and fail on any tamper. |
| `python scripts/verify_security.py` | Fire prompt-injection payloads with autonomy forced on; assert no privilege escalation, no auto-approve, a real decision row, a truthful audit entry. |
| `python scripts/loadtest.py` (`make loadtest`) | Push ~20× normal return volume through the queue and report p95; asserts no lost jobs. |
| [`docs/scenarios/README.md`](docs/scenarios/README.md) | The manual scenario catalog — click through the app, no commands. See "Scenario walkthroughs" below. |

### Operate / debug

| Command | What it does |
|---|---|
| `make replay a="<graph_run_id> <node>"` | Re-run **one** pipeline node for a past graph run in isolation, to debug it. |
| `make reprocess a="--since <date> --until <date> --policy-version <v>"` | Batch re-review a window of still-open returns (add `--dry-run` to preview). |
| `make backup` | Write `backups/<timestamp>/` — `pg_dump` + a Qdrant snapshot + a MinIO mirror. |
| `make restore` / `bash scripts/restore.sh backups/<timestamp>` | Restore Postgres + Qdrant + MinIO from a backup directory. |
| `cd frontend && npm run dev` | Start the Next.js shop + dashboard on the host (`http://localhost:3000`). Runs in the foreground. |
| `cd frontend && npm run gen:api` | Regenerate `frontend/lib/api/schema.ts` from the backend's OpenAPI schema (after an API shape change). |

---

## Local URLs

| URL | What |
|---|---|
| http://localhost:3000 | Shop + reviewer/admin dashboard |
| http://localhost:8000/docs | FastAPI OpenAPI docs |
| http://localhost:8081 | Keycloak (admin: `admin` / your `KEYCLOAK_ADMIN_PASSWORD`) |
| http://localhost:3001 | Langfuse — every agent call, cost, latency, I/O |
| http://localhost:6333/dashboard | Qdrant — the policy-doc vector collection |
| http://localhost:8090 | Bifrost — LLM gateway dashboard + `/metrics` |
| http://localhost:4444 | ContextForge — MCP gateway (JWT-gated API) |
| http://localhost:8181 | OPA — policy engine (`/v1/data/returnguard/...`) |
| http://localhost:9001 | MinIO console — return photos + product images |
| http://localhost:8025 | MailHog — order / return / decision emails |
| http://localhost:8200 | Vault (dev token: `root`) |
| http://localhost:9090 | Prometheus — backend + worker metrics |
| http://localhost:3002 | Grafana — provisioned agent-health dashboards (anon access on) |

---

## Operations

**Kill switch (stop autonomy now, no deploy).** Dashboard → Governance → tick
**kill switch** on the `global` row → Save (or `PUT /dashboard/governance
{"scope":"global","kill_switch":true}` as an admin). Effect is immediate — the
Governance Gate reads `feature_flags` per run, so the next case and every case
after routes to a human regardless of level. Untick to resume; consider dropping
`automation_level` to `shadow` while you investigate.

**Escalation backlog.** Bulk-claim + decide from the dashboard Queue. If the
backlog is *pipeline* throughput rather than *human* throughput, add workers:
`docker compose up -d --scale worker=3` — arq is a shared Redis queue, replicas
cooperate, and the atomic claim in `review_return` prevents double-processing.

**Dead-letter.** A `dead_letter` row means a case crashed 3× — it was
auto-escalated (a human will see it) but the root cause needs a look. Inspect it
by opening a `psql` shell inside the Postgres container and running a query —
the command below does both in one line, `-c` just means "run this SQL and
exit":
```bash
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
  "select * from dead_letter order by created_at desc;"
```
Also check the matching `agent_run_events` (kind `error`) the same way. Re-run
one case: `make replay a="<graph_run_id> <node>"` to debug a single node, or
re-queue the whole case the same `psql` way — this `update` puts it back in
`pending` with a reset attempt counter, and the `dispatch_outbox` cron
re-enqueues it within a few seconds:
```bash
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
  "update returns set status='pending', review_attempts=0 where id='<return-id>';"
```

**Policy change.** Dashboard → Policy → edit → Save writes a new `policy_docs`
version and enqueues a Qdrant re-embed. New cases pick it up automatically;
`agent_runs.policy_version` records which applied. Re-review still-pending cases
under the old policy: `make reprocess a="--since <date> --policy-version <new>"`.

**Key rotation.** Patch the secret inside Vault, then restart the two services
that actually read it — Vault needs its dev-mode root token passed explicitly
via `-e VAULT_TOKEN=root` (from your `.env`'s `VAULT_DEV_ROOT_TOKEN_ID`) or it
403s:
```bash
docker compose exec -T -e VAULT_TOKEN=root vault vault kv patch \
  secret/returnguard/llm openai_api_key=sk-...
# (or groq_api_key=... on the same line instead)
docker compose restart backend worker   # settings are cached per process
```
For generated DB / MinIO / Keycloak creds, edit `.env` and `make nuke` is the
clean path.

**Backup / restore.** `make backup` → `backups/<timestamp>/` (pg_dump + Qdrant
snapshot + MinIO mirror). `bash scripts/restore.sh backups/<timestamp>` restores.

## Security notes

- **Auth** — Auth.js + Keycloak (Auth Code + PKCE), token exchanged server-side
  only. FastAPI verifies the Keycloak JWT (JWKS) on every request; roles from
  `realm_access.roles`.
- **Per-agent identity + least privilege** — one Keycloak service account per
  agent ↔ a ContextForge virtual server exposing only that agent's tools ↔ a
  Bifrost virtual key capping models + spend; OPA (`infra/opa/authz.rego`) is
  asked before every tool/model call and fails closed. The Image agent is
  granted **zero** tools.
- **Uploads** — magic-byte sniff (`filetype`), 8 MB cap, Pillow re-encode to
  strip EXIF / trailing payload, per-object MinIO key, presigned GET only.
- **Rate limiting** — `slowapi`: a global per-IP cap at the edge plus stricter
  per-route caps on `POST /orders` and `POST /returns`.
- **Prompt injection** — customer free-text (and text baked into an uploaded
  image) is data, not instructions; no prompt can move `automation_level`, the
  thresholds, or the "auto-deny is impossible" rule. `scripts/verify_security.py`
  fires a blatant payload with autonomy forced on and asserts no auto-approve,
  a real decision row, escalation, and a truthful audit entry.
- **No money movement by an agent** — refunds are a human-only dashboard action;
  no MCP tool mutates payment or refund state.
- **Audit** — `audit_log` is append-only (a DB trigger blocks UPDATE/DELETE) and
  hash-chained; `scripts/verify_audit_chain.py` re-walks it.
- **Secrets** — Vault only; `structlog` redacts API-key/bearer/DB-URL shapes and
  any credential-looking log key.
- **Local-only scope** — dev-mode Vault/Keycloak, plain HTTP on localhost, no
  TLS. Not a production posture.

---

## Scenario walkthroughs

Every scenario is real — it places orders, submits returns, and drives the
actual multi-agent pipeline. Unlike the `verify_*.py` scripts, these are
**not automated** — each is a plain-English, click-through-the-app guide
meant to be walked through live, by hand, in front of an audience. Start at
[`docs/scenarios/00-watching-a-case-live.md`](docs/scenarios/00-watching-a-case-live.md)
(how to read the Live Trace, Langfuse, MinIO, Grafana, and the four real
alerts), then the index at
[`docs/scenarios/README.md`](docs/scenarios/README.md) lists all 18:

| # | Walkthrough | Route | What it shows |
|---|---|---|---|
| 01 | [Matching photo](docs/scenarios/01-matching-photo-auto-approve.md) | auto-approve | a clean case clears in seconds through a real CLIP match; a QA sample still queues |
| 02 | [Mismatched photo](docs/scenarios/02-mismatched-photo.md) | escalate | the photo is a claim to verify — an unverifiable one goes to a human |
| 03 | [AI-faked photo](docs/scenarios/03-ai-faked-damage-photo.md) | escalate | the AI-image detector is one signal, never a lone denial |
| 04 | [Ambiguous / worn item](docs/scenarios/04-ambiguous-worn-item.md) | escalate (proposed deny) | wear ≠ defect is a real policy rule, not a hardcoded check |
| 05 | [Serial returner](docs/scenarios/05-serial-returner.md) | escalate | the Behaviour agent scores the history, not just this transaction |
| 06 | [Fraud ring](docs/scenarios/06-fraud-ring.md) | escalate | shared-fingerprint accounts linked by the `flag_ring` MCP tool |
| 07 | [High value](docs/scenarios/07-high-value-within-policy.md) | escalate | big refunds always get a human, even at level `auto` |
| 08 | [Outside the window](docs/scenarios/08-outside-return-window.md) | escalate (proposed deny) | auto-deny is structurally impossible, even at 96% confidence |
| 09 | [Incomplete request](docs/scenarios/09-incomplete-request-data-quality.md) | escalate | the data-quality gate refuses to guess |
| 10 | [Prompt injection](docs/scenarios/10-prompt-injection.md) | escalate | customer text is data, not instructions; least privilege holds |
| 11 | [Kill switch](docs/scenarios/11-kill-switch.md) | escalate (all) | one admin switch overrides every automation level |
| 12 | [Automation ladder](docs/scenarios/12-automation-level-ladder.md) | varies | the same case at `shadow` / `suggest` / `assist` / `auto` |
| 13 | [Policy edit](docs/scenarios/13-policy-edit-changes-later-cases.md) | varies | an admin's edit takes effect immediately; old cases keep their old `policy_version` |
| 14 | [Request-info round trip](docs/scenarios/14-request-info-round-trip.md) | varies | a reviewer's question re-queues the case through the real pipeline |
| 15 | [Override + appeal](docs/scenarios/15-reviewer-override-and-appeal.md) | human decision | deny-with-confirm, a 409 on re-deciding, appeal routed away (COI), a 403 if the original reviewer tries |
| 16 | [Dead-letter](docs/scenarios/16-pipeline-crash-dead-letter.md) | escalate | 3 real crashes → auto-escalate, never an infinite retry |
| 17 | [Groq → OpenAI fallback](docs/scenarios/17-groq-outage-openai-fallback.md) | unaffected | a real Groq outage, a real decision still produced on OpenAI |
| 18 | [Volume spike](docs/scenarios/18-return-volume-spike.md) | unaffected | `make loadtest` — the queue holds, p95 measured, nothing lost |

---

## Contributing

- After editing an agent prompt: bump its `version:` header, then
  `make sync-prompts` (pushes the new version to Langfuse).
- After changing the API shape: `cd frontend && npm run gen:api` (regenerates
  `frontend/lib/api/schema.ts`; the frontend types come straight from it).
- Policy lives in `infra/opa/*.rego` with its own unit tests: `make opa-test`.
- `make replay a="<graph_run_id> <node>"` re-runs one pipeline node in isolation;
  `make reprocess a="--since <date> --dry-run"` batch-re-reviews open returns.

There is **no** pytest / Playwright / eval harness by design; automated
verification is `scripts/verify_*.py` (`make smoke` runs all of it), and the
18 scenario walkthroughs above are the manual, human-run complement — each
one was itself run for real against the live system while it was written.

---

## What `make smoke` proves (10 checks, all green)

| Check | What it proves against the live system |
|---|---|
| `verify_m1` | 18-service stack healthy; `/health/deep` really talks to Postgres/Redis/Qdrant/MinIO/Vault/Bifrost/ContextForge/OPA; alembic at head |
| `verify_m2` + `_frontend` | register via Keycloak → order → return with a real photo → rows in Postgres + object in MinIO; Next.js shop + Auth.js/Keycloak PKCE |
| `verify_m3` + `_dlq` | a real Groq call via Bifrost → `agent_runs` with real tokens/cost/latency = API = DB; a real Langfuse trace; WS replay; 3 real crashes → `dead_letter` + auto-escalate, never an infinite retry |
| `verify_m4` | the full agent graph: every node writes `agent_runs`; Policy does a real Qdrant retrieval; Behavior loads the registered model; `intake`/`policy`/`behavior` call their MCP tools **through ContextForge** (`ok=true` + `call_tool` audit rows); the Image agent's virtual server exposes **zero** tools; GovernanceGate decides **via OPA**; hash chain valid; no auto-deny |
| `verify_audit_chain` | every `row_hash` recomputes; the chain is unbroken |
| `verify_security` | injection via return text + text-in-image → no privilege escalation, no auto-approve; OPA denies the Image agent every tool + the `reason` model role; `slowapi` rate limiting wired; no money-mutating tool |
| `verify_m5` | reviewer claim → deny-with-confirm → audit chain extended → override logged in `agreement_samples` → `assist` auto-approve path → request-info round trip → refund settlement (`process_refunds` → `refunded` + audit row) |
| `verify_m6` | this README has every section + working URL; every `make` target / script exists; all 18 `docs/scenarios/*.md` walkthroughs have their expected sections |
