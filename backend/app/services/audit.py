"""Append-only, hash-chained audit log (backend side). Identical canonical rule
to worker/pipeline/audit.py.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

GENESIS = "0" * 64


def _canonical(ts_iso, actor_type, actor_id, action, entity_type, entity_id, data) -> str:
    return json.dumps(
        {"ts": ts_iso, "actor_type": actor_type, "actor_id": actor_id, "action": action,
         "entity_type": entity_type, "entity_id": entity_id, "data": data},
        sort_keys=True, separators=(",", ":"), default=str,
    )


async def append(
    session: AsyncSession, *, actor_type: str, actor_id: str, action: str,
    entity_type: str, entity_id: str, data: dict,
) -> str:
    """Append one row within the caller's transaction (so the mutation + its audit
    row commit together). A single xact-scoped advisory lock serialises ALL audit
    appends across the backend and the worker — "SELECT the tip FOR UPDATE" forks
    under concurrency (a blocked LIMIT 1 does not re-scan for the new tip)."""
    await session.execute(text("SELECT pg_advisory_xact_lock(742042)"))
    last = (
        await session.execute(
            text("SELECT row_hash FROM audit_log ORDER BY id DESC LIMIT 1")
        )
    ).scalar_one_or_none()
    prev = last or GENESIS
    ts_iso = dt.datetime.now(dt.UTC).isoformat()
    canonical = _canonical(ts_iso, actor_type, actor_id, action, entity_type, entity_id, data)
    row_hash = hashlib.sha256((prev + canonical).encode()).hexdigest()
    await session.execute(
        text(
            "INSERT INTO audit_log "
            "(ts, actor_type, actor_id, action, entity_type, entity_id, data, prev_hash, row_hash) "
            "VALUES (:ts,:at,:ai,:ac,:et,:ei,CAST(:d AS jsonb),:ph,:rh)"
        ),
        {"ts": ts_iso, "at": actor_type, "ai": actor_id, "ac": action, "et": entity_type,
         "ei": entity_id, "d": json.dumps(data, default=str), "ph": prev, "rh": row_hash},
    )
    return row_hash
