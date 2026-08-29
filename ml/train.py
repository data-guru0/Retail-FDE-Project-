"""Train + calibrate the Behavior risk model.

Gradient-boosted trees + isotonic calibration on a held-out split. Fixed seed,
train/val/test split, metrics JSON, feature importance, MODEL_CARD.md, dataset
snapshot hash. Versioned artifact under ml/registry/<version>/ and a row in
`model_registry` so the Behavior agent can load it by version.

Run: make train   (docker compose run --rm worker python -m ml.train)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

SEED = 20260829
HERE = pathlib.Path(__file__).parent
DATA = HERE / "data" / "returns_dataset.csv"
REGISTRY = HERE / "registry"

CAT_COLS = ["category", "reason_code"]
NUM_COLS = [
    "account_age_days", "order_total", "refund_amount", "days_since_order",
    "seasonal", "photo_provided", "night_submission", "customer_lifetime_orders",
    "customer_return_rate", "prior_denied_returns", "shared_address_accounts",
    "shared_device_accounts", "shared_payment_accounts",
]


def _features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    X = pd.get_dummies(df[NUM_COLS + CAT_COLS], columns=CAT_COLS, dtype=float)
    return X, list(X.columns)


def main() -> None:
    if not DATA.exists():
        raise SystemExit("run `make dataset` first — ml/data/returns_dataset.csv missing")
    df = pd.read_csv(DATA)
    dataset_hash = hashlib.sha256(DATA.read_bytes()).hexdigest()
    X, feat_names = _features(df)
    y = df["is_fraud"].to_numpy()

    X_tr, X_tmp, y_tr, y_tmp = train_test_split(
        X, y, test_size=0.4, random_state=SEED, stratify=y
    )
    X_val, X_te, y_val, y_te = train_test_split(
        X_tmp, y_tmp, test_size=0.5, random_state=SEED, stratify=y_tmp
    )

    base = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, max_depth=6,
        l2_regularization=1.0, random_state=SEED,
    )
    base.fit(X_tr, y_tr)
    model = CalibratedClassifierCV(base, method="isotonic", cv="prefit")
    model.fit(X_val, y_val)

    p_te = model.predict_proba(X_te)[:, 1]
    pred = (p_te >= 0.5).astype(int)
    metrics = {
        "roc_auc": round(float(roc_auc_score(y_te, p_te)), 4),
        "pr_auc": round(float(average_precision_score(y_te, p_te)), 4),
        "precision@0.5": round(float(precision_score(y_te, pred, zero_division=0)), 4),
        "recall@0.5": round(float(recall_score(y_te, pred, zero_division=0)), 4),
        "f1@0.5": round(float(f1_score(y_te, pred, zero_division=0)), 4),
        "brier": round(float(brier_score_loss(y_te, p_te)), 4),
        "test_n": int(len(y_te)),
        "test_fraud_rate": round(float(y_te.mean()), 4),
    }

    # permutation-free importance proxy: the base HGB's per-feature gain isn't
    # exposed; use a quick permutation on the test set.
    from sklearn.inspection import permutation_importance

    imp = permutation_importance(model, X_te, y_te, n_repeats=5, random_state=SEED, scoring="roc_auc")
    importance = sorted(
        ({"feature": f, "importance": round(float(v), 4)}
         for f, v in zip(feat_names, imp.importances_mean, strict=True)),
        key=lambda d: -d["importance"],
    )[:15]

    version = dt.datetime.now(dt.UTC).strftime("v%Y%m%d-%H%M%S")
    out = REGISTRY / version
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": feat_names, "num_cols": NUM_COLS,
                 "cat_cols": CAT_COLS}, out / "model.joblib")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (out / "feature_importance.json").write_text(json.dumps(importance, indent=2))
    _write_card(out, version, dataset_hash, metrics, importance, len(df))
    _register(version, out, metrics, dataset_hash)

    print(json.dumps({"version": version, **metrics}, indent=2))
    assert metrics["roc_auc"] > 0.75, "model underperforms — investigate before shipping"
    print("train ok")


def _write_card(out, version, dhash, metrics, importance, n_rows) -> None:
    card = f"""# Model Card — Behavior risk model `{version}`

## Intended use
Produces a calibrated fraud/abuse **risk score in [0,1]** for a single
return/refund request. Consumed by the Behavior agent as ONE signal into the
Decision agent. **Never** a lone auto-deny; a human confirms every denial.

## Not for
Any decision about a person outside this return-review context. No
protected-attribute data is used or available (see docs/FAIRNESS.md).

## Training data
Synthetic (`ml/generate_dataset.py`, seed {SEED}), {n_rows} rows.
Dataset sha256: `{dhash}`. Injected structure: a high-return cohort, 3 fraud
rings sharing address/device/payment fingerprints, Nov/Dec seasonality. The
label is generated from a stochastic process; ring membership itself is hidden
from features (only its observable consequence — shared-fingerprint counts — is a
feature).

## Model
`HistGradientBoostingClassifier` + isotonic calibration (`CalibratedClassifierCV`,
prefit) on a 60/20/20 train/val/test split, seed {SEED}.

## Test metrics
```json
{json.dumps(metrics, indent=2)}
```

## Top features (permutation importance, ROC-AUC)
```json
{json.dumps(importance, indent=2)}
```

## Limitations
- Trained on synthetic data; real-world drift is expected. Retrain via
  `make dataset && make train` and register the new version.
- Calibration holds near the training prior (~fraud rate above); shifts need
  recalibration.
- Correlated features (the shared-fingerprint trio) — importance is split across them.
"""
    (out / "MODEL_CARD.md").write_text(card)
    # keep the canonical copy in docs/
    (pathlib.Path(__file__).parents[1] / "docs" / "MODEL_CARD.md").write_text(card)


def _register(version, out, metrics, dhash) -> None:
    import os

    import psycopg

    dsn = os.environ.get("DATABASE_URL", "")
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    if not dsn:
        from pipeline.settings import get_settings

        dsn = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(
            "INSERT INTO model_registry (name, version, artifact_path, metrics, dataset_hash) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (name, version) DO UPDATE "
            "SET metrics = EXCLUDED.metrics",
            ("behavior_risk", version, str(out / "model.joblib"), json.dumps(metrics), dhash),
        )
    (REGISTRY / "LATEST").write_text(version)
    print(f"registered behavior_risk {version}")


if __name__ == "__main__":
    main()
