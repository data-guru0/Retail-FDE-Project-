"""M3 dead-letter drill — a case that crashes the pipeline 3x lands in
`dead_letter`, is auto-escalated, and is logged. Never an infinite retry.

Method (real, not mocked): toggle the worker's documented fault-injection hook
(`RG_PIPELINE_FORCE_ERROR`), which makes `review_return` raise a real exception
after claiming the case — exercising the genuine retry -> dead_letter -> escalate
path. Restore the worker afterwards.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import time
import uuid

from _kc import register_user, token
from _rg import API, Check, httpx, q1

FIX = pathlib.Path(__file__).resolve().parents[1] / "scenarios" / "fixtures" / "sample_return.jpg"
ROOT = pathlib.Path(__file__).resolve().parents[1]
OVERRIDE = ROOT / "docker-compose.dlqtest.yml"

OVERRIDE_YML = """services:
  worker:
    environment:
      RG_PIPELINE_FORCE_ERROR: "1"
"""


def compose(*args: str):
    return subprocess.run(["docker", "compose", *args], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def submit() -> str:
    email = f"dlq-{uuid.uuid4().hex[:8]}@test.local"
    pw = "Passw0rd!" + uuid.uuid4().hex[:6]
    register_user(email, pw)
    h = {"Authorization": f"Bearer {token(email, pw)}"}
    prods = httpx.get(f"{API}/products?sort=price_asc", timeout=15).json()
    order = httpx.post(
        f"{API}/orders",
        json={"lines": [{"product_id": prods[0]["id"], "qty": 1}],
              "shipping_address": {"line1": "1", "city": "x", "zip": "1"},
              "card_number": "4242424242424242", "card_exp": "12/30", "card_cvc": "123"},
        headers=h, timeout=20,
    ).json()
    with open(FIX, "rb") as f:
        r = httpx.post(
            f"{API}/returns",
            data={"order_item_id": order["items"][0]["id"], "reason_code": "damaged"},
            files={"photo": ("r.jpg", f, "image/jpeg")}, headers=h, timeout=30,
        ).json()
    return r["id"]


def main() -> None:
    c = Check("verify_m3_dlq")
    OVERRIDE.write_text(OVERRIDE_YML)
    try:
        print("  enabling fault injection on the worker…")
        r = compose("-f", "docker-compose.yml", "-f", "docker-compose.override.yml",
                    "-f", OVERRIDE.name, "up", "-d", "--force-recreate", "worker")
        assert r.returncode == 0, r.stderr
        time.sleep(10)

        rid = submit()
        print(f"  submitted {rid}; expecting 3 crashes -> dead_letter…")
        deadline = time.time() + 150
        attempts = None
        while time.time() < deadline:
            attempts = q1("select attempts from dead_letter where return_id=%(r)s", r=rid)
            if attempts:
                break
            time.sleep(4)
        c.ok(attempts is not None, "a dead_letter row was written after repeated failures")
        c.ok((attempts or 0) >= 3, f"dead_letter.attempts >= 3 (got {attempts})")
        c.ok(q1("select status from returns where id=%(r)s", r=rid) == "escalated",
             "return was auto-escalated")
        c.ok(
            q1("select count(*) from agent_run_events where return_id=%(r)s and kind='dead_letter'",
               r=rid) == 1,
            "a dead_letter trace event was emitted",
        )
    finally:
        print("  restoring the worker…")
        OVERRIDE.unlink(missing_ok=True)
        compose("up", "-d", "--force-recreate", "worker")
        # WAIT until the restored worker is up AND fault injection is really gone —
        # otherwise the dying poisoned container grabs jobs from the next check.
        for _ in range(40):
            time.sleep(2)
            p = compose("exec", "-T", "worker", "printenv", "RG_PIPELINE_FORCE_ERROR")
            if p.returncode != 0 or not (p.stdout or "").strip():
                break
        else:
            print("  WARNING: worker still shows RG_PIPELINE_FORCE_ERROR after restore")

    c.done()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"verify_m3_dlq crashed: {type(e).__name__}: {e}")
        sys.exit(2)
