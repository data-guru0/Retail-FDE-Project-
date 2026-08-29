"""Configure IBM ContextForge (mcp-context-forge 0.5.0):

1. register the plain mcp-server as an upstream **gateway** (ContextForge
   federates its tools)
2. create one **virtual server per agent** exposing only that agent's allowed
   tools (least privilege — CLAUDE.md)
3. write the per-agent server ids to scenarios/mcp_setup.json and to Vault

Least-privilege map:
  intake   -> get_order
  policy   -> check_policy
  behavior -> get_customer_history, flag_ring
  decision -> get_order, check_policy, get_customer_history
  planner / image / critic / explanation -> (no tools)

Invariant verify_m4 checks: the Image agent's virtual server lists NO flag_ring.

Run on the host:  python scripts/mcp_setup.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

from _rg import _E, httpx

GW = "http://localhost:4444"
UPSTREAM = "http://mcp-server:8070/mcp/"
JWT_SECRET = _E["CONTEXTFORGE_JWT_SECRET"]
OUT = pathlib.Path(__file__).resolve().parents[1] / "scenarios" / "mcp_setup.json"

ALLOW = {
    "intake": ["get_order"],
    "policy": ["check_policy"],
    "behavior": ["get_customer_history", "flag_ring"],
    "decision": ["get_order", "check_policy", "get_customer_history"],
    "planner": [], "image": [], "critic": [], "explanation": [],
}


def jwt() -> str:
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "mcp-gateway", "python", "-m",
         "mcpgateway.utils.create_jwt_token", "--username", "admin@returnguard.local",
         "--secret", JWT_SECRET, "--exp", "3600"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return out.stdout.strip().splitlines()[-1].strip()


def _base(obj) -> str:
    return (obj.get("originalName") or obj.get("name") or "").strip()


def main() -> None:
    tok = jwt()
    c = httpx.Client(base_url=GW, headers={"Authorization": f"Bearer {tok}"}, timeout=30)

    # 1. register upstream gateway (idempotent)
    gws = c.get("/gateways").json()
    gws = gws if isinstance(gws, list) else gws.get("data", [])
    if not any(g.get("name") == "returnguard-tools" for g in gws):
        r = c.post("/gateways", json={
            "name": "returnguard-tools", "url": UPSTREAM,
            "transport": "STREAMABLEHTTP",
            "description": "ReturnGuard plain tools backend",
        })
        print("register gateway:", r.status_code, r.text[:200])
        r.raise_for_status()
    else:
        print("gateway already registered")

    # 2. wait for tool federation
    tool_ids: dict[str, str] = {}
    for _ in range(20):
        data = c.get("/tools").json()
        items = data if isinstance(data, list) else data.get("data", [])
        tool_ids = {_base(t): (t.get("id") or t.get("name")) for t in items}
        if {"get_order", "check_policy", "get_customer_history", "flag_ring"} <= set(tool_ids):
            break
        time.sleep(3)
    print("federated tools:", list(tool_ids))
    if "flag_ring" not in tool_ids:
        print("ERROR: tools not federated", file=sys.stderr)
        sys.exit(1)

    # 3. per-agent virtual servers
    existing = c.get("/servers").json()
    existing = existing if isinstance(existing, list) else existing.get("data", [])
    by_name = {s.get("name"): s for s in existing}
    servers = {}
    for agent, allowed in ALLOW.items():
        name = f"agent-{agent}"
        ids = [tool_ids[t] for t in allowed if t in tool_ids]
        payload = {"name": name, "description": f"ReturnGuard {agent} — scoped tools",
                   "associated_tools": ids}
        if name in by_name:
            sid = by_name[name].get("id")
            c.put(f"/servers/{sid}", json=payload)
        else:
            r = c.post("/servers", json=payload)
            r.raise_for_status()
            sid = r.json().get("id")
        servers[agent] = {"server_id": sid, "tools": allowed}
        print(f"  {name}: id={sid} tools={allowed}")

    OUT.write_text(json.dumps(
        {"gateway_url": GW, "agents": servers, "tool_ids": tool_ids}, indent=2))
    print("wrote", OUT)
    _to_vault(servers)


def _to_vault(servers: dict) -> None:
    try:
        r = subprocess.run(
            ["docker", "compose", "exec", "-T", "-e", "VAULT_ADDR=http://vault:8200",
             "-e", "VAULT_TOKEN=root", "vault", "vault", "kv", "patch",
             "secret/returnguard/mcp",
             f"agent_servers={json.dumps({a: s['server_id'] for a, s in servers.items()})}"],
            capture_output=True, text=True,
        )
        print("vault patch:", "ok" if r.returncode == 0 else r.stderr[:200])
    except Exception as e:  # noqa: BLE001
        print("vault patch skipped:", e)


if __name__ == "__main__":
    main()
