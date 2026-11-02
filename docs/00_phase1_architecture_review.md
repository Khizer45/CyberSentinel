# Phase 1 — Requirements & Architecture Review

**Product:** CyberSentinel — ML-Based Network Threat Detection Platform
**Status:** Baseline for implementation (Phases 2–7). Design decisions below are reflected in the code in this repository.
**Inputs reviewed (9 documents):** SRS, Project Proposal, PRD, Technical Requirements Specification, Security Requirements
Specification, Software Workflow & Developer/User Manual, System Architecture Document (SAD), Database ERD & Data
Dictionary, Requirements Traceability Matrix (RTM). The tenth document listed in the master prompt — the **API
Specification** — was not supplied (see conflict C-02).

> Nothing in this document claims measured model performance. All model metrics are produced by the notebooks when you
> run them on the real datasets.

---

## 1. Understanding of CyberSentinel

CyberSentinel is a defensive, research-oriented network intrusion and threat detection platform. It ingests
**flow-level** records (CSV exports of CIC-IDS2017 or UNSW-NB15 style features — no packet payloads), applies
**pre-trained, integrity-verified** ML artifacts, and produces for every record:

| Output | Meaning | Never presented as |
|---|---|---|
| `predicted_label` | Classifier's canonical class (e.g. `DoS`), `needs_review` when confidence is below the model's threshold, `unclassified` in anomaly-only mode | Proof of compromise |
| `probability` | Calibrated P(malicious) — **only** when the artifact manifest declares that calibration was evaluated | — |
| `classifier_score` | Raw (uncalibrated) model attack score in [0,1] | A probability |
| `anomaly_score` / `is_anomaly` | Isolation-Forest abnormality (higher = more anomalous) and threshold flag | An attack verdict |
| `risk_score` / `risk_band` | Versioned **policy** score 0–100 and band low/medium/high/critical | A model probability |
| `explanation` | Feature attributions / reason codes with an explicit non-causal disclaimer | Causal explanation |

Analysts upload datasets, run asynchronous analysis jobs, triage alerts (high-risk predictions), record append-only
dispositions, and export authorized results. Researchers train and evaluate supervised, unsupervised and
semi-supervised models **in Jupyter notebooks only**; the API never trains, tunes or downloads models.

## 2. Architecture summary

```
Browser (React + TS)  ──HTTPS/JSON──▶  FastAPI /api/v1  ──▶  services  ──▶  repositories ──▶ PostgreSQL
   in-memory access token              routers: HTTP contract,  │                          (7 tables, Alembic)
   HttpOnly refresh cookie             auth deps, validation    │
                                                                 ├──▶ job runner (bounded in-process pool)
                                                                 └──▶ app.ml runtime library
                                                                        ├─ dataset schemas & cleaning
                                                                        ├─ artifact integrity + loader ──▶ MODEL_DIR (trusted, read-only)
                                                                        ├─ inference engine
                                                                        ├─ risk policy scoring
                                                                        └─ explanations
Engineering zone (offline): notebooks/ ──imports──▶ backend/app/ml (same code = train/serve parity)
                            notebooks/nb_utils (training-only helpers) ──exports──▶ model_artifacts/bundles/*
```

Key properties:

* **Training/runtime separation (SEC-07).** Training-only code (splits, label masking, estimator fitting, plotting)
  lives in `notebooks/nb_utils`. The backend package contains no `fit` calls and no network clients; an automated
  architecture test enforces this.
* **Train/serve parity (ML-02, FR-08).** Column normalization, label normalization, cleaning and the custom
  transforms referenced inside pickled preprocessors live in `backend/app/ml`, imported by both the notebooks and the
  API. Each exported bundle ships a *golden* input/expected-output pair that the backend re-scores (`cli models verify
  --golden`).
* **Chain of trust for artifacts (SEC-06).** `model_versions.artifact_sha256` pins the SHA-256 of `manifest.json`;
  the manifest pins the SHA-256 of every component file; runtime library versions are checked fail-closed; loaded
  objects are checked against a class allowlist and interface contract.
* **Asynchronous jobs (NFR-02).** `POST /analyses` returns `202` with a job id; a bounded worker pool processes the
  dataset in chunks; the UI polls job status.

## 3. Final folder structure

```
CyberSentinel/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py                 # auth, RBAC, pagination dependencies
│   │   │   └── v1/{router.py, endpoints/*.py}
│   │   ├── core/                       # config, logging, security, errors, middleware, rate limit
│   │   ├── db/                         # declarative base, portable types, session
│   │   ├── models/                     # SQLAlchemy ORM (7 tables)
│   │   ├── schemas/                    # Pydantic request/response models
│   │   ├── repositories/               # parameterized data access
│   │   ├── services/                   # business logic (auth, datasets, jobs, risk, alerts, audit…)
│   │   ├── ml/                         # runtime-safe ML library shared with notebooks
│   │   ├── utils/                      # csv safety, IP pseudonymization, text helpers
│   │   ├── cli.py                      # create-admin, model registry sync/approve/verify, dataset import/purge
│   │   └── main.py                     # app factory
│   ├── config/risk_policy.json         # versioned risk policy
│   ├── migrations/                     # Alembic (PostgreSQL)
│   ├── scripts/export_openapi.py
│   ├── tests/
│   ├── requirements-ml.txt             # shared ML pins (backend + notebooks)
│   ├── requirements.txt / requirements-dev.txt / constraints.txt
│   └── .env.example
├── frontend/
│   ├── src/{components,features,hooks,layouts,pages,services,styles,types,utils}
│   ├── public/
│   └── package.json
├── notebooks/
│   ├── 01_data_exploration.ipynb … 06_model_evaluation.ipynb
│   ├── nb_utils/                       # training-only helpers (never imported by the API)
│   ├── tests/                          # helper tests + synthetic raw-format fixtures for smoke runs
│   └── requirements.txt
├── model_artifacts/
│   ├── README.md
│   ├── registry.json                   # MODEL_MANIFEST: index of exported bundles
│   ├── bundles/<model_name>/<version>/ # manifest.json + *.joblib (git-ignored)
│   └── experiments/                    # notebook-exported experiment results (JSON)
├── data/        (git-ignored raw/processed datasets)
├── reports/     (git-ignored notebook outputs)
├── docs/
├── .gitignore
└── README.md
```

Deviation from the master prompt's sketch, with justification: `backend/app/db/` (engine/session/base types) is split
from `backend/app/models/` (ORM classes) to avoid import cycles with Alembic; `notebooks/nb_utils/` holds training code
so that the backend package provably contains none.

## 4. Module responsibilities

| Module | Responsibility | Must not |
|---|---|---|
| `api/v1/endpoints/*` | HTTP contract, request parsing, dependency-injected auth/RBAC, response mapping | Contain ML or SQL logic |
| `api/deps.py` | Current user resolution, role guards, pagination/sort parsing | — |
| `core/config.py` | Typed settings from environment; fail fast on missing/weak secrets | Hold secret defaults |
| `core/security.py` | Argon2id hashing, JWT access/refresh tokens with `token_version` revocation | Log credentials |
| `core/errors.py` | Error hierarchy + consistent error envelope, no stack traces | Leak internals |
| `core/middleware.py` | Request-ID correlation, security headers, body-size limits, access logging | Log payloads |
| `core/rate_limit.py` | Sliding-window limiter for login, uploads, analysis, exports | — |
| `repositories/*` | Parameterized ORM queries, filtering allowlists, pagination | Build SQL from strings |
| `services/validation_service.py` | CSV/JSON validation: type, size, encoding, headers, schema, rows, numeric bounds, categories | Execute content |
| `services/dataset_service.py` + `storage_service.py` | Opaque-key storage, checksum, dataset lifecycle, deletion rules | Use user filenames as paths |
| `services/model_registry_service.py` | Register bundles from the registry index, status transitions, cached secure loading | Download or train |
| `services/preprocessing_adapter.py` | Map validated input to the bundle's feature contract | Guess column order |
| `services/prediction_service.py` | Synchronous quick analysis (record/batch) | Persist unaudited results |
| `services/analysis_service.py` + `job_runner.py` | Job creation, claiming, chunked inference, cancellation, recovery | Block HTTP requests |
| `services/risk_scoring_service.py` | Load/validate versioned policy; apply `app.ml.risk` | Present scores as probabilities |
| `services/explanation_service.py` | Attach supported explanations (alerts / needs-review rows) | Claim causality |
| `services/alert_service.py` / `review_service.py` | Alert queries (derived), append-only reviews | Mutate model output |
| `services/report_service.py` | CSV/JSON exports with formula-injection escaping and row caps | Export unauthorized rows |
| `services/audit_service.py` | Controlled-vocabulary audit events, redacted details | Store secrets/payloads |
| `services/metrics_service.py` | Dashboard aggregates, trends, model metrics | — |
| `services/experiment_service.py` | Read-only experiment results exported by notebooks | Run experiments |
| `ml/datasets` | Dataset-family schemas (CIC-IDS2017, UNSW-NB15), header normalization, label maps | Merge incompatible schemas |
| `ml/preprocessing` | Deterministic cleaning, label normalization, feature-frame construction, pickle-safe transforms | Fit anything |
| `ml/artifacts` | Manifest schema, integrity, compatibility, secure loader, bundle exporter | Load untrusted files |
| `ml/inference` | Chunked scoring with a loaded bundle → typed records | Fit/tune |
| `ml/risk` | Pure, testable risk functions | — |
| `ml/explain` | XGBoost TreeSHAP (native), tree-path attribution, baseline-deviation reason codes | — |
| `ml/evaluation` | Metrics (per-class P/R/F1, FPR, ROC/PR-AUC where valid, thresholds, anomaly metrics) | Invent numbers |
| `notebooks/nb_utils` | Raw file discovery, splits, label masking, model builders, plotting, experiment logging | Be imported by `app` |

## 5. Database and API contract alignment

### 5.1 Tables (ERD v1.0 + documented extensions)

| Table | ERD columns implemented | Extensions (justification) |
|---|---|---|
| `users` | all | `failed_login_attempts`, `locked_until`, `last_login_at` (brute-force lockout, FR-01); `token_version` (token revocation on logout/password/role change) |
| `datasets` | all | `size_bytes`, `has_ground_truth`, `validation_report` JSONB (bounded validation summary), `updated_at`, `deleted_at`, `deleted_by` (ERD §7: soft deletion requires actor and time) |
| `model_versions` | all | `description`, `task`, `dataset_family`, `explanation_method`, `probability_calibrated`, `approved_by`, `approved_at`, `status_reason`, `updated_at` |
| `analysis_jobs` | all | `risk_policy_version` (ERD §10 "dedicated column"), `error_message` (safe text), `updated_at` (heartbeat) |
| `predictions` | all | `classifier_score` (ERD §10 "store a raw score separately"), `is_anomaly`, `is_alert`, `true_label` (evaluation only, never an input), `flow_context` JSONB (pseudonymized identifiers) |
| `alert_reviews` | all | — (append-only enforced by PostgreSQL trigger) |
| `audit_logs` | all | `outcome` (SAD §11: actor, action, outcome) — append-only enforced by trigger |

Traceability chain: `datasets → analysis_jobs (+model_version_id, risk_policy_version) → predictions → alert_reviews`.

### 5.2 Endpoint map (`/api/v1`)

| Source requirement | Endpoint(s) |
|---|---|
| FR-20, PRD health | `GET /health`, `GET /health/live` |
| FR-01 | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/change-password` |
| FR-02, FR-17 | `GET/POST /admin/users`, `GET/PATCH /admin/users/{id}`, `POST /admin/users/{id}/reset-password` |
| FR-03/04/05/19 | `POST /datasets` (multipart), `GET /datasets`, `GET /datasets/{id}`, `DELETE /datasets/{id}`, `GET /dataset-schemas` |
| FR-06, PRD models | `GET /models`, `GET /models/{id}`, `PATCH /models/{id}/status` (admin), `POST /models/{id}/verify` (admin) |
| FR-07/08/09 | `POST /analyses` (202), `GET /analyses`, `GET /analyses/{id}`, `POST /analyses/{id}/cancel` |
| FR-10/11/13/14 | `GET /analyses/{id}/predictions`, `GET /predictions/{id}`, `GET /analyses/{id}/export` |
| FR-15 | `POST /predictions/{id}/reviews`, `GET /predictions/{id}/reviews` |
| FR-16, PRD alerts | `GET /alerts`, `GET /alerts/{id}`, `GET /alerts/export` |
| PRD analyze/record, analyze/batch | `POST /analyze/record`, `POST /analyze/batch` (synchronous, bounded, not persisted, audited) |
| FR-12, PRD metrics | `GET /metrics/summary`, `GET /metrics/trends`, `GET /metrics/models` |
| PRD experiments | `GET /experiments`, `GET /experiments/{id}` |
| PRD reports, US4 | `GET /reports/summary?format=json|csv` |
| FR-18 | `GET /audit-logs` |
| ML-07 | `GET /risk-policy`; `GET /system/info` (limits for the UI) |

Pagination: `limit` (≤100) / `offset`, response `{items, total, limit, offset}`. Sorting: allowlisted `sort` values.
Errors: `{"error": {"code", "message", "details", "request_id"}}` with the status mapping of Workflow Manual §7.3.

### 5.3 Role matrix (server-enforced)

| Capability | admin | analyst | viewer |
|---|---|---|---|
| Own profile, change password | ✔ | ✔ | ✔ |
| Aggregate dashboard metrics, model metadata (approved), experiments, risk policy, summary report export | ✔ | ✔ | ✔ |
| Upload / list / view / delete datasets | all | own + shared system datasets | ✘ |
| Create / view / cancel analysis jobs, view predictions & alerts | all | own | ✘ |
| Record alert reviews, quick analysis, record-level exports | ✔ | own scope | ✘ |
| Users, audit logs, model status changes, artifact verification | ✔ | ✘ | ✘ |

## 6. ML artifact interface

```
model_artifacts/                     ← MODEL_DIR (trusted, read-only to the API process)
├── registry.json                    ← MODEL_MANIFEST: {"registry_version":"1.0","bundles":[{model_name, version, path, manifest_sha256}]}
├── bundles/<model_name>/<version>/
│   ├── manifest.json                ← schema "1.0" (validated by app.ml.artifacts.manifest.BundleManifest)
│   ├── preprocessor.joblib          ← fitted ColumnTransformer (sklearn built-ins + allowlisted app.ml transforms)
│   ├── classifier.joblib            ← optional; predict_proba; classes_ == [0..K-1]
│   ├── anomaly_detector.joblib      ← optional; IsolationForest
│   ├── golden_input.csv / golden_expected.json   ← parity check
│   └── model_card.md
└── experiments/*.json               ← notebook-exported experiment results (read-only API)
```

Manifest essentials: `manifest_version`, `bundle{model_name, version, model_type, created_at}`,
`dataset{family, schema_version, split_strategy, random_seed, row counts}`,
`features{feature_schema_version, input_features[ordered], transformed_feature_names, transformed_feature_sources,
benign_reference}`, `preprocessing{preprocessing_version, artifact{file, sha256, size_bytes}}`,
`components.classifier{artifact, estimator_class, task, classes, benign_class, probability_calibrated,
decision_threshold, min_confidence, explanation_method, global_feature_importance}`,
`components.anomaly_detector{artifact, estimator_class, score_definition, score_direction="higher_is_more_anomalous",
threshold, threshold_method, reference_points{benign_median, threshold, upper}}`, measured `metrics`, and `runtime`
library versions.

Loader contract (fail closed at every step): path confinement to `MODEL_DIR` → manifest SHA-256 equals the DB pin →
manifest schema/version → name/version/schema/preprocessing match the DB row → runtime compatibility
(scikit-learn & xgboost major.minor, numpy major) → per-file size and SHA-256 → `joblib.load` → class allowlist and
interface checks (feature names/order, `classes_`, `n_features_in_`) → cache by `(model_version_id, manifest_sha256)`.
Missing → `503 model_unavailable`; tampered/incompatible → `503` plus an audit event. Status `revoked` is never loaded.

Anomaly score definition: `anomaly_score = −IsolationForest.score_samples(x)` ∈ (0, 1]; **higher = more anomalous**;
`is_anomaly = anomaly_score ≥ threshold` where the threshold is selected on **validation** benign scores in notebook 04.

## 7. Ambiguities and conflicts found (explicitly resolved)

| ID | Conflict / ambiguity | Sources | Resolution |
|---|---|---|---|
| C-01 | Provided repository `khizer45/skyntri` contains an unrelated skin-health project | repo vs prompt | Per your instruction: new repository `Khizer45/cybersentinel`; Skyntri untouched |
| C-02 | API Specification document not supplied | master prompt §18 | Contract derived from PRD §3.3.2, Workflow §10, RTM; the generated OpenAPI (`docs/api/openapi.json`) is authoritative |
| C-03 | Endpoint naming: `/analyze/file`, `/jobs/{id}/results`, `PATCH /alerts/{id}` vs `/datasets`, `/analyses/{id}/predictions`, `POST /predictions/{id}/reviews` | PRD, Workflow vs RTM | RTM resource model (keeps Dataset→Job→Prediction→Review traceability); `/analyze/record|batch` kept as bounded synchronous endpoints; alert updates are append-only reviews |
| C-04 | Auth optional for demos vs mandatory | Security Req §5.2, PRD §3.4 vs master prompt, RTM FR-01/02 | Always enforced (JWT + RBAC) |
| C-05 | Invalid request → 400 vs FastAPI default 422 | Security Req §5.2, Workflow §7.3 | Workflow §7.3: schema/shape errors → 400; semantically invalid features → 422 |
| C-06 | Notebook set and names | Workflow §4.1 (5), Tech Req §4.3, master prompt (6) | Master prompt's six notebooks |
| C-07 | `ml/` top-level & `api/routes`, `db/models.py` | Workflow §6, Tech Req §4.6 vs master prompt/SAD App. A | Master prompt/SAD layout; shared ML code in `backend/app/ml` for parity; training helpers in `notebooks/nb_utils` |
| C-08 | Extra tables `alerts`, `experiments`, `audit_events`; storing raw features | Workflow §9.1, Tech Req §4.1 vs ERD | ERD's 7 tables; alerts derived (`is_alert` + reviews); experiments file-based; raw feature rows not stored (only top-feature values inside explanations) |
| C-09 | Disposition vocabulary | ERD (4) vs Workflow §12.1 (5) | `true_positive, false_positive, benign, duplicate, needs_investigation` ("unresolved" ≡ `needs_investigation`) |
| C-10 | Model Lab "runs" experiments in the product | PRD §3.3.1, Demo 2; SRS UC4 | Display-only of notebook-exported results (SEC-07) |
| C-11 | Algorithm lists | SRS/Tech Req vs master prompt | Notebooks evaluate LR, RF, XGBoost, Linear SVM (calibrated, subsampled), IF, K-Means, DBSCAN (exploratory), LP/LS; deployable: allowlisted classifiers with `predict_proba` + IsolationForest; DBSCAN not deployable (no out-of-sample predict) |
| C-12 | OpenAI/ChatGPT plugin deliverable | SRS, Proposal, PRD vs master prompt | Out of scope (absent from master prompt; ChatGPT plugins were retired by OpenAI in 2024). OpenAPI schema enables a later GPT-Actions/MCP adapter; prompt-injection guidance kept in the Security Guide |
| C-13 | Tailwind CSS vs "Modern CSS" | Tech Req §4.5 vs master prompt | Modern CSS with custom properties; no Tailwind |
| C-14 | Docker optional vs prohibited | SRS §1.5, Tech Req vs master prompt | No Docker anywhere |
| C-15 | Old version pins / Python 3.10+ | Tech Req §4.5, Workflow §5.2 | Current releases ≥3 weeks old (supply-chain hygiene); **Python ≥ 3.12** required by numpy 2.5 / xgboost 3.4 / scipy 1.18; verified on 3.13 |
| C-16 | UNSW-NB15 variant (1.94M/2.5M raw rows, 49 cols, no header) | SRS §1.6, Tech Req §4.5 | Canonical schema = official training/testing partition (42 features + `attack_cat` + `label`, official test split); raw 4-file release not accepted for inference (no `rate`, different names) |
| C-17 | CIC-IDS2017 ships a duplicated `Fwd Header Length` header vs "reject duplicate headers" | dataset vs RTM FR-04 | Adapter declares this single known duplicate; verifies equality, drops the copy; any other duplicate is rejected |
| C-18 | Risk formula undefined / suggested weighted sum | SAD §13, Tech Req §4.1, SRS §1.4 | Versioned policy 1.0.0 (see `docs/risk_scoring_policy.md`); defaults are placeholders to tune on validation (notebook 06) |
| C-19 | `probability` semantics | ERD §10, SAD §5.3 | `probability` only when calibration was evaluated; raw `classifier_score` stored separately |
| C-20 | Experiment tracking via MLflow/SQLite | Tech Req §4.4 vs ERD §1 | JSON/CSV files written by notebooks; no MLflow dependency |
| C-21 | Processed data as CSV | Tech Req §4.2 | Parquet (dtype fidelity, size); CSV optional |
| C-22 | Background job mechanism | SAD §13 | In-process bounded pool, DB-backed status, atomic claim, heartbeat and stale-job recovery; one API process recommended |
| C-23 | Upload retention | ERD §13, SAD §13 | Stored under opaque keys until dataset deletion; rejected uploads deleted immediately; CLI purge by age |
| C-24 | Tenant isolation | ERD §13 | Single organization; record-level ownership isolation; aggregates organization-wide |
| C-25 | Viewer capabilities unspecified | ERD role list | Read-only aggregates, models, experiments, summary reports |
| C-26 | Hide raw IPs vs filter by IP | Security Req §5.1, Workflow §9.2 vs PRD §3.4 | HMAC pseudonymization; IP filter pseudonymizes the query; raw IPs never stored |
| C-27 | Real-time monitoring (UC3) | SRS | Out of scope (Workflow §1.2: batch is primary); polling + quick analysis |
| C-28 | `alerts.acknowledged_by/at` | Workflow §9.1 | Represented by `alert_reviews.reviewed_by/created_at` |
| C-29 | Severity labels | SRS vs ERD | ERD values `low, medium, high, critical` |
| C-30 | Nearest-neighbour graph explanations for anomalies | SRS UC6 | Not served (requires training data at runtime); baseline-deviation reason codes instead |
| C-31 | Low-confidence output | Workflow §3.3, §10.1 | `predicted_label = "needs_review"`; top classes kept in `explanation` |
| C-32 | Acceptance targets (F1 > 90 %, > 80 % anomalies, LP > baseline) | SRS §1.9 | Treated as hypotheses; notebooks measure; nothing claimed |
| C-33 | Demo F1 numbers (0.70 vs 0.60) | PRD Demo 2 | Illustrative only; not used |

## 8. Technical risks

| Risk | Mitigation |
|---|---|
| Joblib/pickle deserialization executes code | Trusted directory only, no model upload endpoint, manifest-hash pinned in DB, per-file hashes, class allowlist (defense in depth — not a sandbox) |
| Train/serve skew | Shared preprocessing code, persisted fitted preprocessor, golden parity check |
| Label Propagation is O(n²) | Stratified pool subsample, `knn` kernel, documented limits |
| Shortcut/leaky features (CIC `destination_port`, UNSW `sttl`/`ct_state_ttl`) and known label noise | Ablation switches and dataset cards |
| Library drift between notebook and API environments | One shared `requirements-ml.txt`; manifest runtime check fails closed |
| Several API processes with in-process workers | Atomic claim + heartbeat; documented single-process recommendation |
| Rare classes (e.g. Heartbleed, Infiltration, SQL injection in CIC-IDS2017) | Macro metrics, class weights, explicit rare-class policy in the notebooks |
| SQLite (tests) vs PostgreSQL (production) | Dialect-portable types; suite also runnable against PostgreSQL via `TEST_DATABASE_URL` |

## 9. Phased file-generation plan

| Phase | Deliverables |
|---|---|
| 2 — Database | `app/db/*`, `app/models/*`, Alembic env + `0001_initial_schema` (constraints, indexes, append-only triggers), database guide |
| 3 — ML | `app/ml/*` runtime library, `notebooks/nb_utils/*`, six notebooks, `model_artifacts/` contract, training & artifact guides |
| 4 — Backend | `core/*`, `schemas/*`, `repositories/*`, `services/*`, `api/v1/*`, `cli.py`, `main.py`, risk policy, OpenAPI export |
| 5 — Frontend | Vite/React/TS app, typed API client generated from OpenAPI, auth, 13 pages, charts, tables |
| 6 — Tests & docs | Backend/ML/notebook/frontend tests (executed, results recorded), remaining guides, RTM status |
| 7 — Handover | File tree, setup/run/test commands, manual tasks, known limitations |
