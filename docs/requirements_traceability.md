# Requirements Traceability — Implementation Status

Maps every requirement of the supplied **Requirements Traceability Matrix (RTM) v1.0** to the code that implements it
and the evidence that checks it. Paths are relative to the repository root; backend paths are under `backend/app/`
unless they start with another top-level folder.

**Status values**

* **Implemented · tests passed** — implementation present and the mapped automated tests passed in the verification
  run recorded in the [Testing Guide](testing_guide.md#5-verification-record) (2026-11-03).
* **Implemented · reviewed** — implementation present; the evidence is a code/architecture check or document rather
  than a functional test.
* **Partially verified** — implemented, but part of the RTM's required evidence is still open (stated in the row).

Per RTM §7 a requirement becomes *Verified* when (1) the implementation is in an identified commit, (2) the mapped
test or review has passed, (3) the evidence is stored at a known location and (4) open defects are recorded. Rows marked
*tests passed* meet (1)–(3) for commit `580f315` (evidence: the verification record in the Testing Guide) and open
items are listed below; marking them *Verified* is the project owner's sign-off, so no row claims it here. Re-run the
checks on the commit you release and update the evidence register (§5).

## 1. Functional requirements

| ID | Requirement (RTM) | Implementation | Evidence | Status |
| --- | --- | --- | --- | --- |
| FR-01 | Authenticate with valid credentials; reject invalid attempts safely | `api/v1/endpoints/auth.py`, `services/auth_service.py`, `core/security.py`; `frontend/src/features/auth`, `pages/LoginPage.tsx` | `tests/api/test_auth_api.py`, `tests/core/test_security.py`; `LoginPage.test.tsx`, `AuthContext.test.tsx` | Implemented · tests passed |
| FR-02 | Enforce admin/analyst/viewer permissions server-side | `api/deps.py` (`require_roles`, typed role dependencies), repository visibility filters; UI guards `RequireRole` | `tests/api/test_rbac.py` (every route × role); `App.test.tsx` | Implemented · tests passed |
| FR-03 | Authorized analyst can upload a supported CSV | `api/v1/endpoints/datasets.py`, `services/dataset_service.py`, `services/storage_service.py`; `pages/DatasetUploadPage.tsx` | `tests/api/test_datasets_api.py`; `DatasetUploadPage.test.tsx`; browser smoke test | Implemented · tests passed |
| FR-04 | Validate format, size, row limits and feature schema before inference | `services/validation_service.py`, `ml/preprocessing/reader.py`, `ml/datasets/*`, `core/middleware.py` (streamed size limit) | `tests/api/test_datasets_api.py` (abuse cases, rejections), `tests/ml/test_cleaning_and_reader.py`, `tests/ml/test_schemas_and_labels.py` | Implemented · tests passed |
| FR-05 | View only datasets the user may access | `repositories/datasets.py` (`get_visible`, owner scoping); `pages/DatasetsPage.tsx` | `test_ownership_isolation_and_pagination` in `tests/api/test_datasets_api.py` | Implemented · tests passed |
| FR-06 | Inspect approved model metadata without artifact paths | `api/v1/endpoints/models.py`, `schemas/model_version.py` (no path field), `services/model_registry_service.py`; `pages/ModelsPage.tsx` | `tests/api/test_models_api.py` | Implemented · tests passed |
| FR-07 | Create an analysis job from a validated dataset and approved model | `services/analysis_service.py`, `api/v1/endpoints/analyses.py` (202 + `Location`); `features/analysis/NewAnalysisDialog.tsx` | `tests/api/test_analysis_flow.py`; `NewAnalysisDialog.test.tsx` | Implemented · tests passed |
| FR-08 | Inference uses the exact approved preprocessing and model artifact | `ml/artifacts/loader.py`, `ml/artifacts/golden.py`, `ml/inference/engine.py`, shared `ml/preprocessing/*` | `tests/ml/test_artifacts.py` (tampering, revocation, incompatibility, golden parity); notebook smoke tests | Implemented · tests passed |
| FR-09 | Job exposes queued/running/completed/failed/cancelled status | `services/job_runner.py` (atomic transitions, cancellation, stale recovery), `models/analysis_job.py`; `pages/AnalysisJobsPage.tsx` (polling) | `tests/services/test_job_runner.py`, `tests/api/test_analysis_flow.py` | Implemented · tests passed |
| FR-10 | Predictions linked to job, source record index and model version | `models/prediction.py` (unique `(analysis_job_id, record_index)`), `repositories/predictions.py` | `tests/api/test_analysis_flow.py` (traceability query), `tests/migrations/` | Implemented · tests passed |
| FR-11 | Paginated, filterable prediction results | `GET /analyses/{id}/predictions` (allow-listed filters and sorts); `pages/AnalysisResultsPage.tsx` | `tests/api/test_analysis_flow.py`; browser smoke test (filters, export) | Implemented · tests passed |
| FR-12 | Dashboard summarizes predicted classes and risk bands | `services/metrics_service.py`, `repositories/metrics.py`; `pages/DashboardPage.tsx` | `tests/api/test_analysis_flow.py`, `tests/api/test_reports_experiments_system.py`; `App.test.tsx` | Implemented · tests passed |
| FR-13 | Distinguish classifier probability, anomaly score and policy risk score | `ml/inference/engine.py`, `models/prediction.py` (`probability` only when calibrated, `classifier_score`, `anomaly_score`, `risk_score`); `components/ScoreSemantics.tsx` | `tests/ml/test_inference_and_explanations.py`; `AlertDetailsPage.test.tsx` | Implemented · tests passed |
| FR-14 | Explanation metadata without claiming causality | `ml/explain/*`, `services/explanation_service.py`; `features/alerts/ExplanationView.tsx` (disclaimer shown) | `tests/ml/test_inference_and_explanations.py`; `AlertDetailsPage.test.tsx` | Implemented · tests passed |
| FR-15 | Record a disposition and notes for a prediction | `services/review_service.py`, `models/alert_review.py` (append-only trigger); `features/alerts/ReviewPanel.tsx` | `tests/api/test_analysis_flow.py`, `tests/migrations/`; `AlertDetailsPage.test.tsx`; browser smoke test | Implemented · tests passed |
| FR-16 | Search and filter alert findings | `services/alert_service.py`, `api/v1/endpoints/alerts.py`; `pages/AlertsPage.tsx` | `tests/api/test_analysis_flow.py`, `tests/api/test_rbac.py`; browser smoke test | Implemented · tests passed |
| FR-17 | Admin manages user accounts and roles | `services/user_service.py` (last-admin protection, token revocation), `api/v1/endpoints/admin_users.py`; `pages/UsersPage.tsx` | `tests/api/test_users_and_audit.py`, `tests/api/test_rbac.py`; browser smoke test | Implemented · tests passed |
| FR-18 | Admin reviews audit events | `services/audit_service.py`, `api/v1/endpoints/audit_logs.py`; `pages/AuditLogsPage.tsx` | `tests/api/test_users_and_audit.py`; browser smoke test | Implemented · tests passed |
| FR-19 | Dataset deletion subject to retention and reference rules | `services/dataset_service.py` (soft delete, `dataset_in_use`, purge CLI) | `test_soft_delete_removes_file_and_keeps_metadata` and related tests | Implemented · tests passed |
| FR-20 | Health/readiness without disclosing internals | `services/health_service.py`, `api/v1/endpoints/health.py` | `tests/api/test_errors_and_security.py`, `tests/api/test_reports_experiments_system.py` | Implemented · tests passed |

## 2. Non-functional requirements

| ID | Requirement (RTM) | Implementation | Evidence | Status |
| --- | --- | --- | --- | --- |
| NFR-01 | Clear, consistent errors without stack traces or internals | `core/errors.py` (envelope, generic 500), `frontend/src/utils/errors.ts` | `tests/api/test_errors_and_security.py`; `utils/errors.test.ts` | Implemented · tests passed |
| NFR-02 | Bounded batch processing and asynchronous job status | `services/job_runner.py` (worker pool, queue cap, chunking, heartbeat) | `tests/services/test_job_runner.py`; 12,000-row background job on PostgreSQL (2026-11-02) | Partially verified — representative benchmark on production-sized data not run |
| NFR-03 | Dashboard queries use pagination and documented indexes | `limit ≤ 100` pagination on every list; indexes in the migration and `docs/database_documentation.md` §4.3 | pagination tests in `tests/api/test_datasets_api.py` and `tests/api/test_analysis_flow.py` | Partially verified — EXPLAIN-plan review on large tables not performed |
| NFR-04 | Prediction traceable to model, preprocessing, feature schema and risk policy versions | `analysis_jobs.risk_policy_version`, `model_versions` (preprocessing and schema versions, manifest hash), job summary | `tests/api/test_analysis_flow.py` (traceability query) | Implemented · tests passed |
| NFR-05 | Request/job correlation IDs and operational events in logs | `core/logging.py`, `core/middleware.py`, `core/context.py` | `tests/api/test_errors_and_security.py` (request IDs); log inspection during the E2E run | Implemented · tests passed |
| NFR-06 | Local development runs frontend, backend and PostgreSQL separately without Docker | `docs/installation_guide.md`, `frontend/README.md`; no Docker files | Clean-sandbox run of PostgreSQL, Uvicorn and Vite as separate processes (browser smoke test) | Implemented · reviewed |

## 3. Security requirements

| ID | Requirement (RTM) | Implementation | Evidence | Status |
| --- | --- | --- | --- | --- |
| SEC-01 | Passwords stored only as modern one-way hashes | Argon2id in `core/security.py` | `tests/core/test_security.py`, `tests/api/test_auth_api.py` | Implemented · tests passed |
| SEC-02 | Authentication, role and resource-ownership enforcement | `api/deps.py`, repository visibility filters, audited denials | `tests/api/test_rbac.py`, ownership tests in the dataset and analysis suites | Implemented · tests passed |
| SEC-03 | Parameterized queries / safe ORM methods | `repositories/*` (SQLAlchemy expressions, allow-listed sorts) | `tests/api/test_datasets_api.py` (SQL-injection-style search); code review | Implemented · tests passed |
| SEC-04 | Uploaded files constrained, validated and safely handled | Size/row/content-type limits, strict CSV structure, opaque storage keys, rejected files deleted | `tests/api/test_datasets_api.py` (upload abuse cases), `tests/ml/test_cleaning_and_reader.py` | Implemented · tests passed |
| SEC-05 | Secrets not committed or exposed to frontend clients | `core/config.py` (no defaults, `SecretStr`, placeholder rejection), `.gitignore`, only `VITE_*` variables in the bundle | `tests/core/test_config.py`; repository review (no `.env` files tracked) | Implemented · tests passed |
| SEC-06 | Artifacts trusted, checksum-verified, loaded only when approved | `ml/artifacts/*`, `services/model_registry_service.py` | `tests/ml/test_artifacts.py`, `tests/api/test_models_api.py` | Implemented · tests passed |
| SEC-07 | Running API cannot train, tune or download models | Training code only in `notebooks/nb_utils`; no network clients in `backend/app` | `tests/architecture/test_runtime_boundaries.py` | Implemented · tests passed |
| SEC-08 | Rate limits, timeouts, bounded concurrency | `core/rate_limit.py`, `core/middleware.py`, `db/session.py` (statement timeout), job runner limits | `tests/api/test_errors_and_security.py`, `tests/api/test_auth_api.py` (rate limits), `tests/services/test_job_runner.py` | Implemented · tests passed |
| SEC-09 | Audit records for privileged/security actions, without secrets | `services/audit_service.py`, append-only trigger, log redaction | `tests/api/test_users_and_audit.py`, `tests/migrations/` | Implemented · tests passed |
| SEC-10 | CORS, HTTPS, secure session/token handling, CSRF controls | CORS allowlist, HttpOnly SameSite=Strict refresh cookie, Origin check, HSTS option, production start-up rules | `tests/api/test_auth_api.py`, `tests/api/test_errors_and_security.py`, `tests/core/test_config.py` | Implemented · tests passed (HTTPS deployment is yours — see the Security Guide) |
| SEC-11 | Sensitive data access-controlled and retained per policy | Owner scoping, viewer aggregates only, soft deletion, purge CLI, IP pseudonymisation | `tests/api/test_datasets_api.py`, `tests/api/test_rbac.py`, `tests/core/test_utils.py` | Implemented · tests passed |
| SEC-12 | Dependencies and build artifacts reviewed for vulnerabilities and integrity | Pinned versions (`constraints.txt`, `package-lock.json` with integrity hashes), model artifact hashes | `pip-audit`: no known vulnerabilities; `npm audit --omit=dev`: 0; dev-tool advisory documented | Implemented · reviewed |

## 4. ML requirements

| ID | Requirement (RTM) | Implementation | Evidence | Status |
| --- | --- | --- | --- | --- |
| ML-01 | Train/test separation prevents leakage; split strategy documented | `notebooks/nb_utils/splits.py` (deduplication before splitting, leakage checks), notebook 02, `docs/model_training_guide.md` | Notebook smoke tests; split code review | Partially verified — leakage checklist must be reviewed on the real datasets |
| ML-02 | Inference preprocessing matches the approved training pipeline | Shared `backend/app/ml/preprocessing`, persisted fitted preprocessor, golden fixtures | `tests/ml/test_artifacts.py`, notebook smoke tests (golden parity) | Implemented · tests passed |
| ML-03 | Class-wise precision/recall/F1, confusion matrix; ROC-AUC only where valid | `ml/evaluation/metrics.py` (undefined metrics are `None`, never invented), notebooks 03 and 06 | `tests/ml/test_metrics.py` | Partially verified — evaluation report on the real test sets not yet produced |
| ML-04 | False-positive rate and class imbalance explicitly evaluated | False-alarm rate, per-class results, class weights and threshold analysis in notebooks 03/06 | `tests/ml/test_metrics.py` | Partially verified — requires running the notebooks on real data |
| ML-05 | Anomaly score direction, scale and threshold semantics documented | Manifest `score_direction`/`score_definition`/threshold, model card, `docs/risk_scoring_policy.md` | `tests/ml/test_inference_and_explanations.py` | Implemented · tests passed |
| ML-06 | Semi-supervised label use controlled; no leakage of held-out labels | `notebooks/nb_utils/semi_supervised.py` (per-class label budget masks), notebook 05 | Notebook smoke tests | Partially verified — experiment on real data not run |
| ML-07 | Risk bands are versioned policy outputs, not probabilities | `ml/risk/*`, `config/risk_policy.json`, `docs/risk_scoring_policy.md`; UI labelling | `tests/ml/test_risk_scoring.py` | Implemented · tests passed |
| ML-08 | Model limitations and dataset representativeness documented | `docs/dataset_cards/*.md`, generated `model_card.md` and `limitations` in every bundle manifest | Document review | Partially verified — model cards are produced when you export real bundles |

## 5. Evidence register (RTM §5)

| Evidence | Linked requirements | Where | Result (2026-11-03, code at commit `580f315`) |
| --- | --- | --- | --- |
| EV-001 Authentication and RBAC | FR-01, FR-02, FR-17, SEC-01, SEC-02 | `backend/tests/api/test_auth_api.py`, `test_rbac.py`, `test_users_and_audit.py`; frontend auth tests | Passed |
| EV-002 Dataset upload and validation | FR-03, FR-04, FR-05, SEC-04 | `backend/tests/api/test_datasets_api.py`, `tests/ml/test_cleaning_and_reader.py`; `DatasetUploadPage.test.tsx` | Passed |
| EV-003 Inference parity and artifact integrity | FR-06–FR-10, FR-13, NFR-04, SEC-06, SEC-07 | `backend/tests/ml/test_artifacts.py`, `test_inference_and_explanations.py`, `tests/api/test_analysis_flow.py`, `tests/architecture/` | Passed |
| EV-004 Dashboard, filters and pagination | FR-11, FR-12, FR-16, NFR-03 | API flow tests, `App.test.tsx`, browser smoke test | Passed (EXPLAIN review open) |
| EV-005 Analyst review and audit | FR-15, FR-18, SEC-09 | `tests/api/test_analysis_flow.py`, `test_users_and_audit.py`, `tests/migrations/` | Passed |
| EV-006 Security tests and configuration review | SEC-01–SEC-12, NFR-01 | `tests/api/test_errors_and_security.py`, `tests/core/`, `docs/security_guide.md`, dependency audits | Passed (deployment review is yours) |
| EV-007 ML evaluation and model documentation | ML-01–ML-08 | `tests/ml/`, notebook smoke tests, dataset cards | Mechanics passed; real-data evaluation not run |
| EV-008 Local setup and operational readiness | FR-20, NFR-02, NFR-05, NFR-06 | `docs/installation_guide.md`, sandbox E2E runs | Passed in sandbox; clean-machine checklist on your hardware open |
