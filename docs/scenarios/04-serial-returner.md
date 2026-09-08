# Scenario 04 — Serial returner → escalate

**Route:** escalate **· Automated by:** manual (`_seed_history` helper) **· Group:** decision behaviour **· [demo]**

## What this shows

A single return can look completely ordinary and still be the tip of a pattern.
The Behaviour agent scores the *history*, not just this transaction, so a
high-return-rate account gets a human even when the individual request is clean.

## The situation

An account has placed 12 orders and already returned 9 of them (return rate
~0.75, several previously denied). Now it files one more return that, taken
alone, has a reasonable reason and an acceptable photo.

## Run it

There's no dedicated `run_scenarios.py` entry; build it with the same helper the
suite uses.

```bash
python - <<'PY'
import sys; sys.path.insert(0, "scripts")
from run_scenarios import (_customer, _place_order, _seed_history, _age_order,
                           _submit_return, _wait_final, MUG, _set_level)
from _rg import q1

_set_level("assist")
try:
    h, email = _customer("serial")
    o = _place_order(h)                       # cheap item, well under the high-value line
    _seed_history(email, orders=12, returns_=9)   # <-- the pattern
    _age_order(o["id"], 6)
    rid = _submit_return(h, o["items"][0]["id"], "damaged", "Arrived scratched.", MUG)
    print("return:", rid)
    res = _wait_final(rid)
    beh = q1("select parsed_output from agent_runs where graph_run_id=%(g)s "
             "and agent='behavior' and model like 'behavior_risk:%%'", g=res["graph_run_id"])
    print("status:", res["status"], " risk_score:", beh.get("risk_score"),
          " return_rate:", (beh.get("customer_history") or {}).get("return_rate"))
finally:
    _set_level("shadow")                      # leave the stack as we found it
PY
```

Expected: `status: escalated  risk_score: ~0.65  return_rate: ~0.77`.

Then open `/dashboard/<id>`.

## What happens, step by step

| # | Node | What it does here | What you see |
|---|---|---|---|
| 1–4 | data_quality → planner → intake → policy | normal; `get_order` + `check_policy` via ContextForge; policy likely **eligible**; `policy_version` recorded | tool calls `ok=true` |
| 5 | **image** | CLIP score is acceptable for the generic photo — this signal is *fine* | `clip_similarity` mid/high |
| 6 | **behavior** | `get_customer_history` via ContextForge → 12 orders / 9 returns, prior denials. The scikit-learn risk model weights `return_rate` and `prior_denied_returns` heavily → **risk score is high** (~0.6+). An LLM read of the qualitative pattern agrees. `flag_ring` → no shared fingerprints | `risk_score` high, `return_rate ≈ 0.75` |
| 7 | **decision** | policy is fine and the photo is fine, but the behavioural risk dominates → **escalate**, citing the return rate | `decision = escalate` |
| 8 | **critic** | concurs | `veto = false` |
| 9 | **explanation** | "Your account's recent return activity means a specialist will review this one." | text saved |
| 10 | **GovernanceGate** | proposed = `escalate`; also `risk` is above `tau_risk`, so even if Decision had said `approve` it would not clear the auto-approve envelope → **escalate** | `route = escalate` |

## What to check afterwards

```bash
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select parsed_output->>'risk_score' risk, parsed_output->>'return_rate' rr
  from agent_runs where agent='behavior' order by created_at desc limit 1;"
```

- **Dashboard → case detail → Behaviour block:** the risk score and the
  contributing features (return rate, prior denials) are shown.

## Why it matters

Context beats the single case. Fraud and abuse show up in the shape of an
account's activity long before any one request looks wrong; scoring the history
is how you catch it without punishing a first-time returner.
