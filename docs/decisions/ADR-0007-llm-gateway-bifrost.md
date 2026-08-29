# ADR-0007 — Bifrost as the one LLM gateway (and only that)

**Status:** accepted (M1)

## Context
Every model call (Groq + OpenAI, chat + embeddings) needs: fallback chains,
per-agent spend caps, rate limits, model-access scoping, and uniform
cost/latency telemetry. Hand-rolling retry/fallback/circuit-breaker/budget code
across ten pipeline nodes is exactly the kind of thing that rots.

## Decision
Route **all** model traffic through **Bifrost** (`maximhq/bifrost:v2.0.0`), one
OpenAI-compatible endpoint. The worker's `llm.py` is a thin OpenAI SDK client
pointed at `http://bifrost:8080`. Bifrost owns:
- provider config + the fallback chain
  `llama-3.3-70b-versatile → openai/gpt-oss-120b → gpt-4o-mini`
- one **virtual key per agent** + one per service — budget, rate limit, allowed
  models per key
- Prometheus + OTel spans (fed to Langfuse)

## Per-agent virtual keys — what's real, what's deferred

`scripts/bifrost_setup.py` registers **one Bifrost virtual key per agent** with a
model/provider allow-list, a $3/month budget, and a 60 rpm / 200k tpm rate limit.
Verified at the gateway:

- `explanation` VK → `gpt-4o` : *"Model 'gpt-4o' is not allowed for this virtual key"*
- `image` VK → any Groq model : *"Provider 'groq' is not allowed for this virtual key"*

So the **model/provider least-privilege per agent is enforced by Bifrost** and the
budget/rate-limit tracking is live.

**Deferred:** in OSS Bifrost v2.0.0 a virtual key does **not** bind to the
env-based provider credentials from `config.json` — a *granted* model call under a
VK returns *"no keys found for provider"* (the VK→credential path appears to need
the Enterprise key-vault / IdP-managed keys, and `client.allow_direct_keys` did
not change this from the file). So the **inference hot path does not send the VK
by default** — it calls through Bifrost with the shared provider credentials
(still getting the fallback chain, telemetry, semantic cache, one OpenAI-compatible
endpoint). Opt in with `RG_USE_BIFROST_VK=1` once the binding is resolved.

The security guarantee CLAUDE.md asks for — *an agent can only use the models it
is granted* — is therefore also enforced **in our code**:
`worker/pipeline/models_config.py::assert_grant(agent, role)` runs on every
`chat()` / `chat_vision()` call and raises `PermissionError` for an ungranted
role. Deterministic, logged, and tested (`verify_security.py`). The VKs mirror the
same grants.

## Explicitly NOT used
Bifrost's Enterprise-only per-key **MCP tool filtering** + immutable audit. MCP
governance is ContextForge's job (ADR-0009). Bifrost is a model gateway, nothing
more.

## Consequences
- No custom resilience code in the pipeline.
- A Groq 400/outage produces a real OpenAI response via fallback — never a fake.
- Adding an agent = a grant entry in `models_config.AGENT_MODEL_GRANTS` + a
  virtual key (via `bifrost_setup.py`), not touching call sites.
