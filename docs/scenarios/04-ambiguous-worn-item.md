# Scenario 04 — Ambiguous / worn item → escalate

**Route:** escalate (proposed deny) · **Group:** decision behaviour

See [00 — Watching a case live](00-watching-a-case-live.md) first.

## What this shows

Not every case is clean-approve or obvious-fraud. A worn item returned as
"defective" sits in genuinely ambiguous territory — the real policy text
distinguishes wear from a defect, but a photo alone can't always prove which
one it is. This is what the system does with a judgment call instead of a
clear-cut answer.

## The situation

A customer returns **Cloudstep Knit Sneakers ($95)**, reason **defective**,
but their own description says: *"the sole looks a bit worn on one side, not
sure if that counts as defective or just from wearing them a few times."*

The real policy text (`condition-rules` and `category-exceptions`, seeded in
`seed/seed.py`) says exactly: *"Apparel must be unworn and unwashed"* and
*"Signs of normal wear are not considered defects."*

## Walkthrough (as the customer)

1. Buy the **Cloudstep Knit Sneakers**, then **My orders** → **Return this**.
2. Reason: **defective** → in the notes, describe genuine ambiguity — e.g.
   "one sole looks worn on the outside edge, not sure if that's a defect or
   just from wearing them" → upload a real photo of the item → **Submit
   return**.

## What happens behind the scenes

Real numbers from a live run:

| Agent | What it did | Real result |
|---|---|---|
| **policy** | read the actual apparel/condition rules via RAG | `eligible: no` — *"the item is Apparel, which must be unworn and unwashed... the reported worn sole is considered normal wear, not a defect"* |
| **image** | similarity was borderline, not a clean match or clean mismatch | `clip_similarity: 0.61 (borderline)` |
| **decision** | followed the policy reading | `decision: deny`, confidence 0.95 |
| **critic** | pushed back on the denial | *"the determination that the worn sole constitutes normal wear may not fully account for the specific condition... the borderline image similarity suggests further verification is warranted"* — `veto: true` |
| **GovernanceGate** | proposed = `deny` | **`escalate`** — *"auto-deny is never final; routed for human confirmation of the denial"* |

## In the reviewer dashboard

The case shows **Agent proposed: deny** in red, but **Status: escalated** in
amber — the two badges disagreeing on purpose is the whole point. The
reviewer reads the Policy agent's citation of the real "unworn and unwashed"
rule, looks at the photo, and makes the actual judgment call the system
couldn't safely make on its own.

## Watch it live

- **Live Trace:** the `governance` `node_end` payload's `reason` field is the
  exact "auto-deny is never final" sentence above — the same mechanism as
  [scenario 08](08-outside-return-window.md), triggered by a nuanced policy
  reading instead of a hard date rule.
- **Dashboard → Policy page:** open it to see the real `condition-rules` and
  `category-exceptions` text the Policy agent just cited — this isn't a
  hardcoded check, it's the same versioned document a human can edit (see
  [scenario 13](13-policy-edit-changes-later-cases.md)).

## Why it matters

Language rules ("normal wear ≠ a defect") are exactly the kind of judgment an
LLM reading real policy text is good at applying case by case — better than a
hardcoded `if "worn" in text: deny`. But "the policy agent leans no" still
isn't the same as "deny it" — the Critic's pushback and the structural
auto-deny block both exist so a single agent's read of an ambiguous case never
becomes the final word.
