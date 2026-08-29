# Demo walkthrough

The 8 audience-facing scenarios. Each is real — it runs through the actual
pipeline and produces the state described. The automatable ones are driven by
`scripts/run_scenarios.py`; the two UI-centric ones (7, 8) are done in the
dashboard.

Setup once:

```bash
make up && make migrate && make seed && make m4-setup
python scripts/mcp_setup.py
cd frontend && npm install && npm run dev     # http://localhost:3000
```

Dashboard logins (Keycloak): `admin1@returnguard.local` / `admin1`,
`reviewer1@returnguard.local` / `reviewer1`.

---

## 1. The easy case → auto-approved in seconds

```bash
python scripts/run_scenarios.py A0
```

- An established customer (12 orders, 0 returns) returns a $32 mug set 3 days
  after delivery, with a photo that **is** the product. Automation level `assist`.
- **Observe:** the pipeline runs all agents; CLIP similarity ≈ 1.0
  ("match"); Policy → eligible; Behaviour risk ≈ 0.01; Critic does not veto;
  the **Governance Gate auto-approves** → `returns.status = approved`,
  `refund_state = pending`, an `audit_log` row `action = auto_approve`, and a QA
  sample lands in the human queue (`agreement_samples.kind = qa_sample`).
- **Why it matters:** autonomy is safe *because it's bounded* — this only
  auto-approved because risk < τ, confidence > τ, no veto, not high-value, and an
  admin set the level. Every one of those is a real gate.

## 2. The mismatched photo → caught by the Image agent

```bash
python scripts/run_scenarios.py A2
```

- The return photo is a different object from what was ordered.
- **Observe:** the Image agent's CLIP similarity drops to ~0.63 ("mismatch");
  the case escalates; the score is in the case's live trace and the export.
- **Why:** evidence is checked, not trusted.

## 3. The AI-faked damage photo → caught by the detector

- Submit a return citing damage with an AI-generated image (generate one with
  `docker compose run --rm worker python -m ml.detector_bakeoff.run`, which puts
  real AI images in `ml/detector_bakeoff/sample/ai/`).
- **Observe:** the Image agent reports a high `ai_generated_score`
  (`haywoodsloan/ai-image-detector-deploy`, chosen by the bake-off — ADR-0002);
  combined with the damage claim the case escalates. It is **one signal**, never
  a lone denial.
- **Why:** one model's opinion is never the verdict.

## 4. The serial returner → flagged by Behaviour even when one case looks fine

```bash
python scripts/run_scenarios.py A5     # (A5 also seeds ring history)
```

- Manually: seed a high-return-history account (`scripts/run_scenarios.py`'s
  `_seed_history`), then submit an ordinary-looking return.
- **Observe:** the Behaviour agent's risk score is elevated from the return-rate
  and prior-denials features even though the single return is unremarkable →
  escalate.
- **Why:** context beats the single case.

## 5. Ring detection → two accounts sharing an address, flagged together

```bash
python scripts/run_scenarios.py A5
```

- Two accounts share an address + device fingerprint.
- **Observe:** the Behaviour agent's ring-detection SQL returns the linked
  accounts; the case escalates; the accounts appear together on the dashboard
  **Analytics → Ring detection** panel.
- **Why:** fraud is a graph, not a row.

## 6. The appeal → routed to a different reviewer

- In the dashboard: as `reviewer1`, deny a return (with the confirm step). As the
  customer in the shop, open the denied return and appeal it.
- **Observe:** an `appeals` row with `original_reviewer = reviewer1` and
  `assigned_to` = someone else; `reviewer1` calling
  `POST /appeals/{id}/resolve` gets a **403** (conflict of interest).
- **Why:** fairness needs a fresh pair of eyes.

## 7. Watching an agent think → the live trace

- In the dashboard, open a case **while it is being reviewed** (submit one, then
  immediately open `/dashboard/<id>`).
- **Observe:** the "Live trace" panel fills in node by node over the WebSocket —
  `data_quality`, `planner`, `intake`, `policy` (with the RAG query + hits),
  `image` (CLIP score), `behavior` (risk score + ring), `decision`, `critic`,
  `explanation`, `governance` — each with real tokens / cost / latency. Not a
  canned animation; it's the `agent_run_events` stream.
- **Why:** observability is not an afterthought — you can always see exactly what
  the system did and what it cost.

## 8. The rollout story → shadow vs assist

- The **same** easy case at two levels (Governance page, admin):
  - `shadow` — run scenario A1: the agent decides, it's logged, the case sits in
    the queue for a human, and when the human decides an `agreement_samples` row
    records agree/disagree.
  - `assist` — run scenario A0: the identical clean case is **auto-approved**,
    and the agreement trend + the Analytics "reviewer-hours saved / $ saved"
    numbers are what justify having moved the level up.
- **Observe:** `GET /dashboard/analytics` → `vs_baseline` and
  `GET /dashboard/agent-health` → `agreement_trend`.
- **Why:** trust is earned, not toggled. You don't turn autonomy on — you earn
  your way up the ladder with data, and the kill switch is one click back.

---

## Governance + operational scenarios

- **Kill switch:** Governance page → tick it on `global` → every case escalates,
  `audit_log` shows `kill_switch=true`. (`docs/RUNBOOK.md` — kill-switch drill.)
- **Policy edit + re-embed:** Policy page → change the return window → Save →
  a new `policy_docs` version, Qdrant re-embedded, and the next case's
  `agent_runs.policy_version` is the new one.
- **Dead-letter:** `python scripts/verify_m3_dlq.py` — 3 real crashes → a
  `dead_letter` row + auto-escalate, never an infinite retry.
- **Groq → OpenAI fallback:** observed organically — some runs' `agent_runs.model`
  is `gpt-4o-mini` when Groq returned an error; the decision is still real.
- **Load:** `python scripts/loadtest.py --factor 20` — p50/p95 time-to-decision;
  scale with `docker compose up -d --scale worker=N`.
