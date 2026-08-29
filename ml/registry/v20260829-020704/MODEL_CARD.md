# Model Card — Behavior risk model `v20260829-020704`

## Intended use
Produces a calibrated fraud/abuse **risk score in [0,1]** for a single
return/refund request. Consumed by the Behavior agent as ONE signal into the
Decision agent. **Never** a lone auto-deny; a human confirms every denial.

## Not for
Any decision about a person outside this return-review context. No
protected-attribute data is used or available (see docs/FAIRNESS.md).

## Training data
Synthetic (`ml/generate_dataset.py`, seed 20260829), 6872 rows.
Dataset sha256: `ef95c142304dbff498853361a44582db9827dfc5b2a59ffa5390cdd3c96a7894`. Injected structure: a high-return cohort, 3 fraud
rings sharing address/device/payment fingerprints, Nov/Dec seasonality. The
label is generated from a stochastic process; ring membership itself is hidden
from features (only its observable consequence — shared-fingerprint counts — is a
feature).

## Model
`HistGradientBoostingClassifier` + isotonic calibration (`CalibratedClassifierCV`,
prefit) on a 60/20/20 train/val/test split, seed 20260829.

## Test metrics
```json
{
  "roc_auc": 0.6729,
  "pr_auc": 0.2954,
  "precision@0.5": 0.7857,
  "recall@0.5": 0.1272,
  "f1@0.5": 0.2189,
  "brier": 0.0982,
  "test_n": 1375,
  "test_fraud_rate": 0.1258
}
```

## Top features (permutation importance, ROC-AUC)
```json
[
  {
    "feature": "customer_return_rate",
    "importance": 0.1001
  },
  {
    "feature": "days_since_order",
    "importance": 0.0351
  },
  {
    "feature": "refund_amount",
    "importance": 0.0157
  },
  {
    "feature": "shared_address_accounts",
    "importance": 0.0061
  },
  {
    "feature": "seasonal",
    "importance": 0.0037
  },
  {
    "feature": "night_submission",
    "importance": 0.0024
  },
  {
    "feature": "photo_provided",
    "importance": 0.0016
  },
  {
    "feature": "reason_code_arrived_late",
    "importance": 0.0016
  },
  {
    "feature": "reason_code_quality",
    "importance": 0.0015
  },
  {
    "feature": "reason_code_wrong_item",
    "importance": 0.0009
  },
  {
    "feature": "account_age_days",
    "importance": 0.0008
  },
  {
    "feature": "reason_code_no_longer_needed",
    "importance": 0.0005
  },
  {
    "feature": "category_Apparel",
    "importance": 0.0004
  },
  {
    "feature": "category_Sports & Outdoors",
    "importance": -0.0002
  },
  {
    "feature": "reason_code_damaged",
    "importance": -0.0002
  }
]
```

## Limitations
- Trained on synthetic data; real-world drift is expected. Retrain via
  `make dataset && make train` and register the new version.
- Calibration holds near the training prior (~fraud rate above); shifts need
  recalibration.
- Correlated features (the shared-fingerprint trio) — importance is split across them.
