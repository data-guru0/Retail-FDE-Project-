# ADR-0009 — ContextForge as the MCP governance gateway

**Status:** accepted (M1), auth mechanism confirmed at M1 self-check

## Context
Each agent must reach tools (`get_order`, `check_policy`, `get_customer_history`,
`flag_ring`) under least privilege: the Image agent must not even *see*
`flag_ring`. We need per-agent tool scoping + an audit of every `list_tools` /
`call_tool`.

## Decision
Put **IBM ContextForge MCP Gateway** (`ghcr.io/ibm/mcp-context-forge:0.5.0`) in
front of the plain `mcp-server`. One **virtual server per agent** exposes only
that agent's allowed tools. The `mcp-server` itself has no auth — all authn/authz
lives in the gateway.

## Known unknown resolved: ContextForge ↔ Keycloak JWT
The OSS 0.5.0 build authenticates callers with **its own JWT** (`JWT_SECRET_KEY`),
not by validating arbitrary external Keycloak JWTs against Keycloak's JWKS.

**Chosen mapping:** the worker, holding each agent's Keycloak service-account
credentials, mints a **per-agent ContextForge token** at startup (1:1 with the
Keycloak SA `client_id`) and uses it for that agent's tool calls. The Keycloak SA
remains the identity of record (logged to `agent_runs.sa_subject`, in the app
`audit_log`, and in Langfuse spans); the ContextForge token is the transport
credential scoped to that agent's virtual server.

The invariant that matters — *Image agent cannot list or call `flag_ring`* — is
enforced by the virtual-server tool allow-list and verified in `verify_m4.py`
(`list_tools` has no `flag_ring`; a direct `call_tool` returns a real 403).

## Consequences
- No dependency on ContextForge gaining external-JWKS validation.
- Token minting is a small step in worker startup; tokens are short-lived.
- If a future ContextForge release validates Keycloak JWTs directly, drop the
  minting step — the allow-list config is unchanged.
