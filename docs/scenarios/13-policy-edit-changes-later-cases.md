# Scenario 13 — An admin edits policy → later cases use the new rule

**Route:** varies · **Group:** governance controls

See [00 — Watching a case live](00-watching-a-case-live.md) first.

## What this shows

The return policy isn't a hardcoded rule buried in Python — it's a real,
versioned document an admin can edit from the dashboard, and every future case
picks up the new wording automatically, while every past case still shows
which version it was actually decided under.

## Walkthrough (as an admin, then as a customer)

1. Log in as `admin1@returnguard.local` / `admin1`, go to **Policy editor**.
   Note the **current version** number at the top.
2. Find the **return-window** document and edit its body — for this
   walkthrough, change "30 days" to "45 days" — then click **Save new version
   + re-embed**. A toast confirms: **"saved as version `<N+1>`, re-embed
   `queued`."**
3. As a customer, buy any product, then have an admin (or the demo data)
   backdate that order to 38 days old — inside the *new* 45-day window, but
   outside the *old* 30-day one — and file a return, reason **no longer
   needed**.

## What happens behind the scenes

Real numbers from a live run:

| Step | Real result |
|---|---|
| Policy edit | `return-window` version bumped from **1 → 2**; response: `{"new_version": 2, "reembed": "queued"}` |
| Re-embed | the worker's `reembed_policy` job re-embeds the new text into Qdrant within seconds — no restart needed |
| **policy** agent on the new case (order 38 days old) | `eligible: "yes"` — *"the item is within the 45‑day standard return window (38 days) and Home & Kitchen items are not listed among the category exceptions"* |
| `agent_runs.policy_version` for this case | **2** — recorded permanently against this exact decision |

The same 38-day-old order would have read `eligible: "no"` under version 1
(see [scenario 08](08-outside-return-window.md), which used the *old* wording
at 75 days out). Nothing about the code changed between the two — only the
document version each case happened to run against.

## In the reviewer dashboard

Open any case decided before the edit and any case decided after it — the
**Policy agent's** row in Agent reasoning shows a **`policy v1`** or
**`policy v2`** chip either way. That chip is the permanent record of which
rule text actually governed that specific decision, even if the document is
edited again next week.

## Watch it live

- **Dashboard → Policy editor:** the version number at the top only ever goes
  up — editing never overwrites the old text, it adds a new version and
  deactivates the old one.
- **Live Trace → `policy` node's `rag` event:** shows which document slugs
  were retrieved from Qdrant for this specific case — confirm it's pulling
  the text you just edited.
- To re-review cases that are still sitting open under the *old* policy after
  an edit like this, an admin can batch re-run them:
  `make reprocess a="--since <date> --policy-version <new>"` — a real
  operational tool, not something this walkthrough needs for the demo itself.

Remember to edit the document back afterward if you want the store's real
30-day policy restored for later walkthroughs — that's just another edit,
version 3, exactly as real as the first one.

## Why it matters

A policy that lives in a database with real version history is auditable in a
way a hardcoded rule never can be: you can always answer "what rule was in
force when this refund was approved," which matters the moment a customer, an
auditor, or a court asks. RAG over a versioned document is also what lets a
non-engineer — an actual policy owner — change the rule without touching code
or waiting for a deploy.
