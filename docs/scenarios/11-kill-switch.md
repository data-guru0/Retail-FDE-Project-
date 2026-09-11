# Scenario 11 — Kill switch → every case escalates

**Route:** escalate (all) · **Group:** governance controls

See [00 — Watching a case live](00-watching-a-case-live.md) first.

## What this shows

One admin toggle overrides every automation level, every threshold, and every
agent's opinion, immediately, for every case in flight and every case after
it — no redeploy, no restart.

## Walkthrough (as an admin, then as a customer)

1. Log in as `admin1@returnguard.local` / `admin1`, go to **Governance**.
2. On the **global** row, make sure **Automation level** is `assist` (so a
   clean case *would* normally auto-approve), then tick **Kill switch —
   force human review** and click **Save**. A red **kill switch active**
   badge appears on the card.
3. As a customer, submit the same kind of case that auto-approved in
   [scenario 01](01-matching-photo-auto-approve.md): an established account,
   a genuinely matching photo, an in-policy item.

## What happens behind the scenes

Real numbers from a live run — same recipe as scenario 01, kill switch on:

| Agent | Result | |
|---|---|---|
| **image** | `clip_similarity: ~1.0` (real match) | |
| **behavior** | `risk_score: 0.07` | |
| **decision** | `decision: approve`, confidence **0.94** | the agent genuinely wanted to approve this |
| **critic** | `veto: false` | no objection at all |
| **GovernanceGate** | `proposed: "approve"` but `kill_switch: true` | **`escalate`** — *"kill switch is on — every case goes to human review"* |

Every gate that normally allows auto-approval passed. The kill switch alone
is what stopped it — it's checked before every other rule in
`GovernanceGate`, so it doesn't matter how clean the case is.

## In the reviewer dashboard

The case lands in the escalated queue exactly like a genuinely risky one, but
**Agent proposed** shows a green **approve** badge — the visible mismatch
between "the agent wanted to approve this" and "a human still has to" is the
signature of the kill switch specifically (compare
[scenario 08](08-outside-return-window.md), where the mismatch runs the other
way: the agent wanted to deny, and still can't finalize it alone).

## Watch it live

- **Live Trace → governance `node_end`:** `kill_switch: true` sits right in
  the payload next to the exact reason string above.
- **Grafana → Pipeline runs by route:** watch the `escalate` line jump while
  `auto_approve` flatlines, for cases that would otherwise have split between
  the two.
- Turn it back off (**Governance** → untick → **Save**) and resubmit the same
  kind of case — it auto-approves again immediately. No restart, no
  deployment, just a row in `feature_flags` read fresh on the very next case.

## Why it matters

Every autonomous system needs a big red button that works even when you don't
trust anything else about the system's current state — a bad model deploy, a
suspicious spike in approvals, a policy dispute mid-investigation. The kill
switch is that button: one flag, checked first, that no threshold tuning or
automation-level setting can route around.
