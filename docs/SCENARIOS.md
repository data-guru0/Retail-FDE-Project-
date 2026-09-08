# ReturnGuard — Scenario Catalog

The single source of truth for how ReturnGuard behaves in every situation it is
meant to handle. **Not a metric harness** — no accuracy/precision/recall score,
no labelled test file, no regression gate. Each scenario is a real end-to-end
situation with its own step-by-step walkthrough under [`docs/scenarios/`](scenarios/):

> **the situation → the exact command (or UI steps) → what every agent node does →
> what to check in the DB / audit log / dashboard / Langfuse afterwards**

Every walkthrough is run against the real, running system and confirmed to match
its description. LLM wording varies run to run, so each asserts the **decision +
route + which agents fired + resulting rows**, never verbatim text.

## The walkthroughs

| # | Scenario | Route | Run it | `[demo]` |
|---|---|---|---|---|
| [01](scenarios/01-matching-photo-auto-approve.md) | Matching photo | **auto-approve** | `python scripts/run_scenarios.py A0` | ✅ |
| [02](scenarios/02-mismatched-photo.md) | Mismatched photo | escalate | `python scripts/run_scenarios.py A2` | ✅ |
| [03](scenarios/03-ai-faked-damage-photo.md) | AI-generated damage photo | escalate | manual (AI image) | ✅ |
| [04](scenarios/04-serial-returner.md) | Serial returner | escalate | manual (`_seed_history`) | ✅ |
| [05](scenarios/05-fraud-ring.md) | Fraud ring (shared fingerprint) | escalate | `python scripts/run_scenarios.py A5` | ✅ |
| [06](scenarios/06-high-value-within-policy.md) | High value within policy | escalate | `python scripts/run_scenarios.py A6` | |
| [07](scenarios/07-outside-return-window.md) | Outside the return window | escalate (proposed deny) | `python scripts/run_scenarios.py A7` | |
| [08](scenarios/08-incomplete-request-data-quality.md) | Incomplete request | escalate ("insufficient data") | manual (API) | |
| [09](scenarios/09-prompt-injection.md) | Prompt injection in the reason | escalate | `python scripts/run_scenarios.py A10` + `verify_security.py` | ✅ |
| [10](scenarios/10-kill-switch.md) | Kill switch on | escalate (every case) | manual (Governance page) | |
| [11](scenarios/11-automation-level-ladder.md) | Automation ladder: shadow vs assist | escalate → auto-approve | `run_scenarios.py A1` then `A0` | ✅ |
| [12](scenarios/12-reviewer-override-and-appeal.md) | Reviewer override + appeal (COI guard) | human decision | `python scripts/verify_m5.py` | |

## Run them in bulk

Each scenario has an **id** (`A0`, `A1`, `A2`, `A5`, `A6`, `A7`, `A10`) used on the
command line. The ids are not contiguous — they line up with the walkthrough
numbers above, and the gaps are the scenarios that are a manual checklist rather
than automated.

```bash
# Run every AUTOMATABLE scenario end to end through the real pipeline (~2 min).
# Covers walkthroughs 01, 02, 05, 06, 07, 09, 11. Each one places a real order,
# submits a real return, drives the multi-agent pipeline, and asserts the
# resulting decision + route + which agents fired + the DB / audit rows.
python scripts/run_scenarios.py

# Run only the audience subset marked [demo]: A0 (auto-approve), A2 (mismatched
# photo), A5 (fraud ring). This is what you walk through when showing the project.
python scripts/run_scenarios.py --demo

# Run only the scenarios you name (here: fraud ring + outside-the-window).
python scripts/run_scenarios.py A5 A7

# Run EVERYTHING: all scripts/verify_*.py plus this whole catalog, in sequence.
# The complete proof that nothing is mocked. ~10 min.
python scripts/smoke.py
```

## Operational behaviours (covered by dedicated scripts, not walkthroughs)

| Behaviour | Command — and what it does | Asserts |
|---|---|---|
| Pipeline crashes 3× → dead-letter → auto-escalate | `python scripts/verify_m3_dlq.py` — flips the worker's documented fault-injection env var so `review_return` raises a real exception, submits a return, watches it fail 3× | `dead_letter` row (`attempts>=3`), `status=escalated`, a `dead_letter` trace event, no infinite retry |
| Groq error → Bifrost falls back to OpenAI | observed in `verify_m3` history — no dedicated script; Bifrost owns the fallback chain | `agent_runs.model` shows the OpenAI model; the decision is still a real completion |
| ~20× return volume → queue holds | `python scripts/loadtest.py` (`make loadtest`) — fires ~20× the normal number of returns at once | the arq queue drains, no lost jobs (outbox reconciles), p95 reported by the script |
| Full agent graph + ContextForge tool calls | `python scripts/verify_m4.py` — submits one return and drives every node of the graph | every node writes `agent_runs`; `intake/policy/behavior` call their MCP tools via the gateway (`ok=true`) + `call_tool` audit rows |
| Per-agent least privilege under attack | `python scripts/verify_security.py` — submits a return whose free-text and photo carry a prompt-injection payload, autonomy forced on | Image agent has zero MCP tools + can't use the `reason` model role; no money-mutating tool; no auto-approve; real decision row |
