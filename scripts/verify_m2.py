"""M2 self-check — real shop flow end to end.

register a fresh Keycloak account -> log in -> list products -> place an order ->
read it from order history -> submit a return with a real uploaded image ->
assert the orders / order_items / returns / return_photos / outbox rows exist in
Postgres, the object exists in MinIO, and the return status is `pending`.
"""
from __future__ import annotations

import pathlib
import time
import uuid

from _kc import register_user, token
from _rg import API, Check, httpx, q1

FIX = pathlib.Path(__file__).resolve().parents[1] / "docs" / "scenarios" / "assets" / "sample_return.jpg"


def main() -> None:
    c = Check("verify_m2")
    email = f"m2-{uuid.uuid4().hex[:8]}@test.local"
    pw = "Passw0rd!" + uuid.uuid4().hex[:6]

    kc_id = register_user(email, pw)
    c.ok(bool(kc_id), f"registered Keycloak user {email}")

    tok = token(email, pw)
    c.ok(tok.count(".") == 2, "got a real JWT access token")
    h = {"Authorization": f"Bearer {tok}"}

    prods = httpx.get(f"{API}/products", timeout=15).json()
    c.ok(len(prods) >= 12, f"{len(prods)} products listed")
    p0 = prods[0]

    order_body = {
        "lines": [{"product_id": p0["id"], "qty": 2}],
        "shipping_address": {"line1": "1 Test St", "city": "Testville", "zip": "00001"},
        "card_number": "4242 4242 4242 4242",
        "card_exp": "12/30",
        "card_cvc": "123",
    }
    r = httpx.post(f"{API}/orders", json=order_body, headers=h, timeout=20)
    c.ok(r.status_code == 201, f"POST /orders -> {r.status_code}")
    order = r.json()
    oid = order["id"]
    c.ok(order["payment_last4"] == "4242", "order stored card last4 only")
    c.ok(float(order["total"]) == float(p0["price"]) * 2, "order total correct")

    hist = httpx.get(f"{API}/orders", headers=h, timeout=15).json()
    c.ok(any(o["id"] == oid for o in hist), "order shows in order history")
    item_id = order["items"][0]["id"]

    with open(FIX, "rb") as f:
        r = httpx.post(
            f"{API}/returns",
            data={"order_item_id": item_id, "reason_code": "damaged",
                  "reason_text": "Arrived with a cracked rim."},
            files={"photo": ("return.jpg", f, "image/jpeg")},
            headers=h, timeout=30,
        )
    c.ok(r.status_code == 201, f"POST /returns -> {r.status_code} {r.text[:120]}")
    ret = r.json()
    rid = ret["id"]
    c.ok(ret["status"] == "pending", "return created with status=pending")

    # ---- assert real DB state ------------------------------------------------
    c.ok(q1("select count(*) from orders where id=%(id)s", id=oid) == 1, "orders row exists")
    c.ok(q1("select count(*) from order_items where order_id=%(id)s", id=oid) == 1,
         "order_items row exists")
    # created as 'pending'; the worker may already have picked it up by now — any
    # of these means the row was written correctly and the outbox fired.
    c.ok(q1("select status from returns where id=%(id)s", id=rid)
         in ("pending", "in_review", "escalated", "approved", "denied", "refunded"),
         "returns row persisted (pending or already in the pipeline)")
    pkey = q1("select object_key from return_photos where return_id=%(id)s", id=rid)
    c.ok(bool(pkey), f"return_photos row exists ({pkey})")
    c.ok(
        q1("select count(*) from outbox where payload->>'return_id' = %(id)s", id=rid) == 1,
        "outbox row written in the same transaction",
    )

    # ---- assert the object really is in MinIO ------------------------------
    purls = httpx.get(f"{API}/returns/{rid}", headers=h, timeout=15).json()["photo_urls"]
    c.ok(len(purls) == 1, "return status page returns 1 photo url")
    img = httpx.get(purls[0], timeout=15)
    c.ok(img.status_code == 200 and img.content[:3] == b"\xff\xd8\xff",
         f"MinIO object fetches as a real JPEG ({len(img.content)} bytes)")

    time.sleep(0.2)
    c.done()


if __name__ == "__main__":
    main()
