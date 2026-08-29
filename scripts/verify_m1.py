"""M1 self-check — drives the live stack, asserts real state.

- every compose service healthy / running
- GET /health/deep reports real success for every dependency
- alembic current == head
"""
from __future__ import annotations

import json
import sys

from _rg import API, Check, httpx, run


def compose_ps() -> list[dict]:
    out = run(["docker", "compose", "ps", "--format", "json"]).stdout
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main() -> None:
    c = Check("verify_m1")

    rows = compose_ps()
    c.ok(len(rows) >= 10, f"compose has {len(rows)} services up")
    for r in rows:
        name = r.get("Service") or r.get("Name")
        state = r.get("State")
        health = r.get("Health", "")
        healthy = state == "running" and health in ("", "healthy")
        c.ok(healthy, f"{name}: state={state} health={health or 'n/a'}")

    r = httpx.get(f"{API}/health/deep", timeout=30)
    c.ok(r.status_code == 200, f"/health/deep HTTP {r.status_code}")
    body = r.json()
    for dep, res in body.get("checks", {}).items():
        c.ok(bool(res.get("ok")), f"health/deep {dep}: {res}")
    c.ok(body.get("status") == "ok", f"overall status = {body.get('status')}")

    cur = run(["docker", "compose", "run", "--rm", "-T", "backend", "alembic", "current"])
    heads = run(["docker", "compose", "run", "--rm", "-T", "backend", "alembic", "heads"])
    cur_rev = cur.stdout.strip().split()[0] if cur.stdout.strip() else ""
    head_rev = heads.stdout.strip().split()[0] if heads.stdout.strip() else ""
    c.ok(cur_rev and cur_rev == head_rev, f"alembic current({cur_rev}) == head({head_rev})")

    c.done()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"verify_m1 crashed: {type(e).__name__}: {e}")
        sys.exit(2)
