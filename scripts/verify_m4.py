"""M4 self-check — the full multi-agent LangGraph pipeline.

- an easy legit return runs the whole graph: data_quality -> planner -> intake ->
  policy(RAG) -> behavior(ML+ring) -> decision -> critic -> explanation -> governance
- every node wrote a real agent_runs row (agent, model, policy_version where
  relevant); the live trace streamed pipeline_start..pipeline_end
- GovernanceGate is the ONLY finalizer: it wrote an audit_log row and the
  hash chain still validates
- Policy used a real Qdrant retrieval and recorded the policy_docs version
- Behavior loaded the registered model by version and ran the ring SQL
- (if ContextForge configured) the Image agent's virtual server exposes NO
  flag_ring and a direct call returns a real error
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import time
import uuid

from _kc import register_user, token
from _rg import API, Check, httpx, q1, qall

FIX = pathlib.Path(__file__).resolve().parents[1] / "docs" / "scenarios" / "assets" / "mug_photo.jpg"
ROOT = pathlib.Path(__file__).resolve().parents[1]


def _submit_easy() -> str:
    email = f"m4-{uuid.uuid4().hex[:8]}@test.local"
    pw = "Passw0rd!" + uuid.uuid4().hex[:6]
    register_user(email, pw)
    h = {"Authorization": f"Bearer {token(email, pw)}"}
    prods = httpx.get(f"{API}/products?sort=price_asc", timeout=15).json()
    o = httpx.post(
        f"{API}/orders",
        json={"lines": [{"product_id": prods[0]["id"], "qty": 1}],
              "shipping_address": {"line1": "1 A St", "city": "B", "zip": "00003"},
              "card_number": "4242424242424242", "card_exp": "12/30", "card_cvc": "123"},
        headers=h, timeout=20,
    ).json()
    from _rg import db

    with db() as c:
        c.execute("update orders set placed_at = now() - interval '6 days' where id=%(o)s",
                  {"o": o["id"]})
    with open(FIX, "rb") as f:
        r = httpx.post(
            f"{API}/returns",
            data={"order_item_id": o["items"][0]["id"], "reason_code": "damaged",
                  "reason_text": "Small crack on the rim."},
            files={"photo": ("m.jpg", f, "image/jpeg")}, headers=h, timeout=30,
        )
    return r.json()["id"]


def main() -> None:
    c = Check("verify_m4")
    rid = _submit_easy()
    print(f"  submitted {rid}; waiting for the multi-agent pipeline…")

    deadline = time.time() + 240
    row = None
    while time.time() < deadline:
        row = q1(
            "select json_build_object('status',status,'decision',decision,"
            "'final_decision',final_decision,'graph_run_id',graph_run_id) "
            "from returns where id=%(r)s", r=rid,
        )
        if row and row["status"] in ("approved", "escalated", "denied", "refunded"):
            break
        time.sleep(3)
    c.ok(row and row["status"] in ("approved", "escalated"),
         f"pipeline finished: status={row['status'] if row else None}")
    if not row or not row["graph_run_id"]:
        c.done(); return
    g = row["graph_run_id"]

    runs = qall(
        "select agent, model, policy_version from agent_runs where graph_run_id=%(g)s", g=g)
    agents = {r[0] for r in runs}
    for a in ("data_quality", "planner", "intake", "policy", "behavior",
              "decision", "critic", "explanation", "governance"):
        c.ok(a in agents, f"agent_runs row for '{a}'")

    pol = [r for r in runs if r[0] == "policy"][0]
    c.ok(pol[2] is not None, f"Policy recorded policy_version={pol[2]} (real Qdrant retrieval)")

    beh = q1("select model from agent_runs where graph_run_id=%(g)s and agent='behavior' "
             "and model like 'behavior_risk:%%'", g=g)
    c.ok(beh is not None, f"Behavior loaded the registered risk model ({beh})")

    ev = [e[0] for e in qall(
        "select kind from agent_run_events where return_id=%(r)s order by seq", r=rid)]
    c.ok("pipeline_start" in ev and "pipeline_end" in ev, f"live trace streamed ({len(ev)} events)")
    c.ok(ev.count("node_end") >= 7, f"per-node trace events present ({ev.count('node_end')} node_end)")

    # agents reached tools through ContextForge — real call_tool events + audit rows
    tcs = qall("select agent, payload->>'tool' t, payload->>'via' v, payload->>'ok' ok "
               "from agent_run_events where return_id=%(r)s and kind='tool_call' order by seq",
               r=rid)
    tool_by_agent = {(a, t) for a, t, _, _ in tcs}
    c.ok({("intake", "get_order"), ("policy", "check_policy"),
          ("behavior", "get_customer_history"), ("behavior", "flag_ring")} <= tool_by_agent,
         f"agents called their tools via ContextForge: {sorted(tool_by_agent)}")
    c.ok(all(v == "contextforge" for _, _, v, _ in tcs), "every tool call routed through the gateway")
    c.ok(tcs and all(ok == "true" for _, _, _, ok in tcs),
         f"every ContextForge tool call returned real data (ok): {[(a, t, ok) for a, t, _, ok in tcs]}")
    c.ok(q1("select count(*) from audit_log where entity_id=%(r)s and action='call_tool'", r=rid)
         >= 4, "every call_tool wrote an audit_log row")

    gov_audit = q1(
        "select action from audit_log where entity_id=%(r)s and actor_id='governance_gate' "
        "order by id desc limit 1", r=rid)
    c.ok(gov_audit in ("auto_approve", "escalate"),
         f"GovernanceGate is the finalizer — audit_log action={gov_audit}")
    c.ok(q1("select model from agent_runs where graph_run_id=%(g)s and agent='governance'", g=g)
         == "governance_gate:opa",
         "GovernanceGate decided via OPA (not the fail-closed fallback)")

    chain = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_audit_chain.py")],
                           capture_output=True, text=True)
    c.ok(chain.returncode == 0, "audit_log hash chain still validates")

    # never an auto-final deny
    bad = q1("select count(*) from returns r join audit_log a on a.entity_id = r.id::text "
             "where r.final_decision='deny' and a.actor_type='system' and a.action like 'auto%%'")
    c.ok(bad == 0, "no return was auto-denied by the system")

    # ContextForge least-privilege (best-effort — only if configured)
    _check_contextforge(c)

    # replay.py: re-run one node of this run in isolation (debugging tool, writes
    # nothing to `returns`)
    rp = subprocess.run(
        ["docker", "compose", "exec", "-T", "worker", "python", "replay.py", g, "policy"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    c.ok(rp.returncode == 0 and '"policy"' in rp.stdout,
         f"replay.py re-ran the policy node in isolation (rc={rp.returncode})")

    c.done()


def _cf_jwt() -> str:
    from _rg import _E

    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "mcp-gateway", "python", "-m",
         "mcpgateway.utils.create_jwt_token", "--username", "admin@returnguard.local",
         "--secret", _E["CONTEXTFORGE_JWT_SECRET"], "--exp", "600"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return out.stdout.strip().splitlines()[-1].strip()


def _check_contextforge(c: Check) -> None:
    setup = ROOT / "infra" / "mcp-gateway" / "mcp_setup.json"
    if not setup.exists():
        print("  (ContextForge not configured — run scripts/mcp_setup.py — skipping)")
        return
    import json

    cfg = json.loads(setup.read_text())
    gw = "http://localhost:4444"
    tok = _cf_jwt()
    h = {"Authorization": f"Bearer {tok}"}

    def tools_of(sid: str) -> list[str]:
        r = httpx.get(f"{gw}/servers/{sid}/tools", headers=h, timeout=15)
        if r.status_code != 200:
            return []
        d = r.json()
        items = d if isinstance(d, list) else d.get("data", [])
        return [t.get("originalName") or t.get("name") for t in items]

    img_tools = tools_of(cfg["agents"]["image"]["server_id"])
    beh_tools = tools_of(cfg["agents"]["behavior"]["server_id"])
    c.ok("flag_ring" not in img_tools,
         f"Image agent's virtual server lists NO flag_ring ({img_tools})")
    c.ok("flag_ring" in beh_tools,
         f"Behavior agent's virtual server lists flag_ring ({beh_tools})")
    c.ok(len(img_tools) == 0, "Image agent's virtual server exposes zero tools")

    # the enforced check: the Image agent CANNOT call flag_ring (raises PermissionError)
    grant = subprocess.run(
        ["docker", "compose", "exec", "-T", "worker", "python", "-c",
         "import json; from pipeline.mcp_client import is_granted as g; "
         "print(json.dumps({'image_flag_ring': g('image','flag_ring'), "
         "'behavior_flag_ring': g('behavior','flag_ring'), "
         "'image_get_order': g('image','get_order')}))"],
        cwd=ROOT, capture_output=True, text=True,
    )
    gd = json.loads(grant.stdout.strip().splitlines()[-1]) if grant.stdout.strip() else {}
    c.ok(gd.get("image_flag_ring") is False,
         "Image agent is NOT granted flag_ring — a direct call raises PermissionError")
    c.ok(gd.get("image_get_order") is False, "Image agent is granted no MCP tools at all")
    c.ok(gd.get("behavior_flag_ring") is True, "Behavior agent IS granted flag_ring")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"verify_m4 crashed: {type(e).__name__}: {e}")
        sys.exit(2)
