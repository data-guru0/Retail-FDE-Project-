# Model Card — Behavior risk model `v20260829-021222`

## Intended use
Produces a calibrated fraud/abuse **risk score in [0,1]** for a single
return/refund request. Consumed by the Behavior agent as ONE signal into the
Decision agent. **Never** a lone auto-deny; a human confirms every denial.

## Not for
Any decision about a person outside this return-review context. No
protected-attribute data is used or available (see docs/FAIRNESS.md).

## Training data
Synthetic (`ml/generate_dataset.py`, seed 20260829), 6797 rows.
Dataset sha256: `d9ef6e8f21dc0335d8fe232148e86324427e8e1396ca6f7ea8769e0045804aa8`. Injected structure: a high-return cohort, 3 fraud
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
  "roc_auc": 0.8066,
  "pr_auc": 0.6127,
  "precision@0.5": 0.6005,
  "recall@0.5": 0.5517,
  "f1@0.5": 0.5751,
  "brier": 0.1569,
  "test_n": 1360,
  "test_fraud_rate": 0.2985
}
```

## Top features (permutation importance, ROC-AUC)
```json
[
  {
    "feature": "customer_return_rate",
    "importance": 0.2119
  },
  {
    "feature": "refund_amount",
    "importance": 0.0181
  },
  {
    "feature": "days_since_order",
    "importance": 0.0179
  },
  {
    "feature": "prior_denied_returns",
    "importance": 0.0131
  },
  {
    "feature": "shared_address_accounts",
    "importance": 0.0081
  },
  {
    "feature": "order_total",
    "importance": 0.0075
  },
  {
    "feature": "account_age_days",
    "importance": 0.0034
  },
  {
    "feature": "photo_provided",
    "importance": 0.0027
  },
  {
    "feature": "night_submission",
    "importance": 0.0026
  },
  {
    "feature": "customer_lifetime_orders",
    "importance": 0.0013
  },
  {
    "feature": "shared_payment_accounts",
    "importance": 0.0013
  },
  {
    "feature": "category_Sports & Outdoors",
    "importance": 0.0008
  },
  {
    "feature": "reason_code_defective",
    "importance": 0.0007
  },
  {
    "feature": "reason_code_not_as_described",
    "importance": 0.0007
  },
  {
    "feature": "category_Apparel",
    "importance": 0.0006
  }
]
```

## Limitations
- Trained on synthetic data; real-world drift is expected. Retrain via
  `make dataset && make train` and register the new version.
- Calibration holds near the training prior (~fraud rate above); shifts need
  recalibration.
- Correlated features (the shared-fingerprint trio) — importance is split across them.
