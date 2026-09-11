# ReturnGuard — persistent instructions

ReturnGuard is a governed multi-agent AI system that reviews e-commerce return/refund
requests: a shop plus a reviewer dashboard, backed by a pipeline of specialized agents
that auto-clear obviously-legitimate returns and route anything risky, unclear, or
expensive to a human. It's a portfolio project demonstrating Forward Deployed Engineer
work — governed autonomy, full observability, per-agent identity, real scenario
validation, a business case — not a chatbot demo. It runs entirely locally via Docker
Compose; nothing is deployed anywhere. The only things that cost money are the Groq and
OpenAI API calls.

**Read `INSTRUCTIONS.md` before any non-trivial work on this project** — it holds the
full description of what the system is, how it should behave, the complete data model,
the governance and security rules, and every hard-won lesson from building this before.
This file only holds what to keep in mind on every single turn, so keep it short.

## Non-negotiables — never violate these

1. **Nothing is mocked, stubbed, faked, or hardcoded, ever.** Every agent call is a real
   LLM call, every database write is real, every uploaded file really lands in object
   storage, every "AI decision" comes from an actual model response. If a feature can't
   be built for real yet, it does not exist yet — never a placeholder returning a
   canned response.
2. Every action a person takes in the dashboard (approve / deny / request info / claim /
   appeal / edit policy / change the automation level) must actually write to the
   database and to an append-only audit log — not just update the UI locally.
3. Every agent decision is traceable: which agent, which model, what input (hashed),
   what output, what confidence, what prompt version, which policy version, tokens,
   cost, and latency — logged for real, every time.
4. **Auto-deny never ships without a human confirming.** Auto-approve is fine, only for
   low-risk, high-confidence cases, and only when the current automation level permits
   it. The system starts in the most conservative mode and only moves up deliberately.
5. Nothing runs on paid cloud infrastructure and nothing is deployed anywhere — local
   Docker Compose only. Local models run on the local CPU. The only paid dependencies
   are the Groq and OpenAI API calls.
6. Secrets are never hardcoded, never committed, never logged — they live in a real
   secrets manager, read at boot.
7. Use the latest stable release of every dependency at the moment you actually add it —
   check for real, don't trust a version from memory or from when you last scaffolded.
8. **If you hit a real blocker** — a missing credential, an ambiguous requirement, a
   library that doesn't do what's assumed — stop and ask. Don't paper over it with a
   fake implementation.
9. Never write a setup instruction, a README claim, or a demo/scenario description that
   you haven't personally just run and confirmed for real.
10. **No pytest, no Playwright, no eval-metric harness.** Verify by running the real app
    and reading real output — plain scripts that drive the live system over HTTP/WS and
    assert against real database/storage state. The scenario catalog is a set of
    **manual, code-free, click-through-the-app walkthroughs** meant for a non-technical
    audience — never an automated runner script.

## Apply these directly — found the hard way, don't rediscover them

- Any script that creates a real account with a real reviewer/admin role purely for
  testing must deactivate that account when the test finishes, success or failure —
  otherwise it can pollute real routing logic later (e.g. a real support case getting
  permanently assigned to an unreachable test account nobody can log into).
- Don't trust a language model to do exact date or threshold arithmetic reliably across
  runs. If a numeric comparison must be airtight, compute it in code and hand the model
  only the result to reason about and narrate — not the arithmetic itself.
- A brand-new account's very first action can statistically look "risky" purely from
  having no history — that's correct model behavior, not a bug. If a demo needs to
  reliably take the clean path, give the account a believable history first.
- When building a raw SQL query with a `%`-based wildcard pattern through a driver that
  also uses `%` for its own parameter placeholders, pass the pattern as a bound
  parameter — never inline it into the query string.
- Re-verify third-party model or API catalog names at the moment you actually use them.
  A provider's available models can change completely between when something was
  planned and when it's built — don't assume a model id from memory still exists.

## How to work in this codebase

- Prefer the standard library and dependencies already in use over adding new ones.
  Build the minimum that is actually real for the current requirement — no speculative
  abstractions, no config knobs for a value that never changes.
- Every schema change is a real, ordered migration — never a blanket "create everything"
  step.
- Any prompt sent to a model is version-controlled, and the exact version used is logged
  with every decision that used it.
- One task entrypoint for the whole project (e.g. a single `make <target>` per
  operation) — never a memorized sequence of raw commands.
- Structured logging with a correlation id that follows one request end to end, with
  secrets redacted automatically.
- Lint, format, type-check, and scan for secrets before considering any change done.
- Write a short decision record for every real architectural choice, at the time you
  make it — don't defer this to "later," it tends to never happen.
