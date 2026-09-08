# Scenario 01 — Matching photo → auto-approved

**Route:** auto-approve **· Automated by:** `python scripts/run_scenarios.py A0` **· Group:** decision behaviour **· [demo]**

## What this shows

A clean, in-policy return with a photo that genuinely matches the product is
cleared by the system in seconds — through a *real* image check, not a bypass —
and a copy still lands in the human queue for quality control.

## The situation

An established customer (12 past orders, 0 returns) bought a **Terra Ceramic Mug
Set (RG-009, $32)**. Three days after delivery one mug arrives cracked. They open
a return, reason "damaged", and upload a photo. The photo *is* the real catalog
image of that mug set. The store is running at automation level **`assist`**.

## Run it

```bash
# from the repo root, stack already up (make up + make migrate + make seed + make m4-setup)
python scripts/run_scenarios.py A0
```

Or by hand in the shop (http://localhost:3000):

1. Register / log in as a customer, buy the **Terra Ceramic Mug Set**.
2. Orders → that order → **Return item** → reason **Damaged**, note "one mug
   cracked", upload `scenarios/fixtures/matching_RG-009.jpg`, submit.
3. As `admin1@returnguard.local` set **Governance → global → level = assist**
   first.

## What happens, step by step

Open the case in the dashboard (`/dashboard/<id>`) and watch the **Live trace**
fill in over the WebSocket:

| # | Node | What it does here | What you see |
|---|---|---|---|
| 1 | **data_quality** | reason needs a photo → a photo is present; product has a reference image | `node_end` `ok=true` |
| 2 | **planner** | a return photo *and* a reference image exist → keeps `image` in the plan | plan = `[intake, policy, image, behavior, decision, critic, explanation]` |
| 3 | **intake** | calls `get_order` **through ContextForge** → order total, item, dates | `tool_call` `tool=get_order via=contextforge ok=true` |
| 4 | **policy** | embeds the request, retrieves the return-window + Home&Kitchen rules from Qdrant, calls `check_policy` → **eligible**, records `policy_version` | `rag` event with the hits; `agent_runs.policy_version` set |
| 5 | **image** | CLIP similarity between the upload and the catalog photo ≈ **0.99** (match); AI-image detector score low | `clip_similarity ≈ 0.99`, `ai_generated_score` low |
| 6 | **behavior** | scikit-learn risk model on the tabular features → risk ≈ **0.05**; `get_customer_history` + `flag_ring` via ContextForge → no linked accounts | `risk_score ≈ 0.05`, `ring_accounts = []` |
| 7 | **decision** | combines: policy-eligible + photo match + low risk → **approve**, confidence ≈ 0.9 | `decision = approve` |
| 8 | **critic** | reviews the Decision's reasoning — policy eligible, image matches, low risk, no ring → **nothing to veto** | `veto = false` |
| 9 | **explanation** | writes the plain-English reason stored for the customer + audit | text saved |
| 10 | **GovernanceGate** | `risk 0.05 < tau_risk` **and** `confidence 0.90 > tau_conf` **and** no veto **and** not high-value **and** `level = assist` → **auto_approve**. Then rolls `qa_sample_pct` → a QA sample row is written | `route = auto_approve`; `node_end` reason string |

## What to check afterwards

```bash
# the return is approved with a pending refund
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select status, decision, final_decision, refund_state from returns order by created_at desc limit 1;"
#  status=approved | decision=approve | final_decision=approve | refund_state=pending

# the Governance Gate is the finalizer, and it's in the append-only audit log
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select actor_id, action from audit_log order by id desc limit 3;"
#  governance_gate | auto_approve

# a QA sample landed in the human queue
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select kind, agent_decision from agreement_samples order by id desc limit 1;"
#  qa_sample | approve
```

- **Dashboard → Analytics:** `hours saved` / `$ saved` tick up.
- **Langfuse (http://localhost:3001):** the trace for this run has a GENERATION
  observation per LLM node with real tokens + cost.
- The refund itself is **not** issued by the pipeline — the `process_refunds`
  worker cron moves `refund_state pending → refunded` and emails the customer.

## Why it matters

Autonomy is safe *because it is bounded*. This auto-approved only because every
one of five gates passed — risk < τ, confidence > τ, no Critic veto, not
high-value, and an admin had set the level. Flip any one and it goes to a human.
The image check was real CLIP inference on the actual pixels, not a rule that
trusts the upload.
