"""Real tool implementations, backed by the app Postgres DB.

Plain tools server — no auth here. Authn/authz (per-agent scoping, Keycloak SA
JWT validation, per-call audit) is ContextForge's job, in front of this.

Tools: get_order, check_policy, get_customer_history, flag_ring.
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
    o = orders[0]
    o["total"] = float(o["total"])
    o["placed_at"] = o["placed_at"].isoformat()
    for it in items:
        it["unit_price"] = float(it["unit_price"])
    return {"found": True, "order": o, "items": items}


def check_policy(category: str, days_since_order: int, refund_amount: float) -> dict[str, Any]:
    """Return the active policy-doc text relevant to this return plus the
    machine-checkable window/high-value verdict."""
    docs = _rows(
        "SELECT slug, title, body, version FROM policy_docs "
        "WHERE active = true AND version = (SELECT max(version) FROM policy_docs) "
        "ORDER BY slug",
        {},
    )
    window = 30
    within_window = days_since_order <= window
    high_value = refund_amount > 250
    return {
        "policy_version": docs[0]["version"] if docs else None,
        "standard_window_days": window,
        "within_standard_window": within_window,
        "high_value_needs_human": high_value,
        "category": category,
        "documents": docs,
    }


def get_customer_history(user_id: str) -> dict[str, Any]:
    """Order/return counts + prior denied returns + return rate for a customer."""
    h = _rows(
        """
        SELECT
          (SELECT count(*) FROM orders  WHERE user_id = %(u)s) AS orders,
          (SELECT count(*) FROM returns WHERE user_id = %(u)s) AS returns,
          (SELECT count(*) FROM returns WHERE user_id = %(u)s AND final_decision='deny') AS denied,
          (SELECT count(*) FROM returns WHERE user_id = %(u)s AND final_decision='approve') AS approved
        """,
        {"u": user_id},
    )[0]
    orders = max(int(h["orders"]), 1)
    return {
        "user_id": user_id,
        "lifetime_orders": int(h["orders"]),
        "lifetime_returns": int(h["returns"]),
        "denied_returns": int(h["denied"]),
        "approved_returns": int(h["approved"]),
        "return_rate": round(int(h["returns"]) / orders, 3),
    }


def flag_ring(user_id: str) -> dict[str, Any]:
    """Accounts sharing an address/device/payment fingerprint with this user."""
    rows = _rows(
        """
        SELECT f1.kind, f2.user_id::text AS other_user, f1.value_hash
        FROM fingerprints f1
        JOIN fingerprints f2
          ON f1.value_hash = f2.value_hash AND f1.kind = f2.kind AND f2.user_id <> f1.user_id
        WHERE f1.user_id = %(u)s
        """,
        {"u": user_id},
    )
    linked: dict[str, list[str]] = {}
    for r in rows:
        linked.setdefault(r["other_user"], [])
        if r["kind"] not in linked[r["other_user"]]:
            linked[r["other_user"]].append(r["kind"])
    return {
        "user_id": user_id,
        "linked_account_count": len(linked),
        "linked_accounts": [{"user_id": k, "shared": v} for k, v in linked.items()],
        "is_ring": len(linked) >= 1,
    }
