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
| Shop + dashboard | Next.js 16 (App Router), Auth.js + Keycloak (OIDC + PKCE) |
| API + WebSocket | FastAPI (Python 3.13, Docker), SQLAlchemy 2 async, Alembic |
| Worker | `arq` on Redis; **LangGraph** pipeline with a Postgres checkpointer |
| LLM gateway | **Bifrost** — one endpoint for Groq + OpenAI, fallback chains, per-agent virtual keys, cost/latency telemetry |
| MCP governance | **IBM ContextForge** in front of a plain MCP tools server — one virtual server per agent, exposing only that agent's tools |
| Vector store | Qdrant (return-policy RAG) |
| Local ML | scikit-learn risk model; open-clip CLIP; an AI-image detector — all CPU |
| Observability | **Langfuse v3** (self-hosted, shares Postgres/Redis/MinIO, + ClickHouse) |
| Identity | Keycloak — `customer` / `reviewer` / `admin`, plus one service account per agent |
| Storage / email / secrets | MinIO / MailHog / **HashiCorp Vault** (every runtime secret) |

Architecture detail: `docs/ARCHITECTURE.md`. Every real design choice has an ADR
in `docs/decisions/`.

---

## Run it from a clean checkout

**Prerequisites:** Docker Desktop (running), Node 24+, Python 3.11+ on the host,
`make`. ~9 GB RAM free for the full stack.

```bash
pip install -r scripts/requirements.txt   # host deps for the verify/setup scripts
```

```bash
# 1. secrets — copy the template and fill in the two API keys + any strong
#    random strings for the generated-credential fields
cp .env.example .env
#    edit .env: set OPENAI_API_KEY, GROQ_API_KEY, and the POSTGRES_PASSWORD /
#    MINIO_ROOT_PASSWORD / KEYCLOAK_ADMIN_PASSWORD / LANGFUSE_* / NEXTAUTH_SECRET
#    / CONTEXTFORGE_JWT_SECRET / BIFROST_ADMIN_TOKEN fields to random values.

# 2. bring up the whole stack (Postgres, Redis, Qdrant, MinIO, MailHog, Vault,
#    Keycloak, Bifrost, ContextForge, mcp-server, Langfuse + ClickHouse,
#    backend, worker). First run pulls images + builds — several minutes.
make up

# 3. database schema + seed data (29 real products + return-policy docs)
make migrate
make seed

# 4. one-time M4 setup: synthetic dataset, train + register the risk model,
#    embed the policy docs into Qdrant
make m4-setup

# 5. gateways: ContextForge per-agent tool servers + Bifrost per-agent model keys
#    (also run by `make m4-setup` above)
python scripts/mcp_setup.py
python scripts/bifrost_setup.py

# 6. frontend (runs on the host, not in Docker)
cd frontend && npm install && npm run dev      # http://localhost:3000

# 7. prove it works
python scripts/smoke.py
```

Seeded logins (Keycloak): `reviewer1@returnguard.local` / `reviewer1`,
`admin1@returnguard.local` / `admin1`. Customers self-register in the shop.

Verify from nothing: `make nuke` (deletes volumes) then repeat from step 2.

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
| http://localhost:9001 | MinIO console — return photos + product images |
| http://localhost:8025 | MailHog — order / return / decision emails |
| http://localhost:8200 | Vault (dev token: `root`) |
| http://localhost:9090 / :3002 | Prometheus / Grafana (with `--profile observability`) |

---

## Demo scenarios

Each is real, runs through the actual pipeline, and behaves exactly as
`docs/SCENARIOS.md` documents. The automatable ones:

```bash
python scripts/run_scenarios.py          # all
python scripts/run_scenarios.py A2 A5    # named
```

1. **Easy case** — a return within policy with a matching photo. Auto-approves in
   seconds at `assist`/`auto`. *Why it matters: autonomy is safe when it's bounded.*
2. **Mismatched photo** — the return photo isn't the product. The Image agent's
   similarity score drops, the case escalates. *Why: evidence is checked, not trusted.*
3. **AI-faked damage photo** — an AI-generated photo. The detector flags it as
   one signal → escalate, never a lone denial. *Why: one model's opinion is never the verdict.*
4. **Serial returner** — a high-return-history account; the Behaviour agent flags
   the pattern even when one return looks fine alone. *Why: context beats the single case.*
5. **Fraud ring** — two accounts sharing an address; flagged together. *Why:
   fraud is a graph, not a row.*
6. **The appeal** — a denied return, contested, routed to a *different* reviewer
   (conflict-of-interest guard). *Why: fairness needs a fresh pair of eyes.*
7. **Watching an agent think** — open a case in the dashboard as it runs; the
   live trace fills in node by node with real tokens/cost/latency. *Why:
   observability is not an afterthought.*
8. **The rollout story** — the same easy case in `shadow` (agent decides, human
   acts, agreement logged) vs `assist` (auto-approved), with the agreement trend
   and the vs-baseline numbers that justify moving up. *Why: trust is earned, not toggled.*

---

## Troubleshooting (things that actually went wrong building this)

- **Postgres 18 won't start, "unused mount/volume".** pg18 changed the data-dir
  convention — the volume mounts at `/var/lib/postgresql`, not `/…/data`. Already
  fixed in `docker-compose.yml`; if you have an old volume, `make nuke`.
- **`arq` dependency conflict.** `arq` requires `redis<6`; the worker and backend
  pin `redis==5.3.1`.
- **Keycloak tokens have no `sub` claim.** Keycloak 26 only includes `sub` when
  the `basic` client scope is assigned — it's in the realm export.
- **MinIO presigned URL returns XML / SignatureDoesNotMatch.** The presign must be
  computed against the browser-reachable host (`localhost:9000`), not the docker
  hostname, or the SigV4 signature won't match. `app/services/storage.py` uses a
  separate client for presigning.
- **Bifrost: "provider groq not found".** Bifrost v2 reads `config.json` from
  `/app/data/`, not a `BIFROST_CONFIG_PATH`. And Groq's 2026 catalog dropped the
  `llama-3.x` ids — the model roles now map to `openai/gpt-oss-*` (ADR-0010).
- **ContextForge "Unable to connect to gateway" (502).** The MCP SDK v2 streamable
  server rejects unknown `Host` headers; `mcp-server/server.py` passes
  `TransportSecuritySettings(allowed_hosts=[...])`.
- **Worker: "at least one function must be registered" even though there is one.**
  `pip install .` had baked a stale copy of the package into site-packages that
  shadowed the bind-mounted source — the Dockerfiles use `pip install -e .`.
- **First pipeline run is slow (~2 min).** CLIP + the AI-image detector download
  on first use, then stay resident.

---

See `STATUS.md` for exactly what is verified and what is still partial.
