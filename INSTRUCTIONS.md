# ReturnGuard — full project description and build guide

This is the complete description of the project to build. Read this end to end before
writing anything. It describes what the system is, exactly how it should behave, what
data it needs to track, which technologies to use and why, the governance and security
rules that must hold, and every hard-won lesson from building this once already. It
deliberately does not prescribe file names, folder layout, or literal code — that's for
you to design well, using good judgment and the conventions in `CLAUDE.md`. Apply every
non-negotiable in `CLAUDE.md` throughout: nothing here is an excuse to mock, stub, fake,
or skip real verification.

Work through this as one continuous effort: build a piece, run it for real against the
live system, fix what's broken, move to the next piece. Don't stop to check in unless
you hit a genuine blocker (see "Open questions" near the end). Don't mark anything done
while any part of it is faked.

## What this is and why

A retailer gets a constant stream of return requests: "it arrived broken," "wrong
item," "changed my mind." Each one needs someone to check the order, check the return
policy, look at the evidence photo, weigh the customer's history, and decide: refund,
deny, or ask a follow-up question. It's repetitive, it's judgement-heavy, and a real
fraction of requests are outright fraud — faked damage photos, serial returners, rings
of accounts sharing an address or device.

Doing this entirely by hand is slow and expensive. Handing it entirely to an AI is
reckless — a model that can silently issue refunds is a model that can be tricked into
issuing refunds. The system to build is the middle path: a small pipeline of
specialized AI agents does the legwork and proposes an outcome, but the system only
acts within limits a human explicitly set, and every denial still requires a human to
confirm it.

This is a portfolio project demonstrating **Forward Deployed Engineer** work: one
company, one real operational process, replaced with a properly governed agent system —
not "an agent that answers questions." The parts that matter are the parts that are
hard in the field: governed autonomy, full observability, per-agent identity and least
privilege, scenario-driven validation of real behavior, a real business case, and a
handoff someone else could actually run. It is local-only — everything runs on one
machine, nothing is deployed anywhere, and the only ongoing cost is the handful of cents
per day in real LLM API calls.

## The end-to-end experience

**As a customer:** browse a small real product catalog (a few dozen real products
across several categories, real names/descriptions/prices/photos), add to cart, check
out with a mock payment step (a Luhn-validated fake card number — no real money ever
moves), and see the order in your order history. From any order, start a return: pick
the item, pick a reason, optionally add a note, and — for any reason that implies
visible damage or a wrong item — upload a real photo. Submit it and watch its status
update in near-real-time as the system reviews it: under review, then either a decision
or a reviewer's question, then (if approved) refunded. If your return is denied, you can
appeal with your own explanation, and a different reviewer than the one who denied it
will look again.

**As a reviewer:** a queue of cases needing a human, filterable by status (freshly
escalated, in review, waiting on a customer's answer, already decided). Claim a case,
watch a **live trace** of exactly what every agent did on it as it streams in (or
already did, if you're opening it after the fact) — not a canned animation, the real
sequence of tool calls and model outputs. See the evidence: the photo, the policy text
the system actually cited, the customer's history, any linked accounts. Approve, deny
(with an explicit confirmation step — denial should never be one accidental click), or
ask the customer a specific follow-up question and get notified when they answer, which
sends the case back through the full pipeline with their answer available to every
agent.

**As an admin:** everything a reviewer can do, plus: dial the system's autonomy up or
down (see "Automation levels" below), flip a global kill switch that forces every case
to a human regardless of anything else, edit the actual return policy text (which
creates a new version and re-embeds it — future cases use the new wording, past
decisions still show which version applied to them), and see a real analytics view:
hours and dollars saved versus an all-human baseline, cost per decision, agent-vs-human
agreement over time, and any account rings the system has found.

## The agent pipeline

A submitted return runs through a short pipeline of specialized steps, each one
producing a real, logged result before the next runs:

1. **Data-quality check.** Is there enough here to actually decide on — an item, a
   reason, a photo if the reason needs one, real reference data for the product being
   returned? If not, stop immediately and send it to a human with "insufficient data."
   Never let a later step guess its way past thin evidence.
2. **Planning.** Decide which of the following checks this particular case actually
   needs (a case with a bulletproof reason and no photo requirement doesn't need an
   image check, for instance).
3. **Intake.** Is the request internally coherent — does the free-text reason actually
   match the declared reason code, does the requested amount make sense?
4. **Policy.** Look up the actual, current return-policy text (a real, versioned,
   searchable document — not a rule buried in code) and decide eligibility strictly
   from it: is this within the return window, does this category have exceptions, does
   the condition described actually count as a defect. Record exactly which policy
   version was used for this decision.
5. **Image.** If a photo is involved, compare it to the product's real reference photo
   using a fast local similarity check; escalate genuinely borderline cases to a real
   vision-capable model call. Separately, screen the photo for signs it was AI-generated
   rather than a real camera photo. Both of these are *signals*, never a lone
   auto-denial by themselves.
6. **Behavior.** Score the account's real history — a trained model reading numeric
   features (return rate, account age, refund size, time since order) plus a language
   model reading the qualitative pattern — and separately check whether this account
   shares a shipping address, device, or payment fingerprint with any other account (a
   possible fraud ring). This step looks at the account's pattern, not just this one
   transaction.
7. **Decision.** Combine every signal above into one proposed outcome: approve, deny, or
   escalate, with a stated confidence and the reasoning behind it.
8. **Critic.** A second, independent look at the Decision step's own reasoning — it can
   veto the proposal and force the case to a human even if it would otherwise have
   qualified for automatic handling. A veto in *either direction* (too lenient or too
   harsh) still means "send this to a human," never "let the Critic overrule into a
   different automatic outcome."
9. **Explanation.** Write the plain-language reason that gets shown to the customer, the
   reviewer, and stored permanently for the audit trail and any later appeal.
10. **The governance gate.** The only place a decision is ever finalized. It reads the
    current automation level, any kill switch, and the numeric thresholds, and applies
    hard rules (below) before anything becomes real. Every case that doesn't clear every
    condition for automatic handling goes to a human — that's the safe default, not an
    edge case.

Every one of these steps writes a permanent record of what it did (which model, what it
was given, what it produced, how confident it was, how much it cost, how long it took)
and streams the same event live to anyone watching that case, so a person can watch the
reasoning happen rather than only seeing a final verdict.

## Automation levels and the hard governance rules

The system runs at one of four autonomy levels, settable globally or per product
category, and always starts at the most conservative one:

- **Shadow** (the default, where every real deployment starts): the full pipeline runs
  and its decision is logged, but a human does everything — nothing is finalized
  automatically. This is how you accumulate real agreement data at zero risk before
  trusting the system with anything.
- **Suggest**: functionally identical routing to shadow (a human still finalizes every
  case) — the only difference is the reviewer's screen opens pre-filled with the
  agent's proposed decision and reasoning, so they're checking its work instead of
  starting from a blank form.
- **Assist**: the system may auto-approve low-risk, high-confidence cases; everything
  else still goes to a human. Even so, a configurable percentage of the
  auto-approvals are still randomly sampled back into the human queue for spot-checking
  — a working default is around 10%.
- **Auto**: the same auto-approval behavior as Assist, without that random sampling.

Regardless of level, these rules always hold, with no admin override:

- A global **kill switch** immediately forces every case to a human, checked fresh on
  every single case (not cached from when a case was submitted) — turning it on affects
  cases already in flight the moment they reach the governance gate, and turning it off
  resumes automatic handling immediately, no restart required.
- **Automatic denial is structurally impossible.** A proposed denial always becomes an
  escalation with the denial pre-filled as a suggestion — only a human's explicit
  confirmation step can actually deny a return. This should be true even at 96%+ model
  confidence; the point is that a wrong denial costs a customer's trust and possibly a
  refund they were owed, so that asymmetry justifies never skipping the human step, no
  matter how confident the model is.
- **Automatic approval is bounded on every axis at once**: the estimated risk must be
  below a threshold, the confidence above another threshold, the Critic must not have
  vetoed, and any refund above a fixed high-value dollar amount always requires a human
  regardless of every other signal — a genuinely clean $329 return should escalate for
  sign-off purely because of its size, even at the most permissive automation level.
  Reasonable working defaults: a risk threshold around 0.30, a confidence threshold
  around 0.80, and a high-value line around $250.
- A denied return can be **appealed** by the customer with their own explanation. The
  appeal must route to a reviewer who is **not** the one who made the original decision
  — enforce this as a real constraint, not a UI convention: the original reviewer should
  get a real, explicit rejection if they try to act on their own appeal, and a case that
  was already finally decided should reject a second decision attempt outright.
- A reviewer can ask the customer a specific follow-up question instead of deciding
  blind. When the customer answers, the case genuinely re-enters the full pipeline (not
  just a note appended for a human to read) with the question and answer available to
  every agent, so their answer can actually change the outcome.
- If a case's processing crashes outright (a real exception, not a bad but valid model
  answer) a bounded number of times — three is reasonable — it should land in a
  permanent, visible "failed" record and get auto-escalated to a human, never retried
  forever and never silently dropped. Nothing about this should require a person to
  notice on their own that something went missing.
- Every human action (approve, deny, claim, edit policy, change the automation level,
  resolve an appeal) writes to the case record **and** an append-only audit trail in the
  same transaction — never just an in-memory UI update. When a human's decision
  disagrees with what the agent proposed, log that disagreement distinctly; it's the
  data that justifies (or argues against) moving up the automation ladder later.

## What data needs to exist

Design a real relational schema for at least the following (exact column names and
types are yours to design well; these are the facts that must be trackable, not a
literal table definition):

- **Users**, with a role (customer, reviewer, or admin).
- **Products**: name, description, category, price, stock, a reference photo.
- **Orders** and their line items: what was bought, at what price, when, the shipping
  address, a masked payment reference (never a real card number at rest).
- **Returns**: which order/item, the stated reason code and free text, the requested
  amount, current status (submitted, under review, escalated, approved, denied,
  refunded, waiting on customer info), the agent's proposed decision and confidence, the
  human's final decision if any, who claimed and who decided it and when, the refund
  state, and which policy version and which full pipeline run produced the current
  state.
- **Return photos**: a pointer to the stored object, its content type/size/hash — never
  the raw file path a browser could tamper with.
- **Policy documents**: versioned, with the version that was active at any point in time
  always recoverable, so a past decision's policy basis is never ambiguous even after
  later edits.
- **Every agent run**: which agent, which model, a hash of the input (never the raw
  input, to keep this table safe to inspect), the parsed output, a confidence score,
  token counts, real cost, real latency, which prompt version, which policy version if
  relevant, and a link back to the specific case and specific end-to-end pipeline run.
  Also a fine-grained event stream per run (one row per meaningful step: a node
  starting, a tool call, a node finishing) so a live trace can be reconstructed or
  replayed after the fact.
- **The append-only, tamper-evident audit log**: actor (human or agent), action, what
  entity it affected, a data payload, and enough of a hash-chain (each row referencing
  the previous row's hash) that the whole history can be independently re-verified for
  tampering at any time.
- **A durability record for "a case was submitted"** written in the same transaction as
  the return itself, so a crash between submission and the background worker picking it
  up can never silently lose a case — something has to reconcile this on a schedule.
  Similarly, a permanent record of any case that failed processing repeatedly.
- **Feature flags / governance settings**: automation level and kill switch (global and
  optionally per category), the QA-sampling percentage, and the numeric thresholds —
  read fresh on every single decision, never cached at startup.
- **Appeals**: the reason given, which reviewer it's routed to, which reviewer is
  explicitly excluded (the original decider), status, and outcome.
- **A reviewers table** distinct from the general users table, since a reviewer's
  identity needs to be referenced by claims, decisions, and appeal routing.
- **Fingerprints per account** (address/device/payment, each hashed, never stored raw)
  so that shared-fingerprint ring detection is a real, queryable join, not a heuristic
  guess.
- **A model registry** for the locally-trained risk model: a version, the metrics it
  achieved, and which version is currently in use — logged against every decision that
  used it.
- **Samples of agent-vs-human agreement**: every time a human's decision can be compared
  to what the agent proposed (an override, a QA-sampled auto-approval), record whether
  they agreed — this feeds the trend that justifies moving the automation level up or
  down.

## Technology choices and why

Use real, current-stable versions of each of these (re-check what's actually current at
build time — a plan's exact version numbers age quickly):

- **A relational database** (Postgres is a strong default) for everything above, with
  real foreign keys, constraints, and indexes — schema changes as real, ordered
  migrations, never a blanket "generate everything from the models" step.
- **A queue/cache** (Redis is a strong default) so a background worker can pick up
  submitted returns asynchronously, with a scheduled reconciliation job as the
  durability backstop for the "never lose a submission" requirement above.
- **A workflow/graph orchestration library for the agent pipeline** (LangGraph is a
  strong default) with a durable checkpointer so a run is resumable and independently
  inspectable, not just a chain of function calls with no persisted state of its own.
- **An LLM gateway sitting in front of every model call** (Bifrost or an equivalent) so
  you get one OpenAI-compatible endpoint for multiple providers, automatic fallback
  from one provider to another on a real outage, per-caller rate limits and budgets, and
  built-in cost/latency telemetry — this replaces any hand-rolled retry, fallback, or
  circuit-breaker code you'd otherwise be tempted to write yourself. Every model call
  should name an abstract *role* ("fast," "reasoning," "deep," "vision") resolved to an
  actual model id through config, never a literal model string scattered through the
  pipeline code — that's what makes swapping providers or models later a config change,
  not a code change.
- **A fast, cheap model tier** for high-volume, low-depth agents (intake, planning,
  policy, behavior, an initial decision pass) and a **slower, more careful tier** for
  the agents doing genuine judgment (critic, explanation, and vision checks) — routed
  through the gateway above, with a real fallback path from the fast/cheap provider to
  the careful one if the cheap provider is unavailable.
- **A vector database** (Qdrant or equivalent) purely for the policy-document
  retrieval — don't reuse the relational database's own vector extension if one is
  available; keeping this as a separate, purpose-built store is a deliberate choice.
- **A governed tool-calling layer for anything an agent can "do"** (look up an order,
  check policy, pull a customer's history, check for a fraud ring): a small real tools
  service, sitting behind a gateway that enforces **one scoped virtual identity per
  agent**, exposing to each agent only the specific tools it's allowed to call, auditing
  every tool listing and every call. The concrete, load-bearing test of this whole
  layer: the image-comparison agent should be grantable **zero tools and zero model
  roles beyond vision** — no combination of a compromised or confused image agent should
  ever be able to reach the fraud-ring-check tool, and this should be provable by
  actually trying it and getting a real permission error back, not just by omission.
- **A policy-as-code engine** (Open Policy Agent or equivalent) as the actual place
  auto-approve/escalate decisions and per-agent tool/model grants are evaluated — real
  policy, not an `if` statement buried in application code, with its own unit tests and
  a fail-closed default if the policy engine is ever unreachable.
- **Real identity and access** (Keycloak or an equivalent OIDC provider): customer,
  reviewer, and admin roles for humans, and — separately — one distinct, narrowly-scoped
  service-account identity per agent, so "the policy agent" and "the image agent" are
  never interchangeable from an access-control point of view.
- **Local, CPU-only models for anything that doesn't need a hosted API call**: a fast
  image-similarity model (CLIP or equivalent) as the first-pass image check, an
  AI-generated-image detector chosen by actually running a small real bake-off of two or
  three real candidates and keeping the best empirical performer (never picked in
  advance without evidence), and a trained tabular classifier (gradient-boosted trees
  with calibrated probabilities is a strong default) for the numeric behavior-risk
  score, trained on a realistic synthetic dataset with real injected fraud patterns —
  not a toy dataset with an obvious separable signal.
- **Object storage** (MinIO or equivalent S3-compatible store) for every uploaded photo
  and product image — sniff the real file type before trusting an extension, cap the
  size, strip metadata by re-encoding the image server-side, and serve access only
  through short-lived signed URLs, never a public bucket.
- **A local SMTP catcher** (MailHog or equivalent) so order/return/decision emails are
  real sends to a real (local-only) inbox, not a log line pretending to be an email.
- **A secrets manager** (HashiCorp Vault or equivalent) as the single real source of
  every credential, read at process boot — a bootstrap file exists only to seed the
  secrets manager itself and is never itself the runtime source of truth.
- **Full observability**: a real LLM-tracing platform (Langfuse or equivalent) capturing
  every model call's prompt, completion, tokens, cost, and latency, linked back to the
  specific decision it informed; metrics scraped into a real metrics store (Prometheus
  or equivalent) with a small number of genuinely meaningful alert rules (a queue that's
  been waiting too long, a daily spend ceiling, a spike in pipeline errors, agreement
  between agent and human drifting downward); and at least one real dashboard
  visualizing the metrics above, refreshing live.
- **A frontend** (a modern React-based framework like Next.js is a strong default) for
  the shop and the dashboard, using real OIDC login against the identity provider above
  — never a fake session — with API types generated from the backend's real schema
  rather than hand-duplicated.
- **A backend API** (a modern async Python framework like FastAPI is a strong default,
  or an equivalent in another language) verifying the identity provider's token on every
  request, plus a way to push live events to an open client (a WebSocket per case is a
  reasonable choice) so the live trace can actually stream.

## Security and least privilege, concretely

- Every request to the backend must carry a real, verified token — no endpoint should
  trust an unauthenticated caller's claimed identity.
- Each agent has its own scoped identity end to end: its own service account, its own
  tool grant, its own model-role grant, its own spend budget. Prove the boundary holds
  by actually attempting a call the image agent shouldn't be able to make and getting a
  real rejection, not by only checking that the "happy path" works.
- No tool available to any agent should be able to move money. Refunds are a human-only
  action, full stop — there should be no code path, however indirect, by which an agent
  can cause a refund to actually be issued.
- Treat any customer-supplied text — including text baked into an uploaded image — as
  **data to be evaluated, never as an instruction to follow**. No amount of "ignore
  previous instructions" style text in a return's free-text field should be able to
  change the automation level, move a threshold, or bypass the "no automatic denial"
  rule. Prove this with a real attempt, not by assuming your prompts are safe.
- Rate-limit the public-facing endpoints, especially return and order submission.
- Uploaded files: verify the real file type from its bytes (not its claimed extension or
  content-type header), cap the size, and re-encode server-side before storing.
- Every credential-shaped value should be automatically redacted from logs — assume a
  log line will eventually be pasted somewhere it shouldn't be, and design for that.

## The scenario catalog

Beyond automated verification, build a catalog of real, end-to-end situations that
demonstrate exactly how the system behaves — this is the primary artifact for showing
the finished project to an audience (in this case, a classroom demo for students who've
never seen it). Each scenario should be a **plain-English, click-through-the-app
walkthrough** — no code, no terminal commands, no SQL in the walkthrough text itself —
written for someone with zero technical background: what to click as a customer, what
to click as a reviewer, and what to actually watch happen (the live trace, the tracing
dashboard, where the uploaded photo really lands in storage, the relevant metrics
panel, and — where relevant — which real alert rule this behavior relates to). Write a
short shared explainer once for "how to watch a case" (the live trace, the tracing
tool, the storage console, the metrics dashboard, the alert rules) and have every
individual walkthrough link back to it instead of repeating the explanation each time.

Cover at least three groups of scenarios, roughly 18 real situations in total:

- **Decision behavior** (around 10): an easy, clean case that auto-approves; a photo
  that doesn't match what was actually sold; a photo that's plausibly AI-generated; an
  ambiguous case (e.g. normal wear mistaken for damage) that hinges on a nuanced policy
  reading rather than a hard rule; an account with a high prior return/denial rate;
  two accounts sharing a fingerprint; a refund large enough to trip the high-value rule
  even though everything else about it is clean; a request outside the return window
  (which should propose a denial that still requires human confirmation); an
  incomplete request that the data-quality check correctly refuses to guess on; and a
  prompt-injection attempt in the free-text reason.
- **Governance controls** (around 5): the kill switch forcing every case to a human;
  the same clean case walked through all four automation levels back to back, showing
  the outcome change at each one; an admin editing the policy text and a later case
  immediately reflecting the new wording while an earlier decision still shows the old
  version it actually used; a reviewer's follow-up question and the customer's answer
  genuinely re-triggering the pipeline; and the full deny → appeal → different-reviewer
  → resolution chain, including what happens if the original reviewer tries to act on
  their own appeal.
- **Operational** (around 3): a case that fails processing repeatedly and lands in a
  visible failed state instead of retrying forever; a real outage of the primary LLM
  provider that still produces a real decision via the fallback provider; and a burst of
  return volume that makes the queue grow rather than anything crashing or losing a
  job. These three necessarily need one real operator action each (something has to
  actually break, or a load test has to actually run) since a real crash, outage, or
  spike can't come from filling out a customer-facing form correctly — say so plainly
  in the walkthrough rather than pretending it's just another click-through.

Every walkthrough must be run for real against the live system while it's written, and
must quote real, actual output from that run — never an invented or "typical" example.
Language-model wording will vary a little between runs; hedge only the parts that
genuinely vary, and make sure the decision, the route, and which agents fired are what
actually happened. There is deliberately no script that runs this catalog for you —
walking it by hand, live, is the entire point.

## What "done" looks like

There is no pytest/Playwright/eval-metric suite. Instead:

- A handful of plain scripts that drive the real, running system over real HTTP/WebSocket
  calls and assert against real database and storage state — one script's worth of
  checks per major capability area (the stack itself is healthy; the shop and auth
  flow works end to end with a real upload; a single agent call produces a real,
  traceable decision; the full multi-agent graph produces a correct outcome with every
  tool call properly scoped; the audit log's hash chain is genuinely unbroken; a
  security-focused check that a real injection attempt can't escalate privilege or force
  an approval; a full reviewer-workflow walkthrough including override, appeal, and
  refund settlement; a final check that a written README's claims and URLs actually
  hold up against the live system). One single command should run every one of these in
  sequence and report a clear pass/fail summary.
- The entire scenario catalog above, walked by hand against a genuinely fresh rebuild —
  not the environment you've been iterating on all session — before calling this done.
  Tearing everything down to a clean slate and rebuilding from nothing occasionally
  during the build catches drift that a long-lived dev environment will hide (a local
  model cache surviving a container restart when it shouldn't have, a config change that
  only took effect because a service happened to already be running, and so on).
- A README written only after the system is real and running, documenting only commands
  and scenarios you personally just executed — never a description of a plan. It should
  let someone who has never seen this project follow it from an empty machine to a
  working demo, in plain language for the non-technical parts (what problem this solves,
  how the pipeline works, what the autonomy levels mean) and exact copy-pasteable
  commands for the technical parts. Verify this literally, not just in your head: delete
  your local dependency caches and built artifacts and follow your own instructions from
  scratch.
- A short decision record for every real architectural choice, written at the time you
  make the choice — not deferred to the end, where it reliably doesn't happen.
- One last full pass over the whole codebase specifically hunting for anything mocked,
  stubbed, faked, or hardcoded, checked against every non-negotiable in `CLAUDE.md` one
  more time before calling this finished.

## Open questions to actually resolve, not guess past

- Whether your chosen MCP/tool-gateway product validates your identity provider's
  tokens directly, or only its own issued tokens. If it's the latter, mint a
  gateway-specific token per agent, mapped one-to-one from that agent's real identity —
  either way, the "the image agent still can't reach a tool it's not granted" invariant
  must hold and be provable.
- Which AI-image detector actually performs best — resolve this empirically with a real
  small labeled sample, not by picking one in advance. Two things to know going in: the
  real generation of convincing fake samples for that test will need a real image-
  generation model call through your gateway (make sure the specific image-gen model you
  use is actually enabled for that provider in your gateway's configuration before
  running the test, or it will fail outright); and one real run of this kind of bake-off
  found roughly a 90%+ accuracy achievable, so treat a result meaningfully worse than
  that as a signal to try another candidate.

## Lessons from building this once already — apply directly, don't rediscover them

- **A fast/cheap model provider's exact catalog of available model ids can change
  completely between when a plan is written and when it's built.** Don't hardcode a
  specific model id from an older plan into your reasoning — check what that provider
  actually serves right before you wire it up, and expect that an entire model family
  can disappear from a catalog, not just get a deprecation warning.
- **Any script that creates a real account with a real elevated role purely to test
  something must clean that account up when it finishes — success or crash.** A real
  bug: a verification script created synthetic reviewer/admin accounts with random,
  never-recorded passwords and left them permanently active. Real appeal-routing logic
  (which picks a random *other* reviewer) later handed a real appeal to one of these
  unreachable accounts, permanently stranding it — nobody could ever log in to resolve
  it. Deactivate every such test-created account in a cleanup step that runs even if the
  rest of the test fails.
- **A language model asked to do exact date or threshold arithmetic will occasionally
  get it backwards on an otherwise-identical rerun** (e.g. calling 38 days "outside" a
  45-day window). A well-designed governance layer catches the downstream effect so
  nothing unsafe happens, but if a numeric comparison needs to be airtight, compute it
  in code and give the model only the yes/no result to reason about, not the arithmetic.
- **A brand-new test account's very first action can look statistically "risky" purely
  from having zero history** — a 100% return rate looks alarming when the denominator
  is one. This is correct model behavior, not a bug, but if a demo scenario needs to
  reliably land on the clean/auto-approve path, seed that account with a believable
  history of prior orders (with no returns) first, rather than being surprised when a
  fresh account escalates.
- **A local, self-hosted database driver may use `%` for its own parameter placeholders
  even in raw SQL mode** — a literal `%` inside a wildcard search pattern written
  directly into the query string will collide with that and throw a confusing error.
  Always pass such a pattern as a bound parameter, never inline it.
- **The first time a locally-run ML model actually gets used, it may need to download a
  large weight file** (on the order of a gigabyte or more) before it can run — expect
  that specific run to be genuinely slow (minutes, not seconds), make sure whatever
  caches that download survives an ordinary container restart, and don't mistake this
  one-time cost for a performance regression.
- **A background worker that starts before the database schema is ready is fine, if it's
  set to auto-restart** — it'll fail once against a table that doesn't exist yet and
  recover cleanly once migrations land moments later. Don't chase that transient crash
  log as if it were a real bug.
- **If the wiring between agents and their governed tools/models isn't fully set up yet,
  failures can be silent rather than loud** — a per-call error handler can catch a
  failed tool call and let the agent quietly fall back to a weaker heuristic instead of
  crashing. This means a broken setup can look like "the system works, the decisions
  just seem a little thin" rather than an obvious error. If agent reasoning ever looks
  suspiciously generic, check whether its tool calls are actually succeeding before
  assuming the model itself is the problem.
- **Decision records (architecture decision records / ADRs) are the single most likely
  "documentation" requirement to get silently skipped**, because nothing forces them the
  way a broken build forces a code fix. Write each one immediately when you make the
  real decision, not as a batch at the end — a batch at the end reliably doesn't happen.
