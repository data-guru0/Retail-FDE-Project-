# Scenario 09 — Incomplete request → the data-quality gate → escalate

**Route:** escalate ("insufficient data") · **Group:** decision behaviour

See [00 — Watching a case live](00-watching-a-case-live.md) first.

## What this shows

The pipeline refuses to guess. When there genuinely isn't enough to judge a
case on, it stops immediately and asks a human — instead of asking an LLM to
produce a confident-sounding answer from thin evidence.

## Part A — the shop itself won't let you submit without a photo

Open the return wizard for any order (**My orders** → **Return this**) and
pick reason **Damaged**, **Defective**, **Not as described**, or **Wrong
item** — Step 3 (**Upload a photo of the item (required)**) won't let you
click **Submit return** without a file chosen; if you somehow bypass the UI
and post directly to the API without one, the server rejects it before
anything is even stored — the return never has a chance to exist half-formed.
This is the earliest possible refusal: no agent, no cost, no delay.

## Part B — a product the Image agent can't compare against

This is a rarer, real operational case: a catalog product whose reference data
is missing (a data-entry gap, a partially-migrated SKU). It's staged for the
demo, but the pipeline's response to it is completely real.

1. **As an admin (not part of this walkthrough's normal flow):** briefly clear
   one product's description in the database to simulate the gap — this is
   the one walkthrough where "the setup" is an operator error, not something
   you do through the shop UI.
2. **As a customer:** buy that product, then file a return with reason
   **Damaged**, a note, and a real photo — everything a customer does looks
   completely normal from their side.

## What happens behind the scenes

Real result from a live run:

| Agent | What it does here | What you see |
|---|---|---|
| **data_quality** | checks: is there an order item? does this reason need a photo, and is one present? is there reference product data to compare against? | `ok: false`, `reason: "no reference product data"` |
| — | **everything else is skipped** — no planner, no intake, no policy, no image, no behavior, no decision, no critic, no explanation | `agent_runs` for this case has exactly two rows: `data_quality` and `governance` |
| **GovernanceGate** | reads `dq_ok = false` | **`escalate`** — *"data-quality gate failed: no reference product data"*. No LLM was ever asked to decide. |

## In the reviewer dashboard

The case looks unusually thin compared to every other escalation — the Agent
reasoning section has only two entries instead of the usual eight or nine. The
Live Trace is correspondingly short: `pipeline_start` → `data_quality`
`node_end` → `governance` `node_end` → `pipeline_end`, nothing in between.
That thinness *is* the signal to a reviewer: this isn't "the agents disagreed
about a hard case," it's "the agents never got a case worth deciding."

## Watch it live

- **Langfuse:** zero generations for this case — the entire gate is a rule,
  not a model call, so there's nothing to trace there. Compare the **LLM
  spend** stat on Grafana before and after: it doesn't move for this case at
  all.
- **Live Trace:** the shortest trace you'll see across every walkthrough —
  good for showing a class the contrast against, say,
  [scenario 06](06-fraud-ring.md)'s much longer one.

## Why it matters

"Escalate because I don't have enough to go on" is a *correct* answer, and
it's cheaper than a wrong one — no tokens spent, no model asked to rationalize
a guess. A system that always produces a confident-sounding decision is a
system that will eventually produce a confidently wrong one when the inputs
are simply too thin to judge.
