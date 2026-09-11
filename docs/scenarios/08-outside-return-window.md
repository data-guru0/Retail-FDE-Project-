# Scenario 08 — Outside the return window → escalate (proposed deny)

**Route:** escalate (proposed deny) · **Group:** decision behaviour

See [00 — Watching a case live](00-watching-a-case-live.md) first.

## What this shows

The system can be extremely confident a return should be denied — and it will
still never deny it by itself. This is the clearest possible demonstration of
"auto-deny is structurally impossible": a real 96%-confidence denial
recommendation, still routed to a human.

## The situation

A customer bought a **Weekend Organic Cotton Tee** 75 days ago and files a
return now, reason "no longer needed." The real policy text's standard window
is 30 days.

## Walkthrough (as the customer)

For a live demo you can't wait 75 real days — instead pick an order you placed
a while ago in a previous walkthrough (any order older than 30 days works;
or ask an admin to backdate one order's `placed_at` for the demo, the same way
the real order's age was set for this test). Then: **My orders** → the old
order → **Return this** → reason **no longer needed** → **Submit return**.

## What happens behind the scenes

Real numbers from a live run (order aged 75 days):

| Agent | What it did | Real result |
|---|---|---|
| **policy** | checked the real 30-day rule via RAG | `eligible: "no"` — *"the request is outside the standard 30‑day return window (75 days since delivery)"*, confidence 1.0 |
| **decision** | followed the policy reading | `decision: deny`, confidence **0.96** |
| **critic** | raised an unrelated concern (an image mismatch) but didn't dispute the window math | `veto: true` |
| **GovernanceGate** | proposed = `deny` | **`escalate`** — *"auto-deny is never final; routed for human confirmation of the denial"* |

## In the reviewer dashboard

**Agent proposed** shows a red **deny** badge; **Status** shows amber
**escalated** — never a final red **denied** badge, no matter how confident
the agent was. Only a reviewer clicking **Deny (confirm)** — which pops a
native confirmation dialog ("Confirm denial? This is the human confirm
step.") — can actually produce a denied case (see
[scenario 15](15-reviewer-override-and-appeal.md) for that full flow,
including the customer's right to appeal it afterward).

## Watch it live

- **Live Trace → governance `node_end`:** `proposed: "deny"` sitting right
  next to `route: "escalate"` — the two fields disagreeing is the entire
  point, and it's true even at automation level `auto` (nothing about
  raising automation ever removes this gate — same mechanism as
  [scenario 07](07-high-value-within-policy.md)'s hard boundary).
- **Governance page:** re-read the rule in plain English at the top of the
  page — *"the kill switch forces every case to a human regardless of
  level"* is the sibling rule; this one is unwritten there because it's not
  a *level* setting at all, it's a permanent code-level constraint in
  `GovernanceGate` (`worker/pipeline/governance.py`) — no admin toggle turns
  it off.

## Why it matters

A wrong auto-approval costs money; a wrong auto-denial costs a customer's
trust and possibly a legitimate refund they were owed. The system is allowed
to be very confident here — 96% — and that confidence still isn't enough
justification to skip a human, because the cost of being wrong is asymmetric.
