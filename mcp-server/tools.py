"""Real tool implementations, backed by the app Postgres DB.

This is a plain tools server — no auth here. Authn/authz (per-agent scoping,
Keycloak SA JWT validation, audit) is ContextForge's job, in front of this.
M1 ships `get_order`; M4 adds `check_policy`, `get_customer_history`, `flag_ring`.
"""
from __future__ import annotations

import os
from typing import Any

from psycopg_pool import ConnectionPool

_pool = ConnectionPool(
    conninfo=os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://"),
    min_size=1,
    max_size=4,
    open=True,
)


def _rows(sql: str, params: dict) -> list[dict[str, Any]]:
    with _pool.connection() as conn:
        conn.row_factory  # noqa: B018
        cur = conn.execute(sql, params)
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def get_order(order_id: str) -> dict[str, Any]:
    """Return the order header + line items for an order id."""
    orders = _rows(
        "SELECT id::text, user_id::text, status, total, payment_last4, placed_at "
        "FROM orders WHERE id = %(oid)s",
        {"oid": order_id},
    )
    if not orders:
        return {"found": False, "order_id": order_id}
    items = _rows(
        "SELECT product_id::text, name_snapshot, unit_price, qty "
        "FROM order_items WHERE order_id = %(oid)s",
        {"oid": order_id},
    )
    order = orders[0]
    order["total"] = float(order["total"])
    order["placed_at"] = order["placed_at"].isoformat()
    for it in items:
        it["unit_price"] = float(it["unit_price"])
    return {"found": True, "order": order, "items": items}
