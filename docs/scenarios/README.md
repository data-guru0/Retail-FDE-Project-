# ReturnGuard — Scenario Catalog

This is the single source of truth for how ReturnGuard behaves in every
situation it's meant to handle. It is **not** a metric harness — there's no
accuracy/precision/recall score, no labelled test file, no regression gate,
and deliberately **no automation script**. Every walkthrough below is a real,
click-through-the-app guide: place a real order in the shop, submit a real
return, watch the reviewer dashboard and the live agent trace, and see the
resulting decision, the Langfuse/Grafana metrics, the MinIO object, and (where
relevant) the alert it would fire.

Each walkthrough was run for real against the live system while it was
written, and quotes the actual real numbers and real model output from that
run — LLM wording varies a little run to run, so treat the exact sentences
as "what a real run said," not a script your run must match word for word.
What should match every time is the **decision, the route, and which agents
fired**.

**Start here:** [00 — Watching a case live](00-watching-a-case-live.md)
explains the five places you can observe a case (Live Trace, Langfuse, MinIO,
Grafana, the four real alerts) once — every walkthrough after it assumes
you've read it.

## The walkthroughs

### Decision behaviour — what the agents do with one case

| # | Scenario | Route | |
|---|---|---|---|
| [01](01-matching-photo-auto-approve.md) | Matching photo, established customer | **auto-approve** | [demo] |
| [02](02-mismatched-photo.md) | Mismatched photo | escalate | [demo] |
| [03](03-ai-faked-damage-photo.md) | AI-generated damage photo | escalate | [demo] |
| [04](04-ambiguous-worn-item.md) | Ambiguous / worn item | escalate (proposed deny) | |
| [05](05-serial-returner.md) | Serial returner | escalate | [demo] |
| [06](06-fraud-ring.md) | Fraud ring (shared fingerprint) | escalate | [demo] |
| [07](07-high-value-within-policy.md) | High value, within policy | escalate | |
| [08](08-outside-return-window.md) | Outside the return window | escalate (proposed deny) | |
| [09](09-incomplete-request-data-quality.md) | Incomplete request (data-quality gate) | escalate | |
| [10](10-prompt-injection.md) | Prompt injection in the return reason | escalate | [demo] |

### Governance controls — what an admin or reviewer can do

| # | Scenario | Route | |
|---|---|---|---|
| [11](11-kill-switch.md) | Kill switch on | escalate (every case) | [demo] |
| [12](12-automation-level-ladder.md) | Automation ladder: shadow → suggest → assist → auto | varies by level | [demo] |
| [13](13-policy-edit-changes-later-cases.md) | Admin edits policy → later cases use it | varies | |
| [14](14-request-info-round-trip.md) | Reviewer requests info → customer answers → re-decided | varies | |
| [15](15-reviewer-override-and-appeal.md) | Reviewer denies → customer appeals → a different reviewer decides (COI guard) | human decision | [demo] |

### Operational — how the system behaves under stress or failure

| # | Scenario | Route | |
|---|---|---|---|
| [16](16-pipeline-crash-dead-letter.md) | A case crashes the pipeline 3× → dead-letter → auto-escalate | escalate | |
| [17](17-groq-outage-openai-fallback.md) | Groq goes down → falls back to OpenAI | unaffected | |
| [18](18-return-volume-spike.md) | A volume spike → the queue holds | unaffected | |

## Running a demo session

A subset is marked **[demo]** — walk those nine (01, 02, 03, 05, 06, 10, 11,
12, 15) when showing the project live and short on time. For a full
teaching session, walk all 18 in order: they build on each other, starting
from the clean baseline (01) and layering in each way a real request can go
wrong, each governance control, and each operational failure mode.

There is nothing to run beforehand beyond the stack itself being up
(`make up`, `make migrate`, `make seed`, `make m4-setup` — see the
[README](../../README.md)). Every walkthrough tells you exactly what to click.
