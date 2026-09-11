# Scenario 17 — Groq goes down → the pipeline falls back to OpenAI

**Route:** unaffected (still a real decision) · **Group:** operational

See [00 — Watching a case live](00-watching-a-case-live.md) first.

## What this shows

Groq serves the "fast" and "reason" role agents (planner, intake, policy,
behavior, decision) for speed and cost; OpenAI is the documented fallback for
those same roles (`worker/pipeline/models_config.py`). If Groq is unreachable
or rejects the key, the case still gets decided — on a different, real model
— instead of failing.

## This one also needs an operator action

Like [scenario 16](16-pipeline-crash-dead-letter.md), you can't make a real
provider outage happen from the shop UI — you have to actually take Groq
away, the way a real incident would. **Never do this against a production
key.** Bifrost reads `GROQ_API_KEY` straight from `.env` at container start —
the backend and worker never need to be touched, since they always call the
fixed Bifrost URL regardless of which provider actually answers.

1. Back up `.env` first (so you can restore the exact original byte-for-byte,
   not just retype the key from memory):
   ```bash
   cp .env .env.bak
   ```
2. Edit `.env` and change the `GROQ_API_KEY` line to an obviously invalid
   value, e.g. `GROQ_API_KEY=invalid_for_this_demo`.
3. Recreate only the Bifrost container so it picks up the broken key — this
   restarts just the LLM gateway, nothing else:
   ```bash
   docker compose up -d --force-recreate bifrost
   ```
4. As a customer, submit any return normally. Watch what model each agent
   actually used in the reviewer dashboard's **Agent reasoning** section (see
   the table below).
5. Restore the real key and bring Bifrost back:
   ```bash
   cp .env.bak .env
   docker compose up -d --force-recreate bifrost
   ```

## What happens behind the scenes

Real result from a live run, key genuinely broken, one full case submitted:

| Agent (normally Groq) | Model that actually ran | |
|---|---|---|
| planner | `gpt-4o-mini-2024-07-18` | normally `openai/gpt-oss-20b` via Groq |
| intake | `gpt-4o-mini-2024-07-18` | normally `openai/gpt-oss-20b` via Groq |
| policy | `gpt-4o-mini-2024-07-18` | normally `openai/gpt-oss-120b` via Groq |
| behavior (LLM read) | `gpt-4o-mini-2024-07-18` | normally `openai/gpt-oss-120b` via Groq |
| decision | `gpt-4o-mini-2024-07-18` | normally `openai/gpt-oss-120b` via Groq |

Every one of those five nodes still produced a real, complete `agent_runs`
row — real tokens, real cost, real confidence — and the case reached a real
final route (`escalate`, in our run). Restoring the real key and restarting
Bifrost brought Groq back immediately: the very next case's `planner` and
`intake` nodes showed `openai/gpt-oss-20b` again.

## In the reviewer dashboard

Nothing about the case *looks* different — same fields, same badges. The only
visible trace of the outage is the **model** name shown next to each agent in
**Agent reasoning**: `gpt-4o-mini-2024-07-18` where you'd normally see a
`openai/gpt-oss-*` id.

## Watch it live

- **Langfuse:** the generations for this case show the OpenAI model and its
  (slightly higher) real cost — compare the same case type's usual Groq-priced
  cost on a normal run.
- **Grafana → LLM spend:** a brief, visible bump for exactly the cases decided
  during the outage window, since OpenAI's fallback model costs more per call
  than Groq's.
- **Bifrost's own dashboard** (`http://localhost:8090`) shows the failed
  provider calls and the gateway's routing decisions in its own metrics —
  worth a look alongside Langfuse and Grafana, since it's the layer that
  actually made the fallback possible.

## Why it matters

A hand-rolled retry-and-fallback in application code is exactly the kind of
plumbing this project deliberately doesn't write — Bifrost's job is to make
one provider's outage invisible to the pipeline's correctness, while still
being fully visible in cost and observability. The agents don't know or care
which provider answered; the governance rules and the audit trail don't
change either.
