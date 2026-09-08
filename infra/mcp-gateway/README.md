# ContextForge (MCP gateway) configuration

ContextForge (`ghcr.io/ibm/mcp-context-forge:0.5.0`) is configured **at runtime by
`scripts/mcp_setup.py`**, not from a static file, because the per-agent virtual
servers reference tool ids that only exist after ContextForge has federated the
upstream `mcp-server`.

`scripts/mcp_setup.py` does, idempotently:

1. `POST /gateways` — register `mcp-server` (`http://mcp-server:8070/mcp/`,
   `STREAMABLEHTTP`) as an upstream; ContextForge federates its 4 tools.
2. `POST|PUT /servers` — create one **virtual server per agent**, each with an
   `associated_tools` allow-list:

   | agent | tools |
   |---|---|
   | intake | `get_order` |
   | policy | `check_policy` |
   | behavior | `get_customer_history`, `flag_ring` |
   | decision | `get_order`, `check_policy`, `get_customer_history` |
   | planner / **image** / critic / explanation | *(none)* |

3. writes the per-agent server ids to `scenarios/mcp_setup.json` + Vault
   (`secret/returnguard/mcp` → `agent_servers`).

## Auth (JWKS known-unknown)

The OSS 0.5.0 build authenticates callers with **its own JWT**
(`JWT_SECRET_KEY` env), not by validating external Keycloak JWTs against Keycloak's
JWKS. The worker mints a per-agent ContextForge token (1:1 with each Keycloak
service-account `client_id`) and uses it for that agent's tool calls. The Keycloak
SA stays the identity of record (logged to `agent_runs.sa_subject`, the app
`audit_log`, and Langfuse). The invariant that matters — *the Image agent's
virtual server lists no `flag_ring` and a direct `call_tool` 403s* — is enforced
by the allow-list above and asserted by `verify_m4.py` / `verify_security.py`.
