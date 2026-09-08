# Scenario 12 — Reviewer override, deny-with-confirm, and the appeal

**Route:** human decision **· Automated by:** `python scripts/verify_m5.py` (override + request-info) **· Group:** governance controls

## What this shows

Three things that only happen when a person acts:

1. A reviewer can **override** the agent — and it's recorded as a disagreement.
2. A denial requires an explicit **confirm** step; a plain "deny" is rejected.
3. An **appeal** is routed to a *different* reviewer — the one who decided it
   can't touch it (conflict-of-interest guard).

## Run it

```bash
python scripts/verify_m5.py
```

That script: submits a mismatched-photo return → it escalates → a reviewer claims
it → tries to deny without `confirm` (**400**) → denies with `confirm: true`
(**200**) → checks `final_decision=deny`, `status=denied`, the audit chain still
validates, and an `agreement_samples` row was written. It also runs the
request-info round trip.

### By hand (dashboard, http://localhost:3000)

1. **Escalate a case:** run Scenario 02 (mismatched photo) so a case lands in the
   queue with the agent proposing `escalate` (or `approve` for a cleaner
   override demo — use Scenario 06's high-value case, agent proposed `approve`).
2. **Claim it** as `reviewer1@returnguard.local` — `POST /dashboard/returns/{id}/claim`.
3. **Override:** decide the *opposite* of what the agent proposed.
   ```bash
   # deny without confirm -> rejected
   curl -X POST .../dashboard/returns/{id}/decide -d '{"decision":"deny"}'
   #  400  "denial requires the explicit confirm step"

   # deny with confirm -> accepted
   curl -X POST .../dashboard/returns/{id}/decide \
        -d '{"decision":"deny","confirm":true,"note":"worn beyond policy"}'
   #  200  {"status":"denied","agent_agreement":false}
   ```
   (In the UI the Deny button opens a confirm dialog that sets `confirm:true`.)
4. **Appeal:** as the **customer**, open the denied return and submit an appeal —
   `POST /appeals/returns/{id}`.
5. **COI guard:** `reviewer1` (who denied it) calls
   `POST /appeals/{appeal_id}/resolve` → **403 "conflict of interest"**. The
   appeal is assigned to a different reviewer.

## What happens, step by step

| Step | Where | Effect on state |
|---|---|---|
| claim | `returns.claimed_by`, `claimed_at` set | case leaves the unclaimed queue |
| decide `deny` (no confirm) | — | **400**, nothing written |
| decide `deny` (confirm) | one transaction: `returns.status=denied`, `final_decision=deny`, `refund_state=none`, `decided_by`, `decided_at` **+** `audit_log` `action=decide_deny` (`actor_type=human`, `confirm=true`, `agent_had_proposed=...`) **+** `agreement_samples` row `kind=override`, `agreed=false` | the denial is now real; the hash chain extends |
| customer appeal | `appeals` row: `original_reviewer=reviewer1`, `assigned_to = someone ≠ reviewer1` | appeal enters a different reviewer's queue |
| `reviewer1` tries to resolve | `decided_by == p.reviewer_id` check (also enforced on `/decide`) → **403** | no state change |
| customer email | MailHog (http://localhost:8025) gets "Your return was denied" | — |

## What to check afterwards

```bash
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select status, final_decision, refund_state, decided_by is not null decided
  from returns order by decided_at desc nulls last limit 1;"
#  denied | deny | none | t

docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select kind, agent_decision, human_decision, agreed
  from agreement_samples where kind='override' order by id desc limit 1;"
#  override | approve/escalate | deny | f

docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select original_reviewer <> assigned_to as routed_away from appeals order by id desc limit 1;"
#  routed_away = t

python scripts/verify_audit_chain.py      # chain still validates after the human write
```

- **Dashboard → Agent health:** the agreement trend moves down a notch — a real
  disagreement, logged, visible.

## Why it matters

Every mutation a human makes goes through a service that writes the `returns` row
**and** an append-only audit row in one transaction, and the UI refetches rather
than patching itself — so the dashboard can never show a decision the database
doesn't have. The confirm step and the COI guard are the friction that belongs on
irreversible, contested actions.
