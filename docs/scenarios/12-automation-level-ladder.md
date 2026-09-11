# Scenario 12 — The automation ladder: shadow → suggest → assist → auto

**Route:** varies by level · **Group:** governance controls · **[demo]**

See [00 — Watching a case live](00-watching-a-case-live.md) first.

## What this shows

The exact same clean case — same customer history, same matching photo, same
real agent reasoning — produces four different outcomes depending only on
which of the four automation levels an admin has chosen. Nothing about the
case changes; only how much the system is trusted to act on its own read of
it.

## Walkthrough (as an admin, then as a customer, four times)

For each level: **Governance** → global row → **Automation level** → pick the
level → **Save**, then submit the [scenario 01](01-matching-photo-auto-approve.md)
recipe (established account, genuinely matching photo, in-policy item) as a
customer, and open the resulting case in the dashboard.

## `shadow` — the default every deployment starts at

Real result from a live run: the agent proposed `approve` (risk 0.07,
confidence 0.93) — but the final row is `status: escalated, final_decision:
null`. The governance reason, verbatim: **`"automation_level=shadow: agent
decides, human acts"`**. The full multi-agent graph ran for real, a real
decision was logged, and a human still has to do every bit of the actual
work. This is how agreement data accrues at zero risk before anyone trusts
the system with anything.

## `suggest` — same routing as shadow, with one UI difference

A `suggest`-level case escalates identically to `shadow` (verified in the
frontend's own code — the routing logic doesn't distinguish them at all). The
difference is entirely in what the reviewer sees: opening the case in
**Actions**, a banner reads **"★ Agent suggests `approve` — note pre-filled
below. Confirm it or override,"** and the decision note textarea already
contains the agent's own explanation. The reviewer isn't asked to start from
a blank form — they're asked to *check the agent's work*, which is a
meaningfully different task even though the underlying route is the same.

## `assist` — the target state

Real result (this is exactly [scenario 01](01-matching-photo-auto-approve.md)):
`status: approved`, governance reason **`"auto-approved: risk 0.08 < 0.9,
confidence 0.92 > 0.2, level=assist, no Critic veto; QA sample: 1-in-1
auto-approvals reviewed"`**. Auto-approval is live, and a slice of those
auto-approvals (`qa_sample_pct` in Governance, 10% by default) still lands a
copy in the human queue for spot-checking — visible as a `qa_sample` row on
the Analytics agreement trend.

## `auto` — like assist, minus the safety net

Real result from a live run: `status: approved`, governance reason
**`"auto-approved: risk 0.08 < 0.9, confidence 0.92 > 0.2, level=auto, no
Critic veto"`** — note there's no `QA sample:` clause at all this time. Same
auto-approval, but nothing gets randomly pulled back for human review anymore.

## Watch it live

- **Live Trace, side by side:** run `shadow` then `auto` back to back and
  diff the `governance` `node_end` payloads — same `risk`, same `confidence`,
  same `proposed`, different `route` and a different `reason` string. That
  diff *is* the automation ladder.
- **Analytics → Quality (from real overrides):** watch the **auto-approved**
  bar grow only once you're above `shadow`/`suggest`, and watch **qa samples**
  grow only at `assist`, not `auto`.
- **Grafana → Pipeline runs by route:** the clearest single panel for
  narrating this scenario live to a class — the mix of `auto_approve` vs.
  `escalate` visibly shifts as you change the level between submissions.

## Why it matters

"Trust is earned, not toggled" only means something if going up a level is a
single, deliberate, auditable admin action — and going back down (or hitting
the kill switch) is exactly as immediate. The ladder is what lets a real
deployment start at zero risk (`shadow`), accumulate real agreement data, and
move up only when that data justifies it — never by assuming the model is
good because it sounds confident.
