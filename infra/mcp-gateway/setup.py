"""Configure IBM ContextForge: register the plain mcp-server as an upstream
gateway, then create one **virtual server per agent** exposing only that agent's
allowed tools. Writes the server ids to Vault (secret/returnguard/mcp) so the
worker can reach each agent's scoped endpoint.

Least-privilege map (CLAUDE.md):
  intake      -> get_order
  policy      -> check_policy
  behavior    -> get_customer_history, flag_ring
  decision    -> get_order, check_policy, get_customer_history
  planner/image/critic/explanation -> (no tools)

The invariant verify_m4 checks: the Image agent's virtual server lists NO
flag_ring and a direct call_tool returns a real error.

Run: make mcp-setup   (docker compose run --rm mcp-setup)  — see Makefile.
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

GW = os.getenv("CONTEXTFORGE_URL", "http://mcp-gateway:4444")
UPSTREAM = os.getenv("MCP_SERVER_URL", "http://mcp-server:8070/mcp")
ADMIN_USER = os.getenv("BASIC_AUTH_USER", "admin")
ADMIN_PASS = os.environ["ADMIN_PASS"]

ALLOW = {
    "intake": ["get_order"],
    "policy": ["check_policy"],
    "behavior": ["get_customer_history", "flag_ring"],
    "decision": ["get_order", "check_policy", "get_customer_history"],
    "planner": [],
    "image": [],
    "critic": [],
    "explanation": [],
}


def _client() -> httpx.Client:
    # ContextForge accepts HTTP Basic for the admin API and mints its own JWT.
    tok = httpx.post(
        f"{GW}/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=15,
    )
    headers = {}
    if tok.status_code == 200 and "access_token" in tok.text:
        headers["Authorization"] = f"Bearer {tok.json()['access_token']}"
        return httpx.Client(base_url=GW, headers=headers, timeout=30)
    # fall back to basic auth
    return httpx.Client(base_url=GW, auth=(ADMIN_USER, ADMIN_PASS), timeout=30)


def register_gateway(c: httpx.Client) -> None:
    existing = c.get("/gateways").json()
    names = {g.get("name") for g in (existing if isinstance(existing, list) else existing.get("data", []))}
    if "returnguard-tools" in names:
        print("gateway already registered")
        return
    r = c.post("/gateways", json={
        "name": "returnguard-tools",
        "url": UPSTREAM,
        "transport": "streamablehttp",
        "description": "ReturnGuard plain tools backend",
    })
    print("register gateway:", r.status_code, r.text[:200])
    r.raise_for_status()


def list_tools(c: httpx.Client) -> dict:
    r = c.get("/tools")
    r.raise_for_status()
    data = r.json()
    tools = data if isinstance(data, list) else data.get("data", [])
    out = {}
    for t in tools:
        # federated tool names are usually "<gateway>-<tool>" or "<gateway>.<tool>"
        raw = t.get("name") or t.get("originalName") or ""
        base = raw.split("-")[-1].split(".")[-1]
        out[base] = t.get("id") or t.get("name")
    return out


def make_virtual_servers(c: httpx.Client, tool_ids: dict) -> dict:
    servers = {}
    existing = c.get("/servers").json()
    existing = existing if isinstance(existing, list) else existing.get("data", [])
    by_name = {s.get("name"): s for s in existing}
    for agent, allowed in ALLOW.items():
        name = f"agent-{agent}"
        ids = [tool_ids[t] for t in allowed if t in tool_ids]
        if name in by_name:
            sid = by_name[name].get("id")
            c.put(f"/servers/{sid}", json={"name": name, "associatedTools": ids})
        else:
            r = c.post("/servers", json={
                "name": name,
                "description": f"ReturnGuard {agent} agent — scoped tool server",
                "associatedTools": ids,
            })
            r.raise_for_status()
            sid = r.json().get("id")
        servers[agent] = {"server_id": sid, "tools": allowed}
        print(f"  {name}: id={sid} tools={allowed}")
    return servers


def main() -> None:
    for _ in range(30):
        try:
            if httpx.get(f"{GW}/health", timeout=5).status_code == 200:
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)

    c = _client()
    register_gateway(c)
    time.sleep(3)  # let it introspect the upstream
    tool_ids = list_tools(c)
    print("federated tools:", tool_ids)
    if "flag_ring" not in tool_ids or "get_order" not in tool_ids:
        print("WARNING: expected tools not federated yet:", tool_ids, file=sys.stderr)

    servers = make_virtual_servers(c, tool_ids)

    out = {"gateway_url": GW, "agents": servers, "tool_ids": tool_ids}
    pathlib_out = os.getenv("MCP_SETUP_OUT", "/out/mcp_setup.json")
    try:
        with open(pathlib_out, "w") as f:
            json.dump(out, f, indent=2)
        print("wrote", pathlib_out)
    except OSError:
        print(json.dumps(out, indent=2))

    _write_vault(servers)


def _write_vault(servers: dict) -> None:
    try:
        import hvac

        v = hvac.Client(url=os.environ["VAULT_ADDR"], token=os.environ["VAULT_TOKEN"])
        cur = v.secrets.kv.v2.read_secret_version(
            mount_point="secret", path="returnguard/mcp", raise_on_deleted_version=True
        )["data"]["data"]
        cur["agent_servers"] = json.dumps({a: s["server_id"] for a, s in servers.items()})
        v.secrets.kv.v2.create_or_update_secret(
            mount_point="secret", path="returnguard/mcp", secret=cur
        )
        print("wrote agent server ids to Vault")
    except Exception as e:  # noqa: BLE001
        print(f"vault write skipped: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
