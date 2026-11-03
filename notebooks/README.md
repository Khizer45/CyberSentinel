# Notebooks — training, evaluation and export

Run in order for one dataset family at a time (`CS_DATASET_FAMILY=cicids2017` or `unsw_nb15`):

| Notebook | Produces |
|---|---|
| `01_data_exploration.ipynb` | data audit: header mapping, missing/infinite values, labels, imbalance, duplicates, shortcut screening |
| `02_preprocessing.ipynb` | deduplicated, leakage-checked train/validation/test splits + preprocessor fitted on train |
| `03_supervised_learning.ipynb` | LR / RF / XGBoost / linear SVM (binary + multi-class), validation selection, thresholds, calibration, importance, shortcut ablation |
| `04_unsupervised_learning.ipynb` | Isolation Forest (benign-only vs unsupervised), validation threshold, K-Means/DBSCAN exploration, unknown-attack hold-out |
| `05_semi_supervised_learning.ipynb` | Label Spreading / Label Propagation vs supervised baseline at 1–100 % label budgets |
| `06_model_evaluation.ipynb` | test-set comparison, risk-policy review, **bundle export** + golden parity verification |

Setup, configuration variables and the full procedure are in `docs/model_training_guide.md`.

`nb_utils/` contains training-side helpers (splits, model factories, label masking, plotting). It may fit models;
the backend package (`backend/app/ml`) may not, and the API never imports `nb_utils`.

`tests/` contains a smoke test that executes all six notebooks on **synthetic, format-only fixtures** in temporary
directories (`CS_RUN_NOTEBOOK_SMOKE=1 python -m pytest tests -q`). Those fixtures carry no information about real
traffic; never use them for results.
