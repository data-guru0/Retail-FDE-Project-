# Scenario 02 — Mismatched photo → escalate

**Route:** escalate **· Automated by:** `python scripts/run_scenarios.py A2` **· Group:** decision behaviour **· [demo]**

## What this shows

The evidence photo is checked against the product, not trusted. When the photo is
a different object, the Image agent catches it and the case goes to a human — the
system never approves on a photo it can't reconcile.

## The situation

A customer orders an item and files a return claiming "this isn't what I
ordered", but the photo they attach is an unrelated object (a dark, generic
image). Automation level doesn't matter here — try it at `shadow` or `auto`.

## Run it

```bash
python scripts/run_scenarios.py A2
```

By hand: buy any product, start a return with reason **Not as described**, upload
`scenarios/fixtures/mismatch_photo.jpg`, submit, open the case in the dashboard.

## What happens, step by step

| # | Node | What it does here | What you see |
|---|---|---|---|
| 1 | **data_quality** | photo present, product has a reference image → pass | `ok=true` |
| 2 | **planner** | photo + reference exist → `image` stays in the plan | plan includes `image` |
| 3 | **intake** | `get_order` via ContextForge → order details | `tool_call ok=true` |
| 4 | **policy** | Qdrant retrieval + `check_policy` → may be within window, records `policy_version` | `rag` event |
| 5 | **image** | CLIP similarity between upload and catalog photo ≈ **0.63** — below the 0.75 match line → **borderline/mismatch**; the borderline result is escalated to the **vision LLM**, which reports "the photo does not depict the ordered item" | `clip_similarity ≈ 0.63`, a vision-LLM sub-call in the trace |
| 6 | **behavior** | risk model + `get_customer_history` + `flag_ring` → risk moderate | `risk_score`, `ring_accounts` |
| 7 | **decision** | policy might be fine, but the evidence doesn't support the claim → **escalate**, with "photo does not match the ordered item" cited | `decision = escalate` |
| 8 | **critic** | concurs — the mismatch is a real signal | `veto = false` (nothing to override; Decision already escalated) |
| 9 | **explanation** | "We couldn't match your photo to the item on the order; a specialist will take a look." | text saved |
| 10 | **GovernanceGate** | proposed = `escalate` → **escalate**. (Even at `auto`, only an `approve` proposal can be auto-finalised.) | `route = escalate` |

## What to check afterwards

```bash
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select status, decision, final_decision from returns order by created_at desc limit 1;"
#  status=escalated | decision=escalate | final_decision=NULL

docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select agent, parsed_output->>'clip_similarity' sim
  from agent_runs where agent='image' order by created_at desc limit 1;"
#  image | 0.63xx
```

- **Dashboard:** the case is in the reviewer queue; the case detail shows the
  low similarity score and the vision-LLM note as evidence.

## Why it matters

A model that approves refunds on whatever image it's handed can be farmed. Here
the photo is a claim to be verified, and a claim the system can't verify is a
claim a human sees.
