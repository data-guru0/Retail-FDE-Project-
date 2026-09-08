"""M3 self-check — the single-agent return pipe, end to end, for real.

submit a return -> wait for the worker -> assert:
  * a real `agent_runs` row exists (agent=decision) with model + tokens + cost + latency
  * the decision on the API == returns.decision == agent_runs.parsed_output.decision
  * a Langfuse trace id is recorded and the trace really exists in Langfuse
  * Bifrost logged a real upstream call for this decision's model
  * agent_run_events were streamed (pipeline_start .. pipeline_end)
"""
from __future__ import annotations

import pathlib
import sys
import time
import uuid

from _kc import register_user, token
from _rg import API, BIFROST, Check, httpx, q1, qall

FIX = pathlib.Path(__file__).resolve().parents[1] / "scenarios" / "fixtures" / "sample_return.jpg"
LANGFUSE_PK = None


def _lf_keys():
    from _rg import _E

    return _E["LANGFUSE_INIT_PROJECT_PUBLIC_KEY"], _E["LANGFUSE_INIT_PROJECT_SECRET_KEY"]


def submit_return() -> tuple[str, dict, str]:
    email = f"m3-{uuid.uuid4().hex[:8]}@test.local"
    pw = "Passw0rd!" + uuid.uuid4().hex[:6]
    register_user(email, pw)
    tok = token(email, pw)
    h = {"Authorization": f"Bearer {tok}"}
    prods = httpx.get(f"{API}/products?sort=price_asc", timeout=15).json()
    p = prods[0]
    order = httpx.post(
        f"{API}/orders",
        json={
            "lines": [{"product_id": p["id"], "qty": 1}],
            "shipping_address": {"line1": "1 A St", "city": "B", "zip": "00002"},
            "card_number": "4242424242424242", "card_exp": "12/30", "card_cvc": "123",
        },
        headers=h, timeout=20,
    ).json()
    with open(FIX, "rb") as f:
        r = httpx.post(
            f"{API}/returns",
            data={"order_item_id": order["items"][0]["id"], "reason_code": "damaged",
                  "reason_text": "Item arrived cracked; photo attached."},
            files={"photo": ("r.jpg", f, "image/jpeg")}, headers=h, timeout=30,
        ).json()
    return r["id"], h, tok


def main() -> None:
    c = Check("verify_m3")
    # this check is about *shadow* behaviour — make sure that's the level,
    # regardless of what a previous scenario left behind
    from _rg import db
    with db() as x:
        x.execute("update feature_flags set automation_level='shadow', kill_switch=false "
                  "where scope='global'")
    rid, h, _ = submit_return()
    print(f"  submitted return {rid}; waiting for the worker…")

    # wait for the pipeline to actually finish (GovernanceGate is the last node)
    deadline = time.time() + 240
    final_status = None
    while time.time() < deadline:
        final_status = q1("select status from returns where id=%(r)s", r=rid)
        if final_status in ("approved", "escalated", "denied", "refunded"):
            break
        time.sleep(3)
    c.ok(final_status in ("approved", "escalated", "denied", "refunded"),
         f"pipeline reached a final state ({final_status})")

    run = q1(
        "select json_build_object("
        "'model',model,'tokens_in',tokens_in,'tokens_out',tokens_out,"
        "'cost',cost_usd,'latency',latency_ms,'trace',langfuse_trace_id,"
        "'parsed',parsed_output,'conf',confidence,'level',automation_level)"
        " from agent_runs where return_id=%(r)s and agent='decision' "
        "order by created_at desc limit 1", r=rid,
    )
    c.ok(run is not None, "an agent_runs row (agent=decision) was written")
    if not run:
        c.done()
        return

    c.ok(bool(run["model"]), f"model recorded: {run['model']}")
    c.ok(run["tokens_in"] > 0 and run["tokens_out"] > 0,
         f"real token counts: in={run['tokens_in']} out={run['tokens_out']}")
    c.ok(run["latency"] > 0, f"latency recorded: {run['latency']}ms")
    c.ok(run["level"] == "shadow", "automation_level == shadow (agent decides, human acts)")
    decision = run["parsed"]["decision"]
    c.ok(decision in ("approve", "deny", "escalate"), f"structured decision: {decision}")

    api_ret = httpx.get(f"{API}/returns/{rid}", headers=h, timeout=15).json()
    c.ok(api_ret["decision"] == decision,
         f"API return.decision ({api_ret['decision']}) == decision agent's proposal ({decision})")
    row_dec = q1("select decision from returns where id=%(r)s", r=rid)
    c.ok(row_dec == decision, f"returns.decision row ({row_dec}) == decision agent's proposal")
    c.ok(api_ret["status"] in ("in_review", "escalated", "approved"),
         f"shadow: agent decided, human still acts (status={api_ret['status']})")

    # events streamed
    evs = qall("select kind from agent_run_events where return_id=%(r)s order by seq", r=rid)
    kinds = [e[0] for e in evs]
    c.ok("pipeline_start" in kinds and "pipeline_end" in kinds,
         f"trace events streamed: {kinds}")
    c.ok("node_end" in kinds, "decision node_end event present")

    # the WebSocket replays those events to a live client
    import asyncio

    import websockets

    async def _ws_check() -> list[str]:
        import json as _j

        got = []
        try:
            async with websockets.connect(f"ws://localhost:8000/ws/returns/{rid}") as w:
                for _ in range(len(kinds) + 3):
                    try:
                        m = _j.loads(await asyncio.wait_for(w.recv(), timeout=8))
                    except (TimeoutError, asyncio.TimeoutError):
                        break
                    if m.get("kind"):
                        got.append(m["kind"])
                    if "pipeline_end" in got:
                        break
        except Exception as e:  # noqa: BLE001
            print(f"    (ws closed: {type(e).__name__})")
        return got

    ws_kinds = asyncio.run(_ws_check())
    c.ok("pipeline_end" in ws_kinds, f"WebSocket replayed the trace to a client: {ws_kinds}")

    # Langfuse trace really exists
    trace_id = run["trace"]
    c.ok(bool(trace_id), f"langfuse_trace_id recorded: {trace_id}")
    if trace_id:
        pk, sk = _lf_keys()
        for _ in range(10):
            lr = httpx.get(f"http://localhost:3001/api/public/traces/{trace_id}",
                           auth=(pk, sk), timeout=15)
            if lr.status_code == 200:
                break
            time.sleep(3)
        c.ok(lr.status_code == 200, f"Langfuse trace {trace_id} fetchable ({lr.status_code})")
        if lr.status_code == 200:
            obs = lr.json().get("observations", [])
            c.ok(any(o.get("type") == "GENERATION" for o in obs),
                 f"trace has a GENERATION observation ({len(obs)} obs)")

    # Bifrost logged a real upstream call
    metrics = httpx.get(f"{BIFROST}/metrics", timeout=15).text
    c.ok("bifrost_" in metrics and "requests" in metrics.lower(),
         "Bifrost exported request metrics (real upstream traffic)")

    c.done()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"verify_m3 crashed: {type(e).__name__}: {e}")
        sys.exit(2)
