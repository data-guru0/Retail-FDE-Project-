# Scenario 14 — Reviewer requests more information → customer answers → re-decided

**Route:** varies · **Group:** governance controls

See [00 — Watching a case live](00-watching-a-case-live.md) first.

## What this shows

A reviewer doesn't have to choose between approving on incomplete information
and denying outright — they can ask the customer a specific question, and the
case genuinely goes back through the full pipeline once an answer arrives,
with the new information available to every agent.

## Walkthrough (both roles)

**As a customer:** buy **Nimbus Wireless Headphones ($149.99)**, file a return
reason **defective**, describing a vague fault, with a real photo. Wait for
it to escalate.

**As a reviewer** (`reviewer1@returnguard.local` / `reviewer1`): claim the
case, type a specific question into the decision note — e.g. "Can you confirm
which earbud has the issue and when it started?" — and click **Request info
from customer** (this button only enables once you've typed something in the
note). The case's status flips to **info requested**, and the customer gets
an email.

**Back as the customer:** open `/returns/<id>` — a box reading **"The
reviewer has a question:"** shows the exact question above your case status.
Type a real answer and click **"Send answer — this re-opens the review."**

## What happens behind the scenes

Real result from a live run:

| Step | Real result |
|---|---|
| Reviewer asks | `info_requests` row inserted; `returns.status` → `info_requested` |
| Customer answers | the answer is saved, `returns.status` → `pending`, `review_attempts` reset to 0, and the case is **re-enqueued through `enqueue_review`** — the exact same entry point as a brand-new submission |
| Second pipeline pass | the full graph runs again — `data_quality`, `planner`, `intake`, `policy`, `image`, `behavior`, `decision`, `critic`, `explanation`, `governance` all fire a second time, each producing a **new** `agent_runs` row |
| What's different this time | every agent's context now includes a `customer_clarification` fact: the original question *and* the customer's actual answer — visible directly in the second pass's prompts |

In our real run the case still escalated on the second pass (the demo photo
didn't actually match a pair of headphones) — answering a question is new
information for the agents to weigh, not a guaranteed path to approval, which
is exactly the honest behavior you want here.

## In the reviewer dashboard

The case detail page grows an **Info requests** section above Agent
reasoning: your question tagged **"asked"** (blue), and once answered, the
customer's reply tagged **"answered"** (green) right underneath it —
unanswered questions stay tagged **"waiting on customer"** (amber) instead.
Scroll down to **Agent reasoning** and you'll see *two* full sets of agent
rows now — the original pass and the re-queued one — both permanently on the
record.

## Watch it live

- **Live Trace:** watch a full second `pipeline_start` → ... → `pipeline_end`
  sequence appear after you answer — the case doesn't just quietly update, it
  genuinely runs again.
- **Audit log:** the `request_info` action and the reviewer's exact question
  are both in the append-only audit trail, alongside every other action taken
  on this case.

## Why it matters

"I don't have enough information" is a legitimate reviewer answer that
shouldn't force a premature approve or deny. Routing it back through the real
pipeline — rather than letting the reviewer just privately decide off the
new fact — keeps every agent's view of the case consistent and keeps the full
reasoning, both before and after the answer, in the same permanent record.
