# Scenario 18 — A volume spike → the queue holds, nothing is lost

**Route:** unaffected (every case still decided) · **Group:** operational

See [00 — Watching a case live](00-watching-a-case-live.md) first.

## What this shows

A burst of returns — a bad shipping day, a product recall, a sale gone wrong
— doesn't drop jobs, doesn't corrupt state, and degrades gracefully into a
longer queue instead of a crash. This is the one walkthrough that's a genuine
load test rather than a single case, so it uses one existing command instead
of the shop UI: `make loadtest` (`scripts/loadtest.py`), which fires many
real returns concurrently, waits for each to reach a real final state, and
reports real p50/p95 time-to-decision.

## Walkthrough

```
make loadtest          # ~20x normal volume, concurrency 4 by default
```

or a smaller run to see the mechanism faster: `python scripts/loadtest.py
--factor 8 --concurrency 4`.

## What happens behind the scenes

Real numbers from a live run (`--factor 8 --concurrency 4`, one worker
replica, the same live stack every other walkthrough used today):

| Metric | Real result |
|---|---|
| Returns submitted | 8, concurrently |
| Completed | **8 / 8** — zero lost jobs |
| Wall time | 82s |
| Time-to-decision p50 | 32.8s |
| Time-to-decision p95 | 38.8s |
| Throughput | ~5.8 decisions/min, one worker |

Nothing crashed and nothing silently disappeared — every one of the 8 real
returns produced a full real agent graph run and a real final `returns` row.
The **outbox pattern** (`returns.submitted` written in the same transaction as
the return itself, a durability backstop `dispatch_outbox` cron re-enqueues
from) is what guarantees "no lost jobs" specifically — even a burst large
enough to make the `arq` queue back up can't drop a submission.

## Scaling it

The lever is worker replicas, not code changes:
```
docker compose up -d --scale worker=3
```
`arq`'s shared Redis queue lets replicas cooperate safely — the atomic claim
inside `review_return` (`SELECT ... FOR UPDATE`) prevents two workers from
double-processing the same case.

## In the reviewer dashboard

During a real spike, the escalated queue simply grows — same table, same
columns, same claim button, just more rows and a rising **Age** column until
reviewers (or auto-approvals) work through it.

## Watch it live

- **Grafana → Time-to-decision p50/p95:** the same numbers `loadtest.py`
  printed, live, as the burst is still draining.
- **Grafana → Oldest undecided escalation (s):** climbs during the burst —
  this is the exact metric behind the real `QueueSLABreach` alert
  (`rg_queue_oldest_seconds > 3600`, held 5 minutes). A load test this size
  won't come close to tripping it — the alert is calibrated for "a case has
  waited over an hour," not "the queue is momentarily busy" — but it's the
  same number, and worth pointing at live during the burst to explain what
  *would* eventually fire it: reviewer capacity falling behind sustained
  volume, not a brief spike.
- **`make reprocess`** and **`make replay`** are the operator tools for
  working through a backlog or investigating one case afterward — not part of
  this demo, but the natural next step after a real spike.

## Why it matters

Systems fail under load in the boring, predictable way (queue backs up,
p95 climbs) far more often than in dramatic ones — and boring failure modes
are the ones worth actually measuring instead of assuming away. A real number
for "how long does a case wait at 8x volume with one worker" is what tells
you whether to add workers, adjust reviewer staffing, or do nothing at all.
