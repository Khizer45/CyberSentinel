# Model Training Guide

You train every model yourself in the notebooks. The API only loads the bundles you export (it never trains,
tunes or downloads models). This guide gives the exact procedure.

## 1. Environment

Python **3.12 or 3.13** (the pinned numpy 2.5 / scipy 1.18 / xgboost 3.4 require ≥ 3.12; verified on 3.13).

```bash
cd notebooks
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # includes ../backend/requirements-ml.txt (same ML pins as the API)
```

The notebook environment and the backend environment **must** use the same `backend/requirements-ml.txt`
versions. The bundle manifest records scikit-learn / xgboost / numpy versions and the API refuses incompatible
artifacts.

## 2. Data

Place the official files as described in `data/README.md`:

* CIC-IDS2017 → `data/raw/cicids2017/*.csv` (MachineLearningCVE or TrafficLabelling CSVs)
* UNSW-NB15 → `data/raw/unsw_nb15/UNSW_NB15_training-set.csv` and `UNSW_NB15_testing-set.csv`

## 3. Configuration

All notebook settings are environment variables (documented in `notebooks/nb_utils/config.py`). The most useful:

| Variable | Default | Purpose |
|---|---|---|
| `CS_DATASET_FAMILY` | `cicids2017` | `cicids2017` or `unsw_nb15` |
| `CS_RANDOM_SEED` | `42` | seed for splits, sampling, estimators |
| `CS_MAX_ROWS_PER_FILE` | unset | quick iteration only — never for reported results |
| `CS_N_JOBS` | `-1` | CPU cores for scikit-learn/XGBoost |
| `CS_LINEAR_SAMPLE` | `200000` | training subsample for logistic regression and linear SVM |
| `CS_SEMI_POOL_SIZE` / `CS_SEMI_EVAL_SIZE` | `20000` | label-propagation pool / evaluation sample |
| `CS_LABEL_BUDGETS` | `0.01,0.05,0.1,0.2,0.4,1.0` | label budgets (SRS 1.4) |
| `CS_SEMI_SEEDS` | `0,1,2` | repetitions per budget |
| `CS_CALIBRATE` | `0` | `1` = isotonic calibration of the selected classifier on half of validation |
| `CS_DROP_SHORTCUT_FEATURES` | `0` | `1` = remove shortcut candidates (ablation run) |
| `CS_MODEL_VERSION` | `1.0.0` | version of the exported bundle (bump for every new export) |
| `CS_EXPORT_BINARY` / `CS_EXPORT_SEMI` | `0` | also export the binary bundle / a Label Spreading bundle |
| `CS_OVERWRITE_BUNDLE` | `0` | allow re-exporting the same name+version (prefer bumping the version) |

Example (Linux/macOS):

```bash
export CS_DATASET_FAMILY=unsw_nb15
jupyter lab            # open the notebooks folder and run 01 → 06
```

Windows PowerShell: `$env:CS_DATASET_FAMILY = "unsw_nb15"` before `jupyter lab`.

## 4. Procedure and what each notebook guarantees

| Step | Notebook | Key guarantees |
|---|---|---|
| Audit | 01 | provenance hashes, header mapping, missing/∞ counts, label map, imbalance, duplicates, shortcut screening |
| Split & fit preprocessing | 02 | dedupe **before** split; CIC stratified 70/15/15; UNSW official test partition; cross-split duplicates removed; preprocessor fitted on **train only**; leakage checklist asserted |
| Supervised | 03 | candidates compared on **validation**; XGBoost early-stops on validation; binary threshold and `needs_review` confidence chosen on validation; calibration evaluated on a held-out half; importance; shortcut ablation |
| Unsupervised | 04 | Isolation Forest threshold = 99th percentile of **benign validation** scores; score direction asserted; clustering exploratory; unknown-attack hold-out |
| Semi-supervised | 05 | labels masked to `-1` before fitting; per-class budgets; k tuned on validation; results on a test sample never used for choices |
| Final evaluation & export | 06 | first use of test labels for comparison; risk-policy review; bundle export; golden parity and engine/notebook equality asserted |

Outputs: `reports/<family>/` (metrics, figures), `model_artifacts/experiments/*.json` (shown in the UI's Model
Lab), `model_artifacts/bundles/<name>/<version>/` and an entry in `model_artifacts/registry.json`.

## 5. Metrics reported (all measured by the notebooks)

Per model: per-class precision/recall/F1 and support, macro and weighted F1, accuracy, confusion matrix,
false-alarm rate (benign flows predicted as attacks), attack-score ROC-AUC and PR-AUC (only when both classes are
present), one-vs-rest macro ROC-AUC (classes absent from a split are skipped), training time, inference latency
(ms/record, records/s) and compressed model size. Anomaly detection: ROC-AUC, PR-AUC, FPR/recall at the threshold
and per-category flag rates. Semi-supervised: macro-F1 per budget and seed, transductive accuracy, paired ΔF1 vs the
supervised baseline.

The SRS acceptance targets (e.g. F1 > 90 %) are hypotheses to test, not results; record what your runs measure.

## 6. Hand-over to the backend

After notebook 06 prints the bundle name and version:

```bash
cd backend && source .venv/bin/activate
python -m app.cli models sync                                   # validates and registers new bundles as draft
python -m app.cli models approve unsw-nb15-xgboost-multiclass 1.0.0
python -m app.cli models verify  unsw-nb15-xgboost-multiclass 1.0.0   # integrity + golden parity in the API env
```

(Use the model name your run printed.) The bundle is then selectable for analysis jobs. See
`docs/model_artifact_integration_guide.md`.

## 7. Practical notes

* **Memory.** CIC-IDS2017 (~2.8 M rows, 77 features) needs roughly 6–8 GB RAM in notebooks 01–02. Use
  `CS_MAX_ROWS_PER_FILE` only to iterate quickly.
* **Rare classes.** Classes with fewer than 6 rows after deduplication (CIC-IDS2017: possibly *Heartbleed*) are kept
  in training only and reported; their test metrics are undefined.
* **Reproducibility.** Seeds are fixed; the manifest records seed, split strategy, row counts, library versions and
  file hashes of the raw inputs are in `preprocessing_report.json`.
* **Smoke test.** `CS_RUN_NOTEBOOK_SMOKE=1 python -m pytest tests -q` (inside `notebooks/`) runs all notebooks on
  synthetic format-only fixtures in temporary folders — use it after editing notebooks.
