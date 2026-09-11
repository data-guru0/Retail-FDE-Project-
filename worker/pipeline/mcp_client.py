"""Per-agent MCP tool access, through ContextForge.

Every tool call an agent makes goes through ContextForge's per-agent **virtual
server** endpoint (`/servers/<agent server id>/mcp`) with a per-agent bearer
token (1:1 with that agent's Keycloak service-account client_id).

Three layers of least privilege:
  1. **OPA** — `is_granted()` asks `data.returnguard.authz.allow_tool`
     (`infra/opa/authz.rego`). This is the enforced check on the hot path.
  2. `AGENT_TOOL_GRANTS` here — the offline mirror of the .rego map, used as a
     fail-closed fallback when OPA is unreachable. Keep the two in sync.
  3. ContextForge's virtual-server `associated_tools` allow-list — the Image
     agent's server exposes zero tools in `tools/list`.

(OSS ContextForge 0.5.0 filters `tools/list` but not `tools/call`, so layers 1-2
are what actually block an out-of-scope call — verified in `verify_security.py`.)
"""
from __future__ import annotations

import json
import threading

import httpx
import structlog

from pipeline import opa

log = structlog.get_logger()

# Offline mirror of infra/opa/authz.rego `tool_grants` (fail-closed fallback).
AGENT_TOOL_GRANTS: dict[str, set[str]] = {
    "intake": {"get_order"},
    "policy": {"check_policy"},
    "behavior": {"get_customer_history", "flag_ring"},
    "decision": {"get_order", "check_policy", "get_customer_history"},
    "planner": set(),
    "image": set(),
    "critic": set(),
    "explanation": set(),
}

_lock = threading.Lock()
_cfg: dict | None = None
_tokens: dict[str, str] = {}


def _config() -> dict:
    """{gateway_url, jwt_secret, agent_servers:{agent: server_id}} from Vault.

    Only cached once `agent_servers` is populated — a beginner runs `make up`
    (starts this worker) *before* `make m4-setup` (writes `agent_servers` via
    `scripts/mcp_setup.py`). Until it's real, re-read every call, and bust the
    settings LRU cache so we actually see the fresh Vault value without a
    worker restart.
    """
    global _cfg
    if _cfg is not None:
        return _cfg
    with _lock:
        if _cfg is not None:
            return _cfg
        from pipeline.settings import _read

        mcp = _read("mcp")
        servers = mcp.get("agent_servers") or "{}"
        parsed = json.loads(servers) if isinstance(servers, str) else servers
        if not parsed:
            _read.cache_clear()          # settings cached a pre-m4-setup read
            mcp = _read("mcp")
            servers = mcp.get("agent_servers") or "{}"
            parsed = json.loads(servers) if isinstance(servers, str) else servers
        cfg = {
            "gateway_url": mcp["gateway_url"],
            "jwt_secret": mcp["jwt_secret"],
            "agent_servers": parsed,
        }
        if cfg["agent_servers"]:
            _cfg = cfg
        return cfg


def _token(agent: str) -> str:
    """A per-agent ContextForge bearer token (HS256, 1:1 with the agent's Keycloak
    service-account client_id — the identity of record). Signed with the gateway's
    JWT secret, same as `mcpgateway.utils.create_jwt_token` would."""
    if agent not in _tokens:
        with _lock:
            if agent not in _tokens:
                import time

                import jwt

                _tokens[agent] = jwt.encode(
                    {"username": f"agent-{agent}", "exp": int(time.time()) + 3600},
                    _config()["jwt_secret"], algorithm="HS256",
                )
    return _tokens[agent]


def is_granted(agent: str, tool: str) -> bool:
    """OPA decides; if OPA is unreachable, fall back to the offline mirror."""
    return opa.allowed(
        "returnguard/authz/allow_tool", {"agent": agent, "tool": tool},
        offline=tool in AGENT_TOOL_GRANTS.get(agent, set()),
    )


def assert_grant(agent: str, tool: str) -> None:
    if not is_granted(agent, tool):
        raise PermissionError(
            f"agent '{agent}' is not granted MCP tool '{tool}' "
            f"(granted: {sorted(AGENT_TOOL_GRANTS.get(agent, set())) or 'none'})"
        )


def call(agent: str, tool: str, **arguments) -> dict:
    """Call `tool` as `agent`, through that agent's ContextForge virtual server.
    Raises PermissionError if the agent isn't granted the tool."""
    assert_grant(agent, tool)
    cfg = _config()
    sid = cfg["agent_servers"].get(agent)
    if not sid:
        raise RuntimeError(f"no ContextForge virtual server for agent '{agent}' "
                           f"(run scripts/mcp_setup.py)")
    url = f"{cfg['gateway_url']}/servers/{sid}/mcp"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": f"returnguard-tools-{tool.replace('_', '-')}",
                       "arguments": arguments}}
    r = httpx.post(
        url,
        headers={"Authorization": f"Bearer {_token(agent)}",
                 "Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
        json=body, timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"MCP {tool} error: {data['error']}")
    text = data["result"]["content"][0]["text"]
    log.info("mcp.call", agent=agent, tool=tool, server=sid[:8])
    return json.loads(text)
