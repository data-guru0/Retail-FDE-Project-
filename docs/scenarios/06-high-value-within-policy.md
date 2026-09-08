# Scenario 06 — High value within policy → escalate

**Route:** escalate **· Automated by:** `python scripts/run_scenarios.py A6` **· Group:** decision behaviour

## What this shows

Some rules override automation entirely. A refund above the high-value threshold
always gets human sign-off — even at automation level `auto`, even when the
Policy agent says the return is perfectly eligible.

## The situation

A customer returns a big-ticket item — the order total is **over $250** — within
the return window, with a good account and a fine reason. Everything about it is
legitimate. The store is at level **`auto`** (the most permissive).

## Run it

```bash
python scripts/run_scenarios.py A6
```

The scenario buys the most expensive product in quantity to push the order total
past $250, ages the order 5 days, and submits a `defective` return.

## What happens, step by step

| # | Node | What it does here | What you see |
|---|---|---|---|
| 1–3 | data_quality → planner → intake | normal; `get_order` via ContextForge returns the order total | `tool_call ok=true` |
| 4 | **policy** | Qdrant retrieval + `check_policy` → **eligible** (within window, valid reason) **and** sets `high_value_flag = true` because the refund amount is over the threshold | `parsed_output.high_value_flag = true`, `policy_version` recorded |
| 5 | **image** | acceptable CLIP score | `clip_similarity` mid/high |
| 6 | **behavior** | history + ring checks clean → low/moderate risk | `risk_score` low |
| 7 | **decision** | on the merits this could be **approve** with decent confidence | `decision = approve` (often) |
| 8 | **critic** | no reasoning flaw to veto | `veto = false` |
| 9 | **explanation** | text saved |
| 10 | **GovernanceGate** | checks `high_value` **before** the auto-approve branch: `refund exceeds the high-value threshold; human sign-off required` → **escalate** with `proposed = approve`. The automation level is irrelevant to this rule | `route = escalate`, `proposed = approve` |

## What to check afterwards

```bash
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select status, decision, final_decision from returns order by created_at desc limit 1;"
#  status=escalated | decision=approve | final_decision=NULL

docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select parsed_output->>'high_value_flag' hv from agent_runs where agent='policy'
  order by created_at desc limit 1;"
#  true

docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select data->'final'->>'reason' from audit_log where actor_id='governance_gate'
  order by id desc limit 1;"
#  ...refund exceeds the high-value threshold; human sign-off required
```

- **Dashboard:** the case is in the queue pre-filled with the agent's `approve`
  recommendation — the reviewer just confirms or overrides.

## Why it matters

Graduated autonomy isn't all-or-nothing. The cheap, high-confidence cases flow;
the expensive ones always pause for a person, regardless of how far up the ladder
the store has moved.
