"""Synthetic return-review dataset for the Behavior risk model.

Thousands of rows with genuine structure — NOT random noise:
  * a high-return-rate cohort (churny/abusive customers)
  * 3 fraud rings, each a cluster of accounts sharing address/device/payment
    fingerprints, with correlated high-value fraudulent returns
  * seasonal return-volume bump in Nov/Dec
  * label `is_fraud` derived from the generative process; the rule inputs are NOT
    all exposed as features (no leakage — e.g. "belongs to ring" is hidden, but
    the *observable* consequence "shares a fingerprint with N accounts" is a
    feature, which is exactly what ring-detection would surface).

Output: ml/data/returns_dataset.csv  +  ml/data/dataset_meta.json (row count,
seed, sha256, class balance). Reproducible: fixed seed.

Run: make dataset   (docker compose run --rm worker python -m ml.generate_dataset)
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import numpy as np
import pandas as pd

SEED = 20260829
OUT = pathlib.Path(__file__).parent / "data"
N_CUSTOMERS = 4000
CATEGORIES = ["Electronics", "Home & Kitchen", "Apparel", "Sports & Outdoors"]
REASONS = ["damaged", "defective", "not_as_described", "wrong_item", "quality",
           "arrived_late", "no_longer_needed"]


def _rng() -> np.random.Generator:
    return np.random.default_rng(SEED)


def build() -> pd.DataFrame:
    rng = _rng()
    rows = []

    # --- customer archetypes -------------------------------------------------
    is_high_return = rng.random(N_CUSTOMERS) < 0.06
    # ring members: 3 rings, sizes 10-16
    ring_of = np.full(N_CUSTOMERS, -1)
    cursor = 0
    for ring_id in range(3):
        size = rng.integers(10, 17)
        ring_of[cursor : cursor + size] = ring_id
        cursor += size
    rng.shuffle(ring_of)  # scatter ring members through the id space

    acct_age = rng.integers(5, 1400, N_CUSTOMERS)
    # ring accounts are young
    acct_age = np.where(ring_of >= 0, rng.integers(3, 90, N_CUSTOMERS), acct_age)

    for cid in range(N_CUSTOMERS):
        ring = ring_of[cid]
        high = is_high_return[cid]

        n_orders = int(rng.integers(1, 25))
        if high:
            n_orders = int(rng.integers(3, 40))
        if ring >= 0:
            n_orders = int(rng.integers(2, 10))

        base_return_rate = 0.08
        if high:
            base_return_rate = rng.uniform(0.45, 0.8)
        if ring >= 0:
            base_return_rate = rng.uniform(0.6, 0.95)

        # observable fingerprint sharing: ring members share with the rest of the ring;
        # a few coincidental non-ring collisions add noise
        if ring >= 0:
            shared_addr = int((ring_of == ring).sum() - 1)
            shared_dev = max(0, shared_addr - int(rng.integers(0, 3)))
            shared_pay = max(0, shared_addr - int(rng.integers(0, 4)))
        else:
            shared_addr = int(rng.poisson(0.05))
            shared_dev = int(rng.poisson(0.03))
            shared_pay = int(rng.poisson(0.02))

        prior_denied = 0
        for _ in range(n_orders):
            if rng.random() > base_return_rate:
                continue
            cat = rng.choice(CATEGORIES, p=[0.3, 0.28, 0.24, 0.18])
            reason = rng.choice(REASONS)
            order_total = float(np.round(rng.uniform(15, 600), 2))
            refund_amount = float(np.round(min(order_total, rng.uniform(10, order_total)), 2))
            days_since_order = int(rng.integers(1, 75))
            month = int(rng.integers(1, 13))
            seasonal = 1 if month in (11, 12) else 0
            photo = int(rng.random() < (0.55 if reason in ("damaged", "defective",
                       "not_as_described", "wrong_item") else 0.15))
            night = int(rng.random() < 0.18)

            # --- fraud generative process --------------------------------
            p_fraud = 0.02
            if high:
                p_fraud += 0.12
            if ring >= 0:
                p_fraud = 0.75
                refund_amount = float(np.round(rng.uniform(120, 600), 2))
                order_total = float(np.round(max(order_total, refund_amount + rng.uniform(0, 40)), 2))
                days_since_order = int(rng.integers(20, 74))
            if reason in ("damaged", "defective") and photo == 0:
                p_fraud += 0.06
            if days_since_order > 45:
                p_fraud += 0.05
            if refund_amount > 300:
                p_fraud += 0.04
            p_fraud = min(p_fraud, 0.97)
            is_fraud = int(rng.random() < p_fraud)

            # denied returns accumulate for fraudulent-ish customers
            denied_now = int(is_fraud and rng.random() < 0.5)
            prior_denied += denied_now

            rows.append(
                {
                    "customer_id": cid,
                    "account_age_days": int(acct_age[cid]),
                    "category": cat,
                    "reason_code": reason,
                    "order_total": order_total,
                    "refund_amount": refund_amount,
                    "days_since_order": days_since_order,
                    "seasonal": seasonal,
                    "photo_provided": photo,
                    "night_submission": night,
                    "customer_lifetime_orders": n_orders,
                    "customer_return_rate": round(base_return_rate, 3),
                    "prior_denied_returns": prior_denied - denied_now,
                    "shared_address_accounts": shared_addr,
                    "shared_device_accounts": shared_dev,
                    "shared_payment_accounts": shared_pay,
                    "is_fraud": is_fraud,
                }
            )

    df = pd.DataFrame(rows)
    return df.sample(frac=1.0, random_state=SEED).reset_index(drop=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = build()
    csv_path = OUT / "returns_dataset.csv"
    df.to_csv(csv_path, index=False)
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    meta = {
        "seed": SEED,
        "rows": len(df),
        "fraud_rate": round(float(df.is_fraud.mean()), 4),
        "sha256": digest,
        "features": [c for c in df.columns if c not in ("is_fraud", "customer_id")],
    }
    (OUT / "dataset_meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    assert 3000 < len(df) < 60000, "unexpected dataset size"
    assert 0.03 < meta["fraud_rate"] < 0.4, "fraud rate outside sane range"
    print("dataset ok")


if __name__ == "__main__":
    main()
