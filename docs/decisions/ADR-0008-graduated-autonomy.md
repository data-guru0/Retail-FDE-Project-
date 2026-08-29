# ADR-0008 — Graduated autonomy (`shadow` → `suggest` → `assist` → `auto`)

**Status:** accepted (M3 default `shadow`, gate enforced M4)

## Context
"Turn the agent on" is not a safe operation. We need to earn trust with data
before letting the system act, and we need a way to pull back instantly.

## Decision
One `automation_level` per scope (global + per category), stored in
`feature_flags`, **read per run** by GovernanceGate:

| level | agent decides | who acts | agreement data | auto-approve | QA sampling |
|---|---|---|---|---|---|
| `shadow` | yes | human (everything) | accrues from day 1 | no | — |
| `suggest` | yes | human (screen pre-filled) | accrues | no | — |
| `assist` | yes | agent auto-approves low-risk/high-conf; rest to humans | accrues | yes | X% of auto-approvals still queued |
| `auto` | yes | as `assist` | accrues | yes | none |

Every deployment **starts in `shadow`**. Moving up the ladder is a deliberate
`admin` action, justified by the agent-vs-human agreement trend and the
vs-baseline numbers on the Analytics page.

Hard rules GovernanceGate enforces regardless of level:
- **kill switch** → escalate everything.
- **auto-deny is impossible** — a `deny` proposal always routes to
  `escalate(proposed=deny)`; only a human's confirm step produces a denied return.
- **auto-approve is bounded** — `risk < tau_risk` AND `confidence > tau_conf` AND
  no Critic veto AND no high-value flag AND level ∈ {assist, auto}.
- thresholds `tau_risk` / `tau_conf` and `qa_sample_pct` live in `feature_flags`,
  tuned by an `admin`.

## Consequences
- The system is useful (agreement data) from the first day, at zero action risk.
- A bad rollout is one `admin` toggle away from full human review.
- The decision-behaviour scenarios (`docs/SCENARIOS.md` B2) demonstrate each level.
