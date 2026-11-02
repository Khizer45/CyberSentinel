# Model Artifact Integration Guide

How exported model bundles become usable by the API, and exactly what the backend checks.

## 1. Paths the backend expects

| Setting (`backend/.env`) | Default | Meaning |
|---|---|---|
| `MODEL_DIR` | `../model_artifacts` (relative to `backend/`) | trusted root; every bundle path is confined to it |
| `MODEL_MANIFEST` | `${MODEL_DIR}/registry.json` | registry index written by notebook 06 |
| `EXPERIMENTS_DIR` | `${MODEL_DIR}/experiments` | experiment JSON files served read-only |
| `MAX_ARTIFACT_MB` | `2048` | per-file size limit checked before loading |
| `MODEL_CACHE_SIZE` | `4` | number of verified bundles kept in memory |
| `MODEL_PRELOAD` | `false` | verify and load approved bundles at startup |

A bundle lives at `MODEL_DIR/bundles/<model_name>/<version>/` and is referenced in the database by that relative
path (`model_versions.artifact_uri`), never by an absolute path, and the path is never returned by the API.

## 2. Bundle contents and manifest (schema 1.0)

`manifest.json` is validated by `app.ml.artifacts.manifest.BundleManifest` (unknown fields are rejected):

| Section | Content |
|---|---|
| `bundle` | `model_name`, `version`, `model_type` (`classifier`/`anomaly_detector`/`semi_supervised`/`ensemble`), description, creation time/source |
| `dataset` | family, `schema_version`, source, split strategy, seed, train/validation/test row counts, label-mapping version, rare-class policy |
| `features` | ordered `input_features` (name, dtype, training categories), `transformed_feature_names`, `transformed_feature_sources`, benign reference statistics |
| `preprocessing` | `preprocessing_version`, artifact file + SHA-256 + size, steps |
| `components.classifier` | artifact, estimator class, task, `classes` (index = encoded label), `benign_class`, `probability_calibrated` + evidence, `decision_threshold` (binary), `min_confidence`, explanation method, global importance |
| `components.anomaly_detector` | artifact, estimator class, score definition, `score_direction = higher_is_more_anomalous`, `threshold`, threshold method, `reference_points {benign_median, threshold, upper}`, training population |
| `metrics` | measured validation/test metrics (bounded JSON) |
| `runtime` | Python, numpy, pandas, scikit-learn, xgboost, joblib versions at export |
| `golden` | golden input CSV + expected outputs (hashes, row count) |
| `limitations` | free-text limitations shown on the model card |

## 3. Registration and approval

```bash
cd backend && source .venv/bin/activate
python -m app.cli models sync              # registry.json → model_versions rows (status draft)
python -m app.cli models list
python -m app.cli models approve <model_name> <version>
python -m app.cli models verify  <model_name> <version>
python -m app.cli models retire  <model_name> <version>
python -m app.cli models revoke  <model_name> <version> --reason "tampering suspected"
```

`sync` loads each bundle completely before registering it (all checks in §4 plus golden parity), stores
metadata (classes, thresholds, measured metrics, explanation method, calibration flag) and pins
`artifact_sha256 = SHA-256(manifest.json)`. Bundles already registered with the same hash are skipped; a different
hash for an existing name/version is refused (bump the version instead). Administrators can also approve, retire,
revoke and verify from the **Models** page. Status rules: `draft → approved | revoked`, `approved → retired | revoked`,
`retired → approved | revoked`; `revoked` is terminal and such bundles are never loaded again.

## 4. Checks at load time (fail closed)

1. Path confinement to `MODEL_DIR` (absolute paths, `..`, backslashes and symlink escapes rejected).
2. `manifest.json` size ≤ 5 MiB and SHA-256 equal to the database pin.
3. Manifest schema validation (supported `manifest_version`, consistent sections, features ⊆ dataset schema).
4. Name, version, feature-schema and preprocessing versions equal to the database row.
5. Runtime compatibility: scikit-learn and xgboost major.minor and numpy major must match the export environment.
6. Each component: inside the bundle directory, size ≤ `MAX_ARTIFACT_MB`, SHA-256 equal to the manifest.
7. `joblib.load`, then class allowlist (ColumnTransformer/Pipeline with SimpleImputer, scalers, OneHotEncoder,
   FunctionTransformer with allowlisted functions; RandomForest/ExtraTrees/DecisionTree/HistGradientBoosting/
   LogisticRegression/CalibratedClassifierCV/LabelSpreading/LabelPropagation/XGBClassifier; IsolationForest).
8. Interface checks: preprocessor input names/order and output names equal the manifest; classifier exposes
   `predict_proba` with `classes_ == [0..K-1]` and the right input width; anomaly detector exposes `score_samples`.

| Failure | API behaviour |
|---|---|
| bundle/manifest/file missing | `503 model_unavailable`, audit event, health shows the model registry as degraded |
| checksum mismatch | `503 model_unavailable`, audit `model.integrity.failure` |
| incompatible versions / types / features | `503 model_unavailable` |
| model not approved / revoked | `409 model_not_approved` for new jobs |

## 5. Inference contract

The API reads the uploaded CSV with the same reader the notebooks used, selects `features.input_features` in
manifest order, applies the stored preprocessor (`transform` only) and calls `predict_proba` / `score_samples`.
Outputs are mapped to the prediction fields documented in `docs/database_documentation.md` §4.1; the risk policy
(`docs/risk_scoring_policy.md`) is applied afterwards. Every prediction is traceable to the job's model version
(and therefore manifest hash, preprocessing version and feature schema) and risk-policy version.

## 6. Parity verification

`python -m app.cli models verify <name> <version>` re-runs the loaded bundle on `golden_input.csv` inside the API
environment and compares with `golden_expected.json` (identical labels; scores within 1e-9). Run it after
upgrading Python packages or moving artifacts between machines.

## 7. Replacing or rolling back a model

Export a new version from notebook 06 (`CS_MODEL_VERSION=1.1.0`), `sync`, `approve` the new version and `retire`
the old one. Jobs keep referencing the version they used, so historical results stay traceable. To roll back,
re-approve the retired version.
