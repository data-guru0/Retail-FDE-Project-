# Scenario 16 — A case crashes the pipeline 3× → dead-letter → auto-escalate

**Route:** escalate (auto, after 3 real failures) · **Group:** operational

See [00 — Watching a case live](00-watching-a-case-live.md) first — this is
the one walkthrough that pushes the real `PipelineErrorSpike` alert toward
firing.

## What this shows

Software breaks. When a case's pipeline run genuinely crashes — not a bad
LLM answer, an actual exception — the system retries a bounded number of
times, then gives up loudly and safely: the case is auto-escalated to a
human and the crash is recorded, instead of being silently retried forever or
silently dropped.

## This one needs an operator action, not just a customer click

Unlike every other walkthrough, you can't make a real exception happen by
filling out a form correctly — you have to actually break something, the way
an SRE rehearsing an incident would. The worker has a real, documented
fault-injection switch for exactly this purpose (`RG_PIPELINE_FORCE_ERROR`,
`worker/pipeline/nodes/agents.py`) — it isn't a special "test mode," it's a
single environment variable that makes `review_return` raise a real exception
after claiming a case, so the retry → dead-letter → escalate path gets
genuinely exercised, then you turn it back off.

## Walkthrough (as an operator, then as a customer)

1. In a terminal, at the repo root, create a tiny override file that adds the
   fault-injection variable to the worker's environment — `docker compose up`
   doesn't take an inline `-e VAR=value` flag the way `exec`/`run` do, so this
   is the actual way to set one:
   ```bash
   cat > docker-compose.faulttest.yml << 'EOF'
   services:
     worker:
       environment:
         RG_PIPELINE_FORCE_ERROR: "1"
   EOF
   ```
2. Recreate just the worker with that file layered on top — this restarts
   only the worker container, with the fault switch now on:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.override.yml \
     -f docker-compose.faulttest.yml up -d --force-recreate worker
   ```
3. As a customer, submit any return normally.
4. Watch it fail 3× (see the table below), then delete the override file and
   recreate the worker again — with no `-f docker-compose.faulttest.yml` on
   the command, Compose rebuilds the worker's environment from just the base
   files, so the fault switch is gone:
   ```bash
   rm docker-compose.faulttest.yml
   docker compose up -d --force-recreate worker
   ```

## What happens behind the scenes

Real result from a live run:

| Step | Real result |
|---|---|
| Attempt 1 | `review_return` claims the case, raises a real exception |
| Attempt 2, 3 | same — three genuine failed attempts, not a simulated count |
| After the 3rd failure | a `dead_letter` row is written: `attempts = 3` |
| The case itself | `returns.status = escalated` — auto-escalated, not stuck |
| Trace | exactly one `agent_run_events` row with `kind = 'dead_letter'` |
| Never happens | an infinite retry loop, or a silently dropped case |

## In the reviewer dashboard

The case appears in the escalated queue looking almost like a data-quality
case — very little in Agent reasoning, because the graph never got past its
first node before crashing each time. The real tell is in the raw data: a
reviewer (or an admin) querying `dead_letter` directly sees exactly which
case failed and how many times.

## Watch it live

- **Grafana → Errors & dead-letters (rate/5m):** this is the one panel that
  actually moves during this walkthrough — both the pipeline error rate and
  the dead-letter rate spike for the ~30–60 seconds this takes.
- **The real alert this feeds:** `PipelineErrorSpike` — `rate(rg_pipeline_errors_total[10m]) > 0.2`,
  held for 10 minutes, severity `critical`. A single manual demo run like this
  one is real error volume, but brief; sustaining the fault-injection flag for
  the full 10-minute window is what would actually flip the alert from
  "pending" to "firing" on `http://localhost:9090/alerts` — worth pointing a
  class at that page and explaining the `for:` window is deliberately not
  instant, exactly like a real on-call alert wouldn't page on one blip.
- **Debugging the root cause for real:** `make replay a="<graph_run_id>
  <node>"` re-runs one node of a past graph run in isolation — the actual tool
  an engineer would reach for after seeing a `dead_letter` row, not part of
  this demo but worth mentioning.

## Why it matters

A retry with no ceiling is an outage waiting to happen (a poison-pill case
that keeps a worker busy forever); a system that fails silently loses a
customer's return with no trace. Three bounded attempts, then a loud,
auditable, auto-escalated failure is the version of "fail safe" that keeps a
human in the loop for the one class of problem the agents themselves can't
reason their way out of: their own crash.
