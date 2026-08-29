"""~Nx normal return volume -> queue holds, p95 measured.

Submits `factor` returns concurrently, waits for all to reach a final pipeline
state, reports p50/p95 time-to-first-decision. The scaling lever is worker
replicas (`docker compose up -d --scale worker=N`).

Usage: python scripts/loadtest.py --factor 20 --concurrency 4
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import statistics
import time
import uuid

from _kc import register_user, token
from _rg import API, httpx, q1


def one() -> float:
    e = f"load-{uuid.uuid4().hex[:8]}@test.local"
    pw = "Pw1!" + uuid.uuid4().hex[:8]
    register_user(e, pw)
    h = {"Authorization": f"Bearer {token(e, pw)}"}
    prods = httpx.get(f"{API}/products?sort=price_asc", timeout=15).json()
    o = httpx.post(f"{API}/orders", headers=h, timeout=20, json={
        "lines": [{"product_id": prods[0]["id"], "qty": 1}],
        "shipping_address": {"line1": "1", "city": "x", "zip": "1"},
        "card_number": "4242424242424242", "card_exp": "12/30", "card_cvc": "123"}).json()
    img = b"\xff\xd8\xff\xe0" + b"\x00" * 400  # tiny — data-quality gate will escalate; that's fine for load
    from PIL import Image  # noqa
    import io
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (128, 128, 128)).save(buf, "JPEG")
    t0 = time.time()
    r = httpx.post(f"{API}/returns", headers=h, timeout=30,
                   data={"order_item_id": o["items"][0]["id"], "reason_code": "damaged"},
                   files={"photo": ("x.jpg", buf.getvalue(), "image/jpeg")}).json()
    rid = r["id"]
    while time.time() - t0 < 300:
        st = q1("select status from returns where id=%(r)s", r=rid)
        if st in ("approved", "escalated", "denied", "refunded"):
            return time.time() - t0
        time.sleep(2)
    return float("nan")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--factor", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args()
    print(f"submitting {a.factor} returns, concurrency {a.concurrency}…")
    start = time.time()
    with cf.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        times = [t for t in ex.map(lambda _: one(), range(a.factor)) if t == t]  # drop nan
    wall = time.time() - start
    times.sort()
    print(f"\ncompleted {len(times)}/{a.factor} in {wall:.0f}s wall")
    print(f"time-to-decision  p50={statistics.median(times):.1f}s  "
          f"p95={times[int(len(times) * 0.95) - 1]:.1f}s  max={max(times):.1f}s")
    print(f"throughput ≈ {len(times) / wall * 60:.1f} decisions/min")


if __name__ == "__main__":
    main()
