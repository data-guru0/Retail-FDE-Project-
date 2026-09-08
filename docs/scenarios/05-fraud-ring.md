# Scenario 05 — Fraud ring → escalate

**Route:** escalate **· Automated by:** `python scripts/run_scenarios.py A5` **· Group:** decision behaviour **· [demo]**

## What this shows

Fraud is a graph, not a row. Two accounts that share a shipping address / device /
payment fingerprint are linked by the Behaviour agent's `flag_ring` tool, and a
return from either one is routed to a human — even if that single return looks
fine.

## The situation

Two customer accounts were created through the normal signup flow. Behind the
scenes they share the **same address hash and the same device hash** (seeded into
the `fingerprints` table). One of them files a return.

## Run it

```bash
python scripts/run_scenarios.py A5
```

What the scenario does: creates two real customers, places an order on each (so
both `users` rows exist), inserts shared `address` + `device` fingerprint rows
for both, ages the order, then submits a return from account #1.

## What happens, step by step

| # | Node | What it does here | What you see |
|---|---|---|---|
| 1–4 | data_quality → planner → intake → policy | normal; `get_order` + `check_policy` via ContextForge; policy may be **eligible**; `policy_version` recorded | tool calls `ok=true` |
| 5 | **image** | generic photo, acceptable CLIP score — not the deciding signal | `clip_similarity` mid |
| 6 | **behavior** | two ContextForge tool calls: `get_customer_history` (unremarkable for this account) **and `flag_ring`** → the tool joins `fingerprints` on shared `value_hash` + `kind` and returns the **linked account(s)**. `ring_accounts` is populated; the risk model + LLM read escalate the risk given a confirmed link | `tool_call tool=flag_ring via=contextforge ok=true`; `ring_accounts = [<other account id>, ...]` |
| 7 | **decision** | a confirmed account link on a refund request → **escalate**, citing the ring | `decision = escalate` |
| 8 | **critic** | concurs | `veto = false` |
| 9 | **explanation** | neutral customer wording | text saved |
| 10 | **GovernanceGate** | proposed = `escalate` → **escalate** | `route = escalate` |

## What to check afterwards

```bash
# the ring tool call is real and audited
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select payload->>'tool' tool, payload->>'via' via, payload->>'ok' ok
  from agent_run_events where kind='tool_call' and payload->>'tool'='flag_ring'
  order by seq desc limit 1;"
#  flag_ring | contextforge | true

docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select action from audit_log where action='call_tool' order by id desc limit 1;"
#  call_tool   (every tool call writes an audit row)

docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select jsonb_array_length((parsed_output->'ring_accounts')) linked
  from agent_runs where agent='behavior' order by created_at desc limit 1;"
#  linked >= 1
```

- **Dashboard → Ring view:** the two accounts appear connected on the shared
  fingerprint.

## Why it matters

Per-account checks miss coordinated abuse by design. The fingerprint join is how
one refund request pulls in everything connected to it, and it runs as a governed
MCP tool the Behaviour agent is explicitly granted (the Image agent is not).
