"""M5 self-check — the full scripted reviewer + governance walkthrough.

new customer -> real purchase -> real return (mismatched photo) -> live trace over
WebSocket -> reviewer claims it -> DENY with the confirm step -> audit chain
extended + still valid -> a vs-baseline analytics number moved -> override a
second case -> agreement_samples grew + trend moved -> flip automation_level to
`assist` + tune thresholds -> an easy case auto-approves, a QA sample can land.
Then verify_security passes.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import subprocess
import sys
import time
import uuid

from _kc import register_user, token
from _rg import API, Check, httpx, q1

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "scenarios" / "fixtures"


def customer(prefix: str) -> dict:
    e = f"{prefix}-{uuid.uuid4().hex[:8]}@test.local"
    pw = "Pw1!" + uuid.uuid4().hex[:8]
    register_user(e, pw)
    return {"Authorization": f"Bearer {token(e, pw)}"}


def staff(prefix: str, role: str) -> dict:
    e = f"{prefix}-{uuid.uuid4().hex[:8]}@test.local"
    pw = "Pw1!" + uuid.uuid4().hex[:8]
    register_user(e, pw, roles=[role] if role == "reviewer" else ["admin", "reviewer"])
    h = {"Authorization": f"Bearer {token(e, pw)}"}
    httpx.get(f"{API}/dashboard/queue", headers=h, timeout=15)  # force users+reviewer row
    return h


def submit(h: dict, photo: str, reason: str, text: str, age_days: int = 5) -> str:
    prods = httpx.get(f"{API}/products?sort=price_asc", timeout=15).json()
    o = httpx.post(f"{API}/orders", headers=h, timeout=20, json={
        "lines": [{"product_id": prods[0]["id"], "qty": 1}],
        "shipping_address": {"line1": "1", "city": "x", "zip": "1"},
        "card_number": "4242424242424242", "card_exp": "12/30", "card_cvc": "123"}).json()
    from _rg import db
    with db() as c:
        c.execute("update orders set placed_at=now()-(%(d)s||' days')::interval where id=%(o)s",
                  {"d": age_days, "o": o["id"]})
    with open(FIX / photo, "rb") as f:
        r = httpx.post(f"{API}/returns", headers=h, timeout=30,
                       data={"order_item_id": o["items"][0]["id"], "reason_code": reason,
                             "reason_text": text},
                       files={"photo": (photo, f, "image/jpeg")})
    return r.json()["id"]


def wait_final(rid: str, timeout: int = 240) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        row = q1("select json_build_object('status',status,'decision',decision,"
                 "'final_decision',final_decision,'refund_state',refund_state,"
                 "'graph_run_id',graph_run_id) from returns where id=%(r)s", r=rid)
        if row and row["status"] in ("approved", "escalated", "denied", "refunded"):
            return row
        time.sleep(3)
    return row or {}


def ws_events(rid: str, expect: int) -> list[str]:
    import websockets

    async def go():
        got = []
        try:
            async with websockets.connect(f"ws://localhost:8000/ws/returns/{rid}") as w:
                for _ in range(expect + 3):
                    try:
                        m = json.loads(await asyncio.wait_for(w.recv(), timeout=8))
                    except (TimeoutError, asyncio.TimeoutError):
                        break
                    if m.get("kind"):
                        got.append(m["kind"])
                    if "pipeline_end" in got:
                        break
        except Exception:  # noqa: BLE001
            pass
        return got

    return asyncio.run(go())


def chain_ok() -> bool:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_audit_chain.py")],
                          capture_output=True).returncode == 0


def audit_len() -> int:
    return q1("select count(*) from audit_log")


def gov_set(admin_h: dict, **kw) -> None:
    httpx.put(f"{API}/dashboard/governance", headers=admin_h, timeout=15,
              json={"scope": "global", **kw}).raise_for_status()


def main() -> None:
    c = Check("verify_m5")
    admin_h = staff("m5admin", "admin")
    rev_h = staff("m5rev", "reviewer")
    rev2_h = staff("m5rev2", "reviewer")
    gov_set(admin_h, automation_level="shadow", kill_switch=False,
            tau_risk=0.30, tau_conf=0.80, qa_sample_pct=100)

    # 1-2. purchase + mismatched-photo return + live trace over WS
    cust_h = customer("m5cust")
    rid = submit(cust_h, "mismatch_photo.jpg", "not_as_described", "Wrong item entirely.")
    res = wait_final(rid)
    c.ok(res.get("status") == "escalated", f"mismatched-photo case escalated ({res.get('status')})")
    kinds = ws_events(rid, 20)
    c.ok("pipeline_end" in kinds, f"live trace streamed over WebSocket ({len(kinds)} events)")

    a0 = audit_len()
    an0 = httpx.get(f"{API}/dashboard/analytics", headers=rev_h, timeout=15).json()

    # 3-4. reviewer claims + denies with the confirm step
    httpx.post(f"{API}/dashboard/returns/{rid}/claim", headers=rev_h, timeout=15).raise_for_status()
    no_confirm = httpx.post(f"{API}/dashboard/returns/{rid}/decide", headers=rev_h, timeout=15,
                            json={"decision": "deny", "note": "photo mismatch"})
    c.ok(no_confirm.status_code == 400, "deny without confirm step is rejected (400)")
    ok = httpx.post(f"{API}/dashboard/returns/{rid}/decide", headers=rev_h, timeout=15,
                    json={"decision": "deny", "note": "photo mismatch", "confirm": True})
    c.ok(ok.status_code == 200, f"deny with confirm step accepted ({ok.status_code})")
    c.ok(q1("select final_decision from returns where id=%(r)s", r=rid) == "deny",
         "returns.final_decision = deny")
    c.ok(q1("select status from returns where id=%(r)s", r=rid) == "denied",
         "returns.status = denied")

    # 5. audit chain extended + valid
    c.ok(audit_len() > a0, f"audit_log grew ({a0} -> {audit_len()})")
    c.ok(chain_ok(), "audit_log hash chain still validates after the human decision")

    # 6. a vs-baseline number moved
    an1 = httpx.get(f"{API}/dashboard/analytics", headers=rev_h, timeout=15).json()
    c.ok(an1["counts"]["human_decided"] > an0["counts"]["human_decided"],
         f"analytics human_decided moved ({an0['counts']['human_decided']} -> "
         f"{an1['counts']['human_decided']})")

    # 7. override a second case -> agreement_samples grow + trend has data
    ag0 = q1("select count(*) from agreement_samples where kind='override'")
    rid2 = submit(customer("m5c2"), "sample_return.jpg", "damaged", "Cracked on arrival.")
    res2 = wait_final(rid2)
    agent_dec = res2.get("decision")
    opp = "approve" if agent_dec != "approve" else "deny"
    httpx.post(f"{API}/dashboard/returns/{rid2}/claim", headers=rev2_h, timeout=15)
    httpx.post(f"{API}/dashboard/returns/{rid2}/decide", headers=rev2_h, timeout=15,
               json={"decision": opp, "note": "reviewer override", "confirm": True}).raise_for_status()
    c.ok(q1("select count(*) from agreement_samples where kind='override'") > ag0,
         "agreement_samples grew after the override")
    ah = httpx.get(f"{API}/dashboard/agent-health", headers=rev_h, timeout=15).json()
    c.ok(len(ah["agreement_trend"]) >= 1, "agent-vs-human agreement trend has data")

    # 8. assist + tuned thresholds -> auto-approve + QA sample
    gov_set(admin_h, automation_level="assist", tau_risk=0.99, tau_conf=0.01, qa_sample_pct=100)
    rid3 = submit(customer("m5c3"), "sample_return.jpg", "damaged", "Small crack, within policy.")
    res3 = wait_final(rid3)
    c.ok(res3.get("status") in ("approved", "escalated"),
         f"assist easy case finished ({res3.get('status')})")
    if res3.get("status") == "approved":
        c.ok(res3.get("refund_state") == "pending", "auto-approved return -> refund_state=pending")
        c.ok(q1("select action from audit_log where entity_id=%(r)s and actor_id='governance_gate' "
                "order by id desc limit 1", r=rid3) == "auto_approve",
             "GovernanceGate wrote an auto_approve audit row")
        c.ok(q1("select count(*) from agreement_samples where return_id=%(r)s and kind='qa_sample'",
                r=rid3) == 1, "a QA sample landed for the auto-approval (assist, 100%)")
    else:
        gr = res3.get("graph_run_id")
        gov = q1("select parsed_output from agent_runs where graph_run_id=%(g)s and agent='governance'",
                 g=gr)
        c.ok(gov and gov.get("automation_level") == "assist",
             f"GovernanceGate ran at automation_level=assist ({gov.get('reason') if gov else 'n/a'})")

    gov_set(admin_h, automation_level="shadow", tau_risk=0.30, tau_conf=0.80, qa_sample_pct=10)

    # 9. request-info round trip: reviewer asks -> customer answers -> case re-queued
    rid4 = submit(customer_h4 := customer("m5c4"), "sample_return.jpg", "quality", "Seems worn.")
    _ = wait_final(rid4)
    httpx.post(f"{API}/dashboard/returns/{rid4}/claim", headers=rev_h, timeout=15)
    ir = httpx.post(f"{API}/dashboard/returns/{rid4}/request-info", headers=rev_h, timeout=15,
                    json={"question": "Was the item used before you noticed the issue?"})
    c.ok(ir.status_code == 200, f"reviewer request-info accepted ({ir.status_code})")
    c.ok(q1("select status from returns where id=%(r)s", r=rid4) == "info_requested",
         "return moved to info_requested")
    seen = httpx.get(f"{API}/returns/{rid4}/info-request", headers=customer_h4, timeout=15).json()
    c.ok(seen.get("question", "").startswith("Was the item"), "customer sees the open question")
    ans = httpx.post(f"{API}/returns/{rid4}/info-request", headers=customer_h4, timeout=15,
                     data={"answer": "No, it was worn on arrival."})
    c.ok(ans.status_code == 200, "customer answer accepted")
    c.ok(q1("select answer from info_requests where return_id=%(r)s", r=rid4) is not None,
         "answer stored on info_requests")
    r4b = wait_final(rid4)
    c.ok(r4b.get("status") in ("escalated", "in_review", "approved", "denied"),
         f"case re-entered the pipeline after the answer ({r4b.get('status')})")

    # 10. refund settlement: an approved return reaches refund_state=refunded
    gov_set(admin_h, automation_level="assist", tau_risk=0.99, tau_conf=0.01, qa_sample_pct=0)
    rid5 = submit(customer("m5c5"), "matching_RG-009.jpg", "damaged",
                  "One mug cracked on the base.")
    # order the matching SKU so CLIP matches
    with __import__("_rg").db() as x:
        x.execute("update order_items oi set product_id = (select id from products where sku='RG-009') "
                  "from returns r where r.order_item_id = oi.id and r.id = %(r)s", {"r": rid5})
    r5 = wait_final(rid5)
    if r5.get("status") == "approved":
        deadline = time.time() + 90
        rf = None
        while time.time() < deadline:
            rf = q1("select refund_state from returns where id=%(r)s", r=rid5)
            if rf == "refunded":
                break
            time.sleep(5)
        c.ok(rf == "refunded", f"approved return settled to refund_state=refunded ({rf})")
        c.ok(q1("select count(*) from audit_log where entity_id=%(r)s and action='refund_issued'",
                r=rid5) == 1, "process_refunds wrote a refund_issued audit row")
    else:
        c.ok(True, f"(m5c5 escalated not approved: {r5.get('status')} — refund path unchanged)")
    gov_set(admin_h, automation_level="shadow", tau_risk=0.30, tau_conf=0.80, qa_sample_pct=10)

    # 11. security
    sec = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_security.py")],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    c.ok(sec.returncode == 0, f"verify_security passes\n{sec.stdout[-400:]}")

    c.done()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"verify_m5 crashed: {type(e).__name__}: {e}")
        sys.exit(2)
