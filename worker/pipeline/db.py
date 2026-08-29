"""Worker DB access. The worker writes a small, fixed set of rows (agent_runs,
agent_run_events, returns updates, dead_letter) so it uses SQL directly via an
async psycopg pool rather than duplicating the backend ORM.
"""
from __future__ import annotations

import json
from typing import Any

from psycopg_pool import AsyncConnectionPool

from pipeline.settings import get_settings

_dsn = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")
pool = AsyncConnectionPool(conninfo=_dsn, min_size=1, max_size=6, open=False)


async def start() -> None:
    await pool.open()


async def stop() -> None:
    await pool.close()


async def fetchrow(sql: str, params: dict | None = None) -> dict | None:
    async with pool.connection() as conn:
        cur = await conn.execute(sql, params or {})
        row = await cur.fetchone()
        if row is None:
            return None
        cols = [c.name for c in cur.description]
        return dict(zip(cols, row, strict=True))


async def fetchall(sql: str, params: dict | None = None) -> list[dict]:
    async with pool.connection() as conn:
        cur = await conn.execute(sql, params or {})
        rows = await cur.fetchall()
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r, strict=True)) for r in rows]


async def fetchval(sql: str, params: dict | None = None) -> Any:
    row = None
    async with pool.connection() as conn:
        cur = await conn.execute(sql, params or {})
        row = await cur.fetchone()
    return row[0] if row else None


async def execute(sql: str, params: dict | None = None) -> None:
    async with pool.connection() as conn:
        await conn.execute(sql, params or {})


async def get_review_context(return_id: str) -> dict | None:
    """Everything the pipeline needs about one return, in one query."""
    return await fetchrow(
        """
        SELECT
          r.id::text            AS return_id,
          r.reason_code, r.reason_text, r.amount, r.status,
          r.order_id::text      AS order_id,
          r.user_id::text       AS user_id,
          oi.name_snapshot      AS item_name,
          oi.unit_price, oi.qty,
          o.placed_at,
          o.total               AS order_total,
          u.email               AS customer_email,
          p.category            AS category,
          p.description         AS product_description,
          (now() - o.placed_at) AS age_since_order,
          (SELECT count(*) FROM returns r2 WHERE r2.user_id = r.user_id)      AS user_return_count,
          (SELECT count(*) FROM orders o2 WHERE o2.user_id = r.user_id)       AS user_order_count,
          (SELECT count(*) FROM return_photos rp WHERE rp.return_id = r.id)   AS photo_count
        FROM returns r
        JOIN order_items oi ON oi.id = r.order_item_id
        JOIN orders o       ON o.id = r.order_id
        JOIN users u        ON u.id = r.user_id
        LEFT JOIN products p ON p.id = oi.product_id
        WHERE r.id = %(rid)s
        """,
        {"rid": return_id},
    )


async def current_automation_level(category: str | None = None) -> tuple[str, bool]:
    row = await fetchrow(
        "SELECT automation_level, kill_switch FROM feature_flags "
        "WHERE scope = %(scope)s",
        {"scope": category or "global"},
    )
    if row is None:
        row = await fetchrow(
            "SELECT automation_level, kill_switch FROM feature_flags WHERE scope = 'global'"
        )
    return (row["automation_level"], row["kill_switch"]) if row else ("shadow", False)


async def insert_agent_run(**kw: Any) -> str:
    kw.setdefault("parsed_output", None)
    if kw.get("parsed_output") is not None:
        kw["parsed_output"] = json.dumps(kw["parsed_output"])
    return await fetchval(
        """
        INSERT INTO agent_runs
          (return_id, graph_run_id, agent, sa_subject, model, prompt_version,
           policy_version, automation_level, input_hash, raw_response, parsed_output,
           confidence, tokens_in, tokens_out, cost_usd, latency_ms, langfuse_trace_id, error)
        VALUES
          (%(return_id)s, %(graph_run_id)s, %(agent)s, %(sa_subject)s, %(model)s,
           %(prompt_version)s, %(policy_version)s, %(automation_level)s, %(input_hash)s,
           %(raw_response)s, %(parsed_output)s, %(confidence)s, %(tokens_in)s, %(tokens_out)s,
           %(cost_usd)s, %(latency_ms)s, %(langfuse_trace_id)s, %(error)s)
        RETURNING id::text
        """,
        kw,
    )


async def add_event(
    return_id: str, graph_run_id: str, seq: int, agent: str, kind: str, payload: dict
) -> None:
    await execute(
        "INSERT INTO agent_run_events (return_id, graph_run_id, seq, agent, kind, payload) "
        "VALUES (%(rid)s, %(grid)s, %(seq)s, %(agent)s, %(kind)s, %(payload)s)",
        {"rid": return_id, "grid": graph_run_id, "seq": seq, "agent": agent,
         "kind": kind, "payload": json.dumps(payload)},
    )
    from pipeline.bus import publish_event

    await publish_event(
        return_id,
        {"seq": seq, "agent": agent, "kind": kind, "payload": payload,
         "graph_run_id": graph_run_id},
    )
