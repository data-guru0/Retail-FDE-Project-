# Watching a case live — read this first

Every walkthrough after this one follows the same shape: you act as a customer
in the shop, then switch hats and act as a reviewer in the dashboard. This page
explains the five places you can *watch* a case while that happens, so the
other 18 walkthroughs don't have to repeat it. Skim it once, then jump into
[the index](README.md).

Nothing below is a simulation. Every screen pulls from the same live Postgres
rows, the same real MinIO objects, and the same real LLM calls the other
walkthroughs produce.

## 1. The Live Trace panel (the fastest one)

Open any case at `http://localhost:3000/dashboard/<id>` and look at the
right-hand column, under **Live trace**. This is a raw WebSocket
(`ws://localhost:8000/ws/returns/<id>`) streaming every pipeline event the
moment it happens — if the pipeline is still running when you open the page,
you'll watch it finish in real time.

Each row shows `<agent name> · <event kind>` with the event's raw JSON payload
underneath. The kinds you'll see, in roughly this order for a typical case:

| Kind | Color | What it means |
|---|---|---|
| `pipeline_start` | green | the graph run began; payload shows the automation level and try count |
| `node_start` | blue | one agent node began working |
| `tool_call` | amber | an agent called a governed MCP tool (`get_order`, `check_policy`, `get_customer_history`, `flag_ring`) through ContextForge |
| `rag` | (default) | the Policy agent's Qdrant retrieval — which policy documents it pulled back |
| `node_end` | blue | one agent node finished; payload has its output |
| `pipeline_end` | green | the graph run finished; payload has the final route |

Several agents run in parallel (intake, policy, image, and behavior don't
depend on each other), so rows can arrive out of the order you'd read the
agent-by-agent table in each walkthrough — that's real concurrency, not a bug.

Below the Live Trace, the **Agent reasoning** section on the same page shows
one collapsible row per agent that actually ran, with its model name,
confidence, cost, and latency already computed — click one open to see its
full parsed output.

## 2. Langfuse — the trace with cost and tokens attached

`http://localhost:3001` — log in as `admin@returnguard.local` with the
`KEYCLOAK_ADMIN_PASSWORD` value from your `.env`. Every LLM call (every agent
except `data_quality`, `image`'s CLIP/detector pass, and `behavior`'s
scikit-learn pass, which are all local and free) writes a **generation** here
with its exact prompt, completion, token counts, cost, and latency. The
dashboard's case-detail page shows the same numbers per agent, but Langfuse is
where you see the literal prompt text that was sent, prompt version included.

Each `agent_runs` row carries a `langfuse_trace_id` — the dashboard doesn't
link to it directly today, so the fastest path is Langfuse's own **Traces**
list sorted by time, which lines right up with when you just submitted the
case.

## 3. MinIO — where the photo really lives

`http://localhost:9001` — log in with `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`
from your `.env`. Open the **returnguard** bucket, then **returns/**, then the
folder named after the case's id — the photo is in there, renamed to a random
id (not your original filename) and re-encoded by Pillow to strip any EXIF
data or hidden payload before it was ever written. Product catalog photos live
the same way, one level up, under **products/**.

Every walkthrough that involves a photo will tell you the exact key
(`returns/<id>/<file>.jpg`); this is the mechanism behind all of them.

## 4. Grafana and Prometheus — the fleet view

`http://localhost:3002` (Grafana, no login needed) has one provisioned
dashboard, **ReturnGuard**, refreshing every 10 seconds:

- **Pipeline runs by route** — a live rate of auto-approve / escalate / deny-proposed, split out
- **Errors & dead-letters** — should sit at zero outside scenario 16
- **LLM spend (USD, total)** and **last 24h** — the real running cost of every case you've submitted today
- **Agent↔human agreement (30d)** — a gauge fed by the Analytics page's same query
- **Oldest undecided escalation (s)** — how long the longest-waiting case in the queue has been sitting there
- **Time-to-decision p50/p95** — the same number the load-test scenario prints, live
- **API request rate by path**

`http://localhost:9090` (Prometheus) is the raw metric store behind that
dashboard — useful if you want to run your own query, e.g.
`rg_llm_cost_usd_total`.

## 5. The four real alerts

`infra/prometheus/alerts.yml` defines four rules, loaded into Prometheus right
now (`http://localhost:9090/alerts` shows their live state):

| Alert | Fires when | What it's protecting against |
|---|---|---|
| `QueueSLABreach` | `rg_queue_oldest_seconds > 3600` for 5m | a case has waited over an hour for a human — reviewer capacity problem |
| `DailyCostCeiling` | 24h LLM spend `> $20` | a runaway loop or a spike in volume is burning API budget |
| `PipelineErrorSpike` | pipeline error rate `> 0.2/s` for 10m | something is systematically breaking the graph (see scenario 16) |
| `AgreementDrift` | agent↔human agreement `< 80%` for 30m | the agents are drifting away from what reviewers actually decide — a signal to freeze the automation level, not raise it |

These are real Prometheus alerting rules with real `for:` windows, not
decorative text — they will not fire instantly just because a threshold is
crossed for one scrape, exactly like a real on-call setup. Scenario 16 (dead-
letter) is the one walkthrough that pushes `PipelineErrorSpike` toward firing
for real; the other three are explained where they're most relevant, but
firing `DailyCostCeiling` or `AgreementDrift` for real would mean deliberately
running the stack for hours or burning real API spend, so those two are shown
by reading the live Grafana panel and the rule definition rather than forcing
the threshold.

## 6. The Analytics page

`http://localhost:3000/dashboard/analytics` (reviewer or admin) is the plain-
English rollup of all of the above, computed by real SQL against the same
tables: hours/dollars saved vs. an all-human baseline, cost per decision, the
agent health table (runs, latency, confidence, cost, errors per agent), the
agreement trend, and any shared-fingerprint ring the Behaviour agent has ever
flagged. Every walkthrough moves these numbers a little; scenario walkthroughs
call out only the row that's most relevant to them.

---

Ready? Start at [the index](README.md), or jump straight to
[01 — Matching photo](01-matching-photo-auto-approve.md).
