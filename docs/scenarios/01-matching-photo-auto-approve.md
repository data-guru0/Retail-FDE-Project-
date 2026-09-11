# Scenario 01 — Matching photo → auto-approved

**Route:** auto-approve · **Group:** decision behaviour · **[demo]**

New here? Read [00 — Watching a case live](00-watching-a-case-live.md) first —
it explains the Live Trace, Langfuse, MinIO, Grafana and alerts panels this
walkthrough points at.

## What this shows

A clean, in-policy return with a photo that genuinely matches the product is
cleared by the system in seconds — through a *real* CLIP image comparison, not
a shortcut — and a copy still lands in the human queue for quality control.
This is the "everything goes right" case: it's the baseline every other
walkthrough contrasts against.

## The situation

A regular customer (several past orders, no prior returns) bought the **Terra
Ceramic Mug Set (RG-009, $32)**. A few days after delivery, one mug arrives
cracked. They open a return, pick reason **Damaged**, and upload a real photo
of the mug set.

## Before you start

Log in to the dashboard as `admin1@returnguard.local` / `admin1`, go to
**Governance**, and set the **global** row's **Automation level** to `assist`,
then **Save**. (If you've just done the [automation ladder](12-automation-level-ladder.md)
walkthrough it may already be there.)

## Walkthrough (as the customer)

1. Go to `http://localhost:3000`, click **Sign in** (register a new account
   from Keycloak's login page if you don't have one).
2. Find the **Terra Ceramic Mug Set (4)** in the shop grid, open it, and click
   **Add to cart** — you'll land on the cart page.
3. Click **Checkout**, fill in an address and city/ZIP, leave the pre-filled
   test card as-is, and click **Pay $32.00**.
4. Go to **My orders**, open the order you just placed, and click
   **Return this** next to the mug set line.
5. Step 1: reason **damaged** → **Next**. Step 2: type something like "one mug
   arrived with a crack across the base" → **Next**. Step 3: upload a real
   photo of the item (a photo of the actual mugs, or the product photo you can
   save from the shop listing) → **Submit return**.
6. You land on `/returns/<id>` — note the id in the URL, then switch to the
   dashboard.

## What happens behind the scenes

Real numbers from a live run of exactly this case:

| Agent | What it did | Real result |
|---|---|---|
| **data_quality** | checked a photo was required and present | `ok: true` |
| **planner** | decided which checks this case needs | full plan: intake, policy, image, behavior, decision, critic, explanation |
| **intake** | called `get_order` via ContextForge, checked the request is coherent | `complete: true`, confidence 0.99 |
| **policy** | retrieved the return-window, condition, and category rules from Qdrant | `eligible: yes`, citing `return-window`, `condition-rules`, `category-exceptions` |
| **image** | ran real CLIP similarity between the upload and the catalog photo, plus the AI-image detector | `clip_similarity: 0.998` (match), `ai_generated_score: 0.016` (real photo) |
| **behavior** | scored the account's real order/return history via `get_customer_history` | `risk_score: 0.08`, `return_rate: 0.077` |
| **decision** | combined all signals | `decision: approve`, confidence 0.92 |
| **critic** | reviewed the Decision agent's reasoning | `veto: false, agree: true` |
| **explanation** | wrote the customer-facing reason | saved |
| **GovernanceGate** | risk 0.08 < τ_risk, confidence 0.92 > τ_conf, no veto, level allows it | **`auto_approve`**, and rolled the QA sample die |

## In the reviewer dashboard

Open `/dashboard/<id>`. **Status**, **Agent proposed**, and **Final** all show
green **approved** / **approve** badges. The **Actions** panel is gone —
there's nothing left for a human to do. A few minutes later the `Return #`
row in **My returns** (customer side) shows stage **refunded** — the
`process_refunds` worker cron moved it from `pending` to `refunded` and sent
an email, without anyone clicking anything.

## Watch it live

- **Live Trace:** a full `pipeline_start` → node events → `pipeline_end`
  sequence ending with `route: auto_approve` — no human ever appears in it.
- **Langfuse:** six generations for this one case (planner, intake, policy,
  behavior's LLM read, decision, critic, explanation minus data_quality/image/
  behavior's local model) — every one under a cent.
- **MinIO:** `returnguard` bucket → `returns/<id>/<file>.jpg` — the photo you
  just uploaded, EXIF-stripped.
- **Analytics page:** **hours saved** and **dollars saved** tick up by one
  case; the **auto-approved** bar under Quality grows by one.
- **Alerts:** none of the four fire here — this is the "everything is fine"
  baseline the alerts are watching *against*.

Even at `assist`, an admin can dial `qa_sample_pct` up (we used 100% while
testing this ourselves) so a share of auto-approvals still get a human's eyes
— check **agreement_samples** growth on the Analytics agreement trend.

## Why it matters

Autonomy is safe *because it's bounded*. This case only auto-approved because
every one of several independent gates passed: policy-eligible, a real image
match, low behavioural risk, no Critic veto, and an admin had explicitly
turned automation on. Flip any single one of those and the exact same case
goes to a human instead — see the next few walkthroughs.
