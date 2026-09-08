"""Re-walk the audit_log hash chain and recompute every row_hash with the
canonical hash-chain rule. Fails on any tamper or break.
"""
from __future__ import annotations

import hashlib
import json
import sys

from _rg import Check, qall

GENESIS = "0" * 64


def canonical(ts_iso, actor_type, actor_id, action, entity_type, entity_id, data) -> str:
    return json.dumps(
        {"ts": ts_iso, "actor_type": actor_type, "actor_id": actor_id, "action": action,
         "entity_type": entity_type, "entity_id": entity_id, "data": data},
        sort_keys=True, separators=(",", ":"), default=str,
    )


def main() -> None:
    c = Check("verify_audit_chain")
    rows = qall(
        "SELECT id, ts, actor_type, actor_id, action, entity_type, entity_id, "
        "data, prev_hash, row_hash FROM audit_log ORDER BY id"
    )
    c.ok(True, f"{len(rows)} audit rows")
    prev = GENESIS
    ok = True
    for r in rows:
        (_id, ts, at, ai, ac, et, ei, data, prev_hash, row_hash) = r
        ts_iso = ts.isoformat()
        expect = hashlib.sha256(
            (prev + canonical(ts_iso, at, ai, ac, et, ei, data)).encode()
        ).hexdigest()
        if prev_hash != prev:
            ok = False
            print(f"  [FAIL] row {_id}: prev_hash mismatch (stored {prev_hash[:12]} != {prev[:12]})")
        if row_hash != expect:
            ok = False
            print(f"  [FAIL] row {_id}: row_hash mismatch (recompute {expect[:12]} != stored {row_hash[:12]})")
        prev = row_hash
    c.ok(ok, "every row_hash recomputes and the chain is unbroken")
    c.done()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"verify_audit_chain crashed: {type(e).__name__}: {e}")
        sys.exit(2)
