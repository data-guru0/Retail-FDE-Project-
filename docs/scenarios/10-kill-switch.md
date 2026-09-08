# Scenario 10 — Kill switch on → everything escalates

**Route:** escalate (every case) **· Automated by:** manual **· Group:** governance controls

## What this shows

One global switch, owned by an admin, forces every case to human review
regardless of automation level, risk, confidence, or how clean the return looks.
It's the "hand off the wheel now" control.

## The situation

Something's wrong — a bad policy edit, a model acting oddly, an incident. The
admin flips the kill switch. From that moment, even a textbook auto-approve case
(Scenario 01) goes to a person.

## Run it

**Turn it on** (dashboard: `admin1@returnguard.local` → **Governance** → tick
*kill switch* on the `global` row → Save), or:

```bash
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "update feature_flags set kill_switch=true where scope='global';"
```

Now submit the Scenario 01 case (matching photo, established customer, level
`assist`):

```bash
python scripts/run_scenarios.py A0    # will NOT auto-approve while the switch is on
```

**Turn it back off** when done:

```bash
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "update feature_flags set kill_switch=false where scope='global';"
```

(Doing this through the dashboard writes an `audit_log` `edit_governance` row;
the raw SQL above does not — prefer the UI for a real demo.)

## What happens, step by step

| # | Node | What it does here | What you see |
|---|---|---|---|
| 1–9 | data_quality → … → explanation | **all run normally.** The pipeline still does the full analysis — CLIP match, policy eligible, low risk, no veto, Decision `approve` | a completely clean trace |
| 10 | **GovernanceGate** | reads `feature_flags` for the case's scope → `kill_switch = true` is the **first** branch checked → `kill switch is on — every case goes to human review` → **escalate**. The auto-approve branch is never reached | `route = escalate`, `kill_switch = true` in the node output |

The agreement data still accrues — you can see what the agent *would* have done.

## What to check afterwards

```bash
docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select parsed_output->>'kill_switch' ks, parsed_output->>'route' route
  from agent_runs where agent='governance' order by created_at desc limit 1;"
#  ks=true | route=escalate

docker compose exec -T postgres psql -U returnguard -d returnguard -c \
 "select parsed_output->>'decision' from agent_runs where agent='decision'
  order by created_at desc limit 1;"
#  approve   <-- the agent still recommended approve; the switch overrode it
```

## Why it matters

Graduated autonomy needs a fast, total, reversible "stop". The switch is checked
before every other rule, it's global, and turning it off is one click — trust you
can retract instantly is trust you can afford to extend.
