"""Append-only, hash-chained audit log (worker side).

Canonical row serialization (ADR-0003): a compact JSON object with sorted keys
over (ts_iso, actor_type, actor_id, action, entity_type, entity_id, data).
row_hash = sha256(prev_hash + canonical). The DB trigger blocks UPDATE/DELETE.
`scripts/verify_audit_chain.py` re-walks and recomputes with the identical rule.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from pipeline import db

GENESIS = "0" * 64


def _canonical(ts_iso, actor_type, actor_id, action, entity_type, entity_id, data) -> str:
    return json.dumps(
        {"ts": ts_iso, "actor_type": actor_type, "actor_id": actor_id, "action": action,
         "entity_type": entity_type, "entity_id": entity_id, "data": data},
        sort_keys=True, separators=(",", ":"), default=str,
    )


async def append(*, actor_type: str, actor_id: str, action: str,
                 entity_type: str, entity_id: str, data: dict) -> str:
    async with db.pool.connection() as conn:
        async with conn.transaction():
            # serialize ALL audit appends (backend + worker) on one xact-scoped
            # advisory lock — "lock the last row FOR UPDATE" forks under concurrency
            # because a blocked SELECT ... LIMIT 1 does not re-scan for the new tip.
            await conn.execute("SELECT pg_advisory_xact_lock(742042)")
            cur = await conn.execute(
                "SELECT row_hash FROM audit_log ORDER BY id DESC LIMIT 1"
            )
            last = await cur.fetchone()
            prev = last[0] if last else GENESIS
            ts_iso = dt.datetime.now(dt.UTC).isoformat()
            canonical = _canonical(ts_iso, actor_type, actor_id, action,
                                   entity_type, entity_id, data)
            row_hash = hashlib.sha256((prev + canonical).encode()).hexdigest()
            await conn.execute(
                "INSERT INTO audit_log "
                "(ts, actor_type, actor_id, action, entity_type, entity_id, data, prev_hash, row_hash) "
                "VALUES (%(ts)s,%(at)s,%(ai)s,%(ac)s,%(et)s,%(ei)s,%(d)s,%(ph)s,%(rh)s)",
                {"ts": ts_iso, "at": actor_type, "ai": actor_id, "ac": action,
                 "et": entity_type, "ei": entity_id, "d": json.dumps(data, default=str),
                 "ph": prev, "rh": row_hash},
            )
    return row_hash
