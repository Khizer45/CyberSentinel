# Risk Scoring Policy (version 1.0.0)

Risk scores are **application policy outputs** on a 0–100 scale. They combine model outputs with documented,
versioned rules. A risk score is **not a probability** and must not be presented as one (ML-07).

Policy file: `backend/config/risk_policy.json` (path configurable with `RISK_POLICY_PATH`). It is validated at
startup; every analysis job stores the `risk_policy_version` it used, and every explained prediction stores a
per-row breakdown. Implementation: `backend/app/ml/risk/` (pure functions with unit tests).

## 1. Inputs

| Symbol | Source | Range | Notes |
|---|---|---|---|
| `p_k` | classifier `predict_proba` for class *k* | [0, 1] | calibrated only if the manifest says so |
| `w(k)` | `category_weights` (default 1.0; overrides per category) | [0, 1] | severity multiplier per attack category |
| `s` | anomaly score `−score_samples(x)` | (0, 1] for Isolation Forest | higher = more anomalous |
| `median, threshold, upper` | manifest `reference_points` (from validation data) | strictly increasing | anchors for the anomaly component |
| `is_anomaly` | `s ≥ threshold` | bool | |
| `needs_review` | top-class score `< min_confidence` | bool | |

## 2. Formula

```
C = Σ_{k ≠ benign} p_k · w(k)                       classifier component (expected attack severity)
A = interp(s; [median, threshold, upper] → [0, 0.5, 1]), clipped to [0, 1]     anomaly component
base = w_c · C + w_a · A        when both components exist (w_c + w_a = 1)
base = C  or  base = A          when only one model component ran
risk = 100 · clip(base, 0, 1)
if is_anomaly:     risk = max(risk, floor_anomaly)
if needs_review:   risk = max(risk, floor_needs_review)
risk_score = round(risk, 2)
risk_band  = highest band whose min_score ≤ risk_score
is_alert   = risk_band ≥ alerting.min_band
             or (alerting.alert_on_anomaly and is_anomaly)
             or (alerting.alert_on_needs_review and needs_review)
```

## 3. Default values (placeholders — review them)

| Parameter | Default |
|---|---|
| weights | classifier 0.7, anomaly 0.3 |
| category weights | default 1.0; `PortScan` 0.6, `Reconnaissance` 0.6, `Fuzzers` 0.7, `Analysis` 0.7 |
| floors | anomaly 25, needs_review 25 |
| bands | low ≥ 0, medium ≥ 25, high ≥ 50, critical ≥ 75 |
| alerting | min band `high`; anomaly-only and needs-review alerts disabled |

These defaults are **not** derived from data. Notebook 06 evaluates the active policy on validation and test data
(alert rate, attack recall at alert, alert precision, false alerts per 10 000 benign flows) and writes a candidate
policy with a validation-optimized classifier weight to `reports/<family>/risk_policy.candidate.json`. Copy values
into `backend/config/risk_policy.json` only after review, and **bump `policy_version`** whenever any value changes.

## 4. Worked example (default policy)

Classes `[Benign, DoS, PortScan]`, probabilities `[0.02, 0.95, 0.03]`, anomaly reference `(0.45, 0.62, 0.80)`,
anomaly score `0.70` (flagged):

* `C = 0.95·1.0 + 0.03·0.6 = 0.968`
* `A = 0.5 + 0.5 · (0.70 − 0.62)/(0.80 − 0.62) = 0.722`
* `base = 0.7·0.968 + 0.3·0.722 = 0.8943` → `risk_score = 89.43` → band **critical** → alert.

(This example is verified by `backend/tests/ml/test_risk_scoring.py`.)

## 5. Interpretation rules for the UI and API

* Show `risk_score` as "policy risk score (0–100)", never as a percentage likelihood.
* Show `probability` only when it is not null (calibrated); otherwise show `classifier_score` labelled
  "uncalibrated model score".
* Show anomaly flags separately from classifications ("unusual" ≠ "malicious").
* Always show the model version, policy version and timestamp with a result.
