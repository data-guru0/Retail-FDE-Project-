# Scenario 11 — The automation ladder: shadow vs assist

**Route:** escalate (shadow) → auto-approve (assist), *same case* **· Automated by:** `python scripts/run_scenarios.py A1` then `A0` **· Group:** governance controls **· [demo]**

## What this shows

The **identical** clean return produces two different routes depending only on
`automation_level`. Moving up the ladder is a deliberate admin decision backed by
the agreement data that `shadow` mode collects for free.

## The ladder

| Level | What the pipeline does | Who acts |
|---|---|---|
| **`shadow`** (default) | runs, logs a decision | human does everything |
| **`suggest`** | runs, pre-fills the reviewer's screen | human acts |
| **`assist`** | auto-approves low-risk/high-confidence; `qa_sample_pct` of those still queued for QA | human handles the rest + QA |
| **`auto`** | as `assist`, no QA sampling | human handles the rest |

The kill switch (Scenario 10) overrides all four.

## Run it

```bash
# shadow: the agent decides, the human still acts
python scripts/run_scenarios.py A1

# assist: the identical clean case is auto-approved
python scripts/run_scenarios.py A0
```

Or set the level yourself between two hand-submitted copies of the Scenario 01
case (dashboard → **Governance** → `global` → level).

## What happens, step by step

**Both runs, nodes 1–9:** identical. data_quality passes, planner keeps `image`,
intake/policy/behavior call their ContextForge tools, CLIP ≈ 0.99, risk ≈ 0.05,
Decision = `approve` (confidence ≈ 0.9), Critic no veto, explanation written.

**Node 10 — GovernanceGate — is where they diverge:**

| | `shadow` (A1) | `assist` (A0) |
|---|---|---|
| branch taken | `automation_level=shadow: agent decides, human acts` | `risk 0.05 < tau_risk` AND `conf 0.90 > tau_conf` AND `level ∈ {assist,auto}` → **auto_approve** |
| `returns.status` | `escalated` | `approved` |
| `returns.final_decision` | `NULL` | `approve` |
| `refund_state` | unchanged | `pending` |
| `audit_log` action | `escalate` | `auto_approve` |
| QA sample | — | one `agreement_samples` row `kind=qa_sample` (at `qa_sample_pct`) |
| agreement data | accrues when the reviewer later decides | the QA sample is the check |

## What to check afterwards

```bash
# after A1 (shadow)
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select status, decision, final_decision from returns
  where id = (select entity_id::uuid from audit_log where action='escalate' order by id desc limit 1);"
#  escalated | approve | NULL

# after A0 (assist)
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select status, final_decision, refund_state from returns
  where id = (select entity_id::uuid from audit_log where action='auto_approve' order by id desc limit 1);"
#  approved | approve | pending
```

- **Dashboard → Analytics:** the `vs_baseline` hours/$ -saved and the
  **agent-vs-human agreement trend** are exactly the numbers an admin points to
  when justifying a move from `shadow` → `suggest` → `assist`.

## Why it matters

Trust is earned, not toggled. `shadow` costs nothing and produces the evidence;
you only turn on autonomy for a decision type once the data says the agent and
your reviewers already agree.
