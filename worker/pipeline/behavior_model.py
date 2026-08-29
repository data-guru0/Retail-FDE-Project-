"""Behavior risk: the registered sklearn model (loaded by version) + a real SQL
ring-detection query over `fingerprints`.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import threading

import structlog

log = structlog.get_logger()
_lock = threading.Lock()
_bundle = None
_version = None

REGISTRY = pathlib.Path("/app/../ml/registry")  # worker mounts ./ml at /app/ml in M4
_ALT = pathlib.Path("/app/ml/registry")


def _load():
    global _bundle, _version
    if _bundle is not None:
        return
    with _lock:
        if _bundle is not None:
            return
        import joblib

        reg = _ALT if _ALT.exists() else REGISTRY
        latest = reg / "LATEST"
        if not latest.exists():
            log.warning("behavior_model.no_registered_model")
            return
        _version = latest.read_text().strip()
        _bundle = joblib.load(reg / _version / "model.joblib")
        log.info("behavior_model.loaded", version=_version)


async def _extra_features(ctx: dict) -> dict:
    from pipeline import db

    row = await db.fetchrow(
        """
        SELECT
          extract(epoch from (now() - u.created_at))/86400 AS account_age_days,
          (SELECT count(*) FROM returns r2
             WHERE r2.user_id = %(uid)s AND r2.final_decision = 'deny') AS prior_denied_returns
        FROM users u WHERE u.id = %(uid)s
        """,
        {"uid": ctx["user_id"]},
    ) or {}
    fp = await db.fetchrow(
        """
        SELECT
          coalesce(count(*) FILTER (WHERE kind='address'),0) AS a,
          coalesce(count(*) FILTER (WHERE kind='device'),0)  AS d,
          coalesce(count(*) FILTER (WHERE kind='payment'),0)  AS p
        FROM fingerprints f
        WHERE f.value_hash IN (SELECT value_hash FROM fingerprints WHERE user_id = %(uid)s)
          AND f.user_id <> %(uid)s
        """,
        {"uid": ctx["user_id"]},
    ) or {}
    now = dt.datetime.now(dt.UTC)
    return {
        "account_age_days": float(row.get("account_age_days") or 365),
        "prior_denied_returns": int(row.get("prior_denied_returns") or 0),
        "shared_address_accounts": int(fp.get("a") or 0),
        "shared_device_accounts": int(fp.get("d") or 0),
        "shared_payment_accounts": int(fp.get("p") or 0),
        "seasonal": 1 if now.month in (11, 12) else 0,
        "night_submission": 1 if now.hour < 6 or now.hour >= 22 else 0,
    }


def _feature_row(ctx: dict, extra: dict):
    import pandas as pd

    age_days = ctx.get("age_since_order")
    days_since_order = round(age_days.total_seconds() / 86400, 1) if age_days else 30.0
    orders = max(int(ctx["user_order_count"]), 1)
    row = {
        "account_age_days": extra["account_age_days"],
        "order_total": float(ctx["order_total"]),
        "refund_amount": float(ctx["amount"]),
        "days_since_order": days_since_order,
        "seasonal": extra["seasonal"],
        "photo_provided": 1 if ctx["photo_count"] > 0 else 0,
        "night_submission": extra["night_submission"],
        "customer_lifetime_orders": orders,
        "customer_return_rate": round(int(ctx["user_return_count"]) / orders, 3),
        "prior_denied_returns": extra["prior_denied_returns"],
        "shared_address_accounts": extra["shared_address_accounts"],
        "shared_device_accounts": extra["shared_device_accounts"],
        "shared_payment_accounts": extra["shared_payment_accounts"],
        "category": ctx["category"],
        "reason_code": ctx["reason_code"],
    }
    return pd.DataFrame([row])


_extra_cache: dict = {}


def risk_score(ctx: dict) -> tuple[float, str, dict]:
    """(calibrated_risk_0_1, model_version, features). Synchronous — the extra
    features are fetched by the async caller and stashed on ctx first."""
    _load()
    extra = ctx["_behavior_extra"]
    X = _feature_row(ctx, extra)
    feats = X.iloc[0].to_dict()
    if _bundle is None:
        # ponytail: transparent fallback until a model is registered (make train).
        r = min(1.0, 0.05
                + 0.4 * feats["customer_return_rate"]
                + 0.15 * (feats["shared_address_accounts"] > 0)
                + 0.1 * (feats["refund_amount"] > 300)
                + 0.05 * (feats["days_since_order"] > 45))
        return round(float(r), 4), "heuristic-fallback", feats
    import pandas as pd

    Xd = pd.get_dummies(X, columns=_bundle["cat_cols"], dtype=float)
    Xd = Xd.reindex(columns=_bundle["features"], fill_value=0.0)
    p = float(_bundle["model"].predict_proba(Xd)[0, 1])
    return round(p, 4), _version, feats


async def prepare(ctx: dict) -> None:
    ctx["_behavior_extra"] = await _extra_features(ctx)


async def ring_accounts(user_id: str) -> list[str]:
    from pipeline import db

    rows = await db.fetchall(
        """
        SELECT DISTINCT f2.user_id::text AS uid
        FROM fingerprints f1
        JOIN fingerprints f2
          ON f1.value_hash = f2.value_hash AND f1.kind = f2.kind AND f2.user_id <> f1.user_id
        WHERE f1.user_id = %(uid)s
        """,
        {"uid": user_id},
    )
    return [r["uid"] for r in rows]
