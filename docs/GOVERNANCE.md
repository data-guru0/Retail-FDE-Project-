# Governance model

How each non-negotiable is actually enforced in code — not by policy, by a check
that fails if it's violated.

| Non-negotiable | Enforcement point | Verified by |
|---|---|---|
| Nothing mocked / faked | every `verify_*` compares live API/UI output to real DB rows + real Langfuse traces; `verify_m3` confirms a real upstream call via Bifrost metrics | `scripts/smoke.py` |
| Human action → DB + audit | every dashboard mutation goes through a service that writes `returns` (or `feature_flags` / `policy_docs`) **and** an `audit_log` row in one transaction; the UI refetches, never patches local state | `verify_m5` |
| Every decision traceable | each graph node writes `agent_runs` (agent, SA subject, model, prompt-version hash, policy version, input hash, tokens, cost, latency, Langfuse trace id) + streams `agent_run_events` | `verify_m3`, `verify_m4` |
| Auto-deny needs a human | `GovernanceGate` cannot emit a final `deny` — a `deny` proposal becomes `escalate(proposed=deny)`. The reviewer's `confirm: true` step is the only path to a `denied` return | `verify_m5` (deny w/o confirm → 400), scenario A7 |
| Auto-approve is bounded | `GovernanceGate` requires `risk < tau_risk` AND `confidence > tau_conf` AND no Critic veto AND no high-value flag AND `automation_level ∈ {assist, auto}`. Thresholds live in `feature_flags`, per scope | scenario A6, `verify_m5` step 8 |
| Per-agent least privilege | Keycloak SA ↔ ContextForge virtual server (tool allow-list) ↔ Bifrost virtual key. The Image agent's virtual server exposes **zero** tools | `verify_m4` (Image server has no `flag_ring`), `verify_security` |
| No money-mutating tool reachable by an agent | refunds are a human-only dashboard action; `mcp-server/tools.py` has no refund/charge tool | `verify_security` (greps the tools source + asserts no auto-approve under injection) |
| Conflict of interest | a reviewer can't action their own appeal or a case they previously decided; appeals route to a different reviewer | `verify_m5`, scenario B5 |
| Audit is tamper-evident | `audit_log` append-only (DB trigger blocks UPDATE/DELETE) + hash chain (ADR-0003) | `scripts/verify_audit_chain.py` |
| Deployment starts safe | the global `feature_flags` row is seeded at `automation_level='shadow'` in the baseline migration | `verify_m1` (row exists), ADR-0008 |

## The autonomy ladder

`shadow → suggest → assist → auto`, per scope (global + per category), read per
run. The kill switch overrides everything. See ADR-0008 for the full table and
rules. The Analytics page produces the agreement-trend + hours/$ -saved numbers
that justify each promotion.

## What an admin can change (and what it costs)

- `automation_level` per scope — the biggest lever; a bad move is one toggle from
  full human review.
- `kill_switch` — instant, global, all cases to humans.
- `tau_risk` / `tau_conf` — the auto-approve envelope. Lower `tau_conf` or raise
  `tau_risk` = more auto-approvals = more risk. The agreement trend is the guard.
- `qa_sample_pct` — the fraction of `assist` auto-approvals still spot-checked.
- Policy text — a new `policy_docs` version + Qdrant re-embed; later runs record
  which version applied, so a decision can always be explained against the rules
  that were in force.
