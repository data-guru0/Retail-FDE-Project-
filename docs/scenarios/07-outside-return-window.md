# Scenario 07 — Outside the return window → proposed deny → escalate

**Route:** escalate (with `proposed = deny`) **· Automated by:** `python scripts/run_scenarios.py A7` **· Group:** decision behaviour

## What this shows

**Auto-deny is impossible by construction.** The Policy agent can conclude "not
eligible", the Decision agent can propose `deny`, but the Governance Gate can
never write a denied return — only a human's explicit confirm step does that.

## The situation

A customer wants to return an item **75 days** after it was placed. The standard
window is 30 days and no category exception applies. Reason: "changed my mind".
The store is at level **`auto`**.

## Run it

```bash
python scripts/run_scenarios.py A7
```

The scenario ages the order 75 days and submits a `no_longer_needed` return.

## What happens, step by step

| # | Node | What it does here | What you see |
|---|---|---|---|
| 1 | **data_quality** | `no_longer_needed` doesn't require a photo → pass | `ok=true` |
| 2 | **planner** | no photo needed / provided → may **drop `image`** from the plan | plan without `image` |
| 3 | **intake** | `get_order` via ContextForge → the (old) order date | `tool_call ok=true` |
| 4 | **policy** | Qdrant retrieval brings back the return-window rule; `check_policy` computes `days_since_order = 75` vs a 30-day window, no exception → **not eligible**; records `policy_version` | `parsed_output.eligible = false`, reason "outside the return window" |
| 5 | **behavior** | history + ring → not the deciding factor | `risk_score` |
| 6 | **decision** | policy says no and there's no mitigating factor → **deny** (proposed), citing the window | `decision = deny` |
| 7 | **critic** | the reasoning is sound → no veto | `veto = false` |
| 8 | **explanation** | drafts the denial rationale (stored for the reviewer *and* for any appeal) | text saved |
| 9 | **GovernanceGate** | sees `proposed == "deny"` → `auto-deny is never final; routed for human confirmation of the denial` → **escalate** with `proposed = deny`. `final_decision` stays `NULL` | `route = escalate`, `proposed = deny` |

A reviewer later opens the case, agrees, and clicks **Deny** — which requires a
`confirm: true` step (see Scenario 12). Only then does `returns.final_decision`
become `deny` and `status` become `denied`.

## What to check afterwards

```bash
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select status, decision, final_decision from returns order by created_at desc limit 1;"
#  status=escalated | decision=deny | final_decision=NULL   <-- NOT denied yet

docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select actor_id, action from audit_log order by id desc limit 1;"
#  governance_gate | escalate    (never 'auto_deny' — that action does not exist)
```

## Why it matters

The one direction the system must never move on its own is *taking money away
from a customer*. Making auto-deny structurally impossible — the gate has no code
path to it — is stronger than a policy that says "don't".
