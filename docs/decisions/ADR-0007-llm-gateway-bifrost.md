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

## Explicitly NOT used
Bifrost's Enterprise-only per-key **MCP tool filtering** + immutable audit. MCP
governance is ContextForge's job (ADR-0009). Bifrost is a model gateway, nothing
more.

## Consequences
- No custom resilience code in the pipeline.
- A Groq 400/outage produces a real OpenAI response via fallback — never a fake.
- Adding an agent = adding a virtual key, not touching call sites.
