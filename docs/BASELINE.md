# Baseline assumptions

The Analytics page compares ReturnGuard against the **all-human** process it
replaces. These are the numbers that comparison uses. They live here (not in
code) so they can be revised without a deploy; `backend/app/routers/analytics.py`
reads them.

| Assumption | Value | Basis |
|---|---|---|
| Reviewer fully-loaded cost | **$32 / hour** | mid-market ops analyst, US, incl. benefits + overhead |
| Human handling time per return (all-human) | **7.5 min** | read order + policy + photo, decide, log — median |
| Human handling time per **escalated** case (with ReturnGuard) | **4.0 min** | the agent has already gathered evidence + drafted a recommendation |
| Human confirm time for an auto-approve QA sample | **1.5 min** | spot check only |
| Return volume | measured from `returns` (last 30 days), annualised |
| Fraud loss per undetected fraudulent refund | **$140** | mean refund amount in the synthetic fraud population |

## Derived comparisons the Analytics page shows

- **reviewer-hours saved** = `auto_approved * 7.5min` + `escalated * (7.5 - 4.0)min`
  + `qa_samples * (7.5 - 1.5)min`, all ÷ 60.
- **$ saved** = reviewer-hours saved × $32.
- **cost-per-decision** = `sum(agent_runs.cost_usd) / count(distinct graph_run_id)`,
  broken out by model.
- **all-human vs current vs full-auto** monthly projection: volume × the per-mode
  handling time × $32, plus LLM spend for the agent modes.
- **false-positive rate** = reviewer overrides where the agent proposed `approve`
  but the human denied (or vice-versa) ÷ total reviewed, from `agreement_samples`.

All inputs are real rows; only the rates in the table above are assumptions.
