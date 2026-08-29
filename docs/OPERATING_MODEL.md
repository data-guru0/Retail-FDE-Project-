# Operating model

Who runs ReturnGuard once it's live, and how the work actually flows.

## Roles

- **Customer** — submits returns in the shop, answers info requests, can appeal a
  denial. Sees only a status tracker (`under review → approved/denied →
  refunded`) and the plain-English explanation.
- **Reviewer** — works the dashboard queue: claims a case, reads the agent trace
  + evidence, approves / denies (with the confirm step) / requests info. Handles
  appeals routed to them (never their own).
- **Admin** — everything a reviewer can do, plus: sets `automation_level` per
  scope, the kill switch, `tau_risk` / `tau_conf` / `qa_sample_pct`, and edits
  policy text.

## Daily flow

1. Returns arrive → the pipeline runs in `shadow` (default) → decisions logged,
   everything in the queue for a human.
2. Reviewers work the queue. Each decision writes an `agreement_samples` row
   (agent proposal vs human outcome).
3. Weekly: the admin looks at the Agent-health page — agreement trend per agent
   and per decision type, cost per decision, false-positive rate from real
   overrides.
4. When agreement on a decision type is consistently high and the vs-baseline
   numbers are compelling, the admin moves that category to `suggest`, then
   `assist`. Each step is logged to `audit_log` (`edit_governance`).
5. In `assist`, `qa_sample_pct` of auto-approvals still land in the queue —
   reviewers keep a hand on the wheel.
6. Any drift (agreement drops, a new failure mode) → drop the level, or the kill
   switch, and add a scenario to `docs/SCENARIOS.md` for the new behaviour.

## What "done" looks like for a case

| Route | `returns.status` | Who acted | Audit action |
|---|---|---|---|
| auto-approve | `approved`, `refund_state=pending` | Governance Gate | `auto_approve` |
| escalate | `escalated` | Governance Gate → then a reviewer | `escalate`, then `decide_*` |
| human deny | `denied` | reviewer (confirm step) | `decide_deny` |
| appeal | new task → different reviewer | reviewer | `appeal_open`, `appeal_resolve` |
| info request | `info_requested` → back to `pending` | reviewer ↔ customer | `request_info` |

## Escalation contacts

Local-only project — none. In a real deployment this section names the on-call
for pipeline outages, the fraud lead for ring findings, and the finance owner
for the refund ledger.
