# Scenario 07 — High value, within policy → escalate

**Route:** escalate · **Group:** decision behaviour

See [00 — Watching a case live](00-watching-a-case-live.md) first.

## What this shows

Money size is its own gate, independent of everything else. A refund over the
real policy's $250 threshold always gets a human — even one that's otherwise
completely clean and even at the most permissive automation level.

## The situation

A customer buys the **Aurora 27" 4K Monitor ($329)** and returns it as
defective, with a photo. $329 is comfortably over the real `$250` line written
into the policy text (`seed/seed.py`'s `high-value-and-fraud` document: *"Any
refund over $250 requires human confirmation regardless of automated
assessment"*) and mirrored in code (`HIGH_VALUE_USD = 250` in
`worker/pipeline/nodes/agents.py`).

## Walkthrough (as the customer)

1. Buy the **Aurora 27" 4K Monitor**, then **My orders** → **Return this**.
2. Reason: **defective** → describe the fault → upload a real photo →
   **Submit return**.

## What happens behind the scenes

Real numbers from a live run — with the store deliberately set to the *most*
permissive level (`assist`, τ_risk 0.9, τ_conf 0.2) to prove the high-value
gate holds regardless:

| Agent | What it did | Real result |
|---|---|---|
| **policy** | flagged the value on top of the normal eligibility check | `eligible: "unclear"`, `high_value_needs_human: true` — *"the item is flagged as high-value and therefore requires human review before a final decision"* |
| **decision** | high-value flag plus a photo mismatch | `decision: escalate`, signals include `high_value_flag` |
| **critic** | pointed out the Decision agent should have leaned on the high-value rule specifically | `veto: true` |
| **GovernanceGate** | `high_value_flag = true` | **`escalate`** — *"refund exceeds the high-value threshold; human sign-off required"*, regardless of risk/confidence numbers |

## In the reviewer dashboard

The case detail page's **Amount** field shows `$329.00` — noticeably larger
than most cases in the queue. Expanding **policy** in Agent reasoning shows
`high_value_flag: true` right in the parsed output; expanding **governance**
shows the exact "refund exceeds the high-value threshold" reason string.

## Watch it live

- **Live Trace → governance `node_end`:** the `reason` field is that literal
  sentence — not "risk too high," not "confidence too low," a distinct, named
  rule.
- Try the same case at automation level `auto` (Governance page → global →
  `auto` → Save) — it escalates exactly the same way. High-value bypasses the
  automation ladder entirely; it isn't something an admin can turn off by
  raising the level.
- **Analytics → Unit economics:** the **monthly projection** stat is one of
  the numbers this gate exists to protect — a single wrongly-auto-approved
  high-value refund would move it more than a dozen small ones.

## Why it matters

Thresholds and confidence scores are the agents' read of *this* case; the
high-value rule is a hard business boundary set by a human in advance,
independent of how confident any model is. Keeping it structurally separate
from the risk/confidence envelope means a very convincing model can still
never auto-clear a refund above the line an admin drew.
