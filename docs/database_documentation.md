# Database Documentation

CyberSentinel persists operational data in **PostgreSQL ≥ 13** (developed and verified against PostgreSQL 16).
The schema implements the *Database Design, ERD & Data Dictionary v1.0* with the extensions listed in §4.
This repository **does not provision or connect to your database** — you create it and apply the migrations.

## 1. Provisioning (you run these)

Create a dedicated owner role for migrations and a least-privilege runtime role for the API. The database
**must use UTF-8 encoding** (psycopg 3 returns raw bytes for `SQL_ASCII` databases).

```sql
-- as a PostgreSQL superuser (psql -U postgres)
CREATE ROLE cybersentinel_owner LOGIN PASSWORD '<strong-password-1>';
CREATE ROLE cybersentinel_app   LOGIN PASSWORD '<strong-password-2>';
CREATE DATABASE cybersentinel OWNER cybersentinel_owner ENCODING 'UTF8' TEMPLATE template0;
```

Apply the schema with the **owner** role (see §2), then grant the runtime role only what it needs:

```sql
\c cybersentinel
GRANT CONNECT ON DATABASE cybersentinel TO cybersentinel_app;
GRANT USAGE ON SCHEMA public TO cybersentinel_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON users, datasets, model_versions, analysis_jobs, predictions
    TO cybersentinel_app;
-- Append-only tables: no UPDATE/DELETE privilege (the triggers below are a second line of defence).
GRANT SELECT, INSERT ON audit_logs, alert_reviews TO cybersentinel_app;
GRANT SELECT ON alembic_version TO cybersentinel_app;
```

## 2. Applying migrations

```bash
cd backend
source .venv/bin/activate                      # Windows: .venv\Scripts\activate
# Owner credentials only for this step (do not keep them in the API's .env):
export DATABASE_URL="postgresql+psycopg://cybersentinel_owner:<pw>@localhost:5432/cybersentinel"
alembic upgrade head          # create / upgrade the schema
alembic current               # show the applied revision
alembic upgrade head --sql    # print the SQL without executing (review before production)
alembic downgrade base        # DESTRUCTIVE: drops all CyberSentinel tables
```

`migrations/env.py` reads `DATABASE_URL` from the environment or `backend/.env` and only accepts PostgreSQL URLs.
The API itself connects with the runtime role:

```
DATABASE_URL=postgresql+psycopg://cybersentinel_app:<pw>@localhost:5432/cybersentinel
```

Then create the first administrator (prompts for the password; nothing is echoed or logged):

```bash
python -m app.cli create-admin --email admin@example.org --display-name "Platform Admin"
```

## 3. Entity relationships

```
users 1──N datasets (owner_user_id)          users 1──N analysis_jobs (submitted_by)
datasets 1──N analysis_jobs                  model_versions 1──N analysis_jobs
analysis_jobs 1──N predictions               predictions 1──N alert_reviews
users 1──N alert_reviews (reviewed_by)       users 1──N audit_logs (actor_user_id, nullable for system events)
```

All foreign keys use `ON DELETE RESTRICT`. Users are **deactivated, never deleted**; datasets are **soft-deleted**
(`status='deleted'`, `deleted_at`, `deleted_by`, stored file removed) so every prediction remains traceable:

```
prediction → analysis_job (risk_policy_version) → dataset (sha256, schema_version)
                        └→ model_version (artifact_sha256, preprocessing_version, feature_schema_version)
```

## 4. Tables

| Table | Purpose | Extensions beyond the ERD (rationale) |
|---|---|---|
| `users` | Identities, role (`admin`/`analyst`/`viewer`), Argon2id hash | `failed_login_attempts`, `locked_until`, `last_login_at` (lockout); `token_version` (revokes JWTs on logout/password/role change) |
| `datasets` | Uploaded/imported flow CSV metadata | `size_bytes`, `has_ground_truth`, `validation_report`, `updated_at`, `deleted_at`, `deleted_by` |
| `model_versions` | Registry of integrity-pinned model bundles | `task`, `dataset_family`, `description`, `explanation_method`, `probability_calibrated`, `status_reason`, `approved_by/at`, `updated_at` |
| `analysis_jobs` | Batch analysis lifecycle | `risk_policy_version`, `error_message`, `updated_at` (worker heartbeat) |
| `predictions` | One row per analysed record | `classifier_score`, `is_anomaly`, `is_alert`, `true_label`, `flow_context` |
| `alert_reviews` | Append-only analyst dispositions | — |
| `audit_logs` | Append-only security events | `outcome` |

### 4.1 Field semantics (data dictionary highlights)

| Column | Semantics |
|---|---|
| `predictions.probability` | Calibrated P(malicious). **NULL unless** the bundle manifest declares evaluated calibration. |
| `predictions.classifier_score` | Raw classifier attack score in [0,1] (`1 − P(benign)` from `predict_proba`); *not* a calibrated probability. |
| `predictions.anomaly_score` | `−IsolationForest.score_samples(x)` ∈ (0,1]; **higher = more anomalous**. |
| `predictions.is_anomaly` | `anomaly_score ≥ threshold` from the manifest (threshold chosen on validation data). NULL when no anomaly model ran. |
| `predictions.risk_score` / `risk_band` | Policy score 0–100 and band; formula and version in `docs/risk_scoring_policy.md`; version stored on the job. |
| `predictions.is_alert` | Risk policy alert decision at inference time (default: band ≥ `high`). |
| `predictions.predicted_label` | Canonical class, `needs_review` (low confidence) or `unclassified` (anomaly-only mode). |
| `predictions.true_label` | Ground truth copied from the uploaded file when present — used **only** for evaluation summaries. |
| `predictions.explanation` | `{method, method_family, target_label, units, top_features[], reason_codes[], disclaimer}`; attribution, not causality. |
| `predictions.flow_context` | Allowlisted identifiers (ports, protocol, timestamp) and **HMAC-pseudonymized** IPs; raw IPs are never stored. |
| `model_versions.artifact_uri` | Bundle path *relative to `MODEL_DIR`*; never returned by the API. |
| `model_versions.artifact_sha256` | SHA-256 of the bundle's `manifest.json` (which pins each component file's hash). |
| `analysis_jobs.summary` | Bounded aggregates: label/band counts, anomaly/alert counts, data-quality counters, timing, and evaluation metrics when the file contained labels. |
| `audit_logs.details` | Allowlisted metadata only (no passwords, tokens, raw rows). |

### 4.2 Constraints

* CHECK constraints for every controlled vocabulary (roles, statuses, modes, bands, dispositions, outcomes), for
  non-negative counters, score ranges (`probability`, `classifier_score` ∈ [0,1], `risk_score` ∈ [0,100]),
  `completed_at ≥ started_at`, lowercase e-mail, hexadecimal SHA-256 values and review-note length (≤ 2000).
* `UNIQUE(users.email)`, `UNIQUE(model_versions.model_name, version)`, `UNIQUE(predictions.analysis_job_id, record_index)`.
* `datasets.owner_user_id` may only be NULL for non-upload (system-imported) datasets.

### 4.3 Indexes (ERD §6)

| Index | Serves |
|---|---|
| `uq_users_email`, `ix_users_role_is_active` | login, user administration |
| `ix_datasets_owner_user_id_created_at (owner, created_at DESC)`, `ix_datasets_sha256` (partial), `ix_datasets_status` | dataset lists, duplicate detection |
| `ix_model_versions_status`, `uq_model_versions_model_name_version` | model catalogue |
| `ix_analysis_jobs_submitted_by_created_at`, `ix_analysis_jobs_status_created_at`, `ix_analysis_jobs_dataset_id`, `ix_analysis_jobs_model_version_id` | job lists, worker recovery |
| `uq_predictions_analysis_job_id_record_index`, `ix_predictions_analysis_job_id_risk_band`, `ix_predictions_predicted_label`, `ix_predictions_created_at` | result pages, dashboard trends |
| `ix_predictions_alerts_created_at` (partial, `WHERE is_alert`) | alert queue |
| `ix_alert_reviews_prediction_id_created_at`, `ix_alert_reviews_reviewed_by` | latest disposition per alert |
| `ix_audit_logs_actor_user_id_created_at`, `ix_audit_logs_action_created_at`, `ix_audit_logs_resource`, `ix_audit_logs_created_at` | audit search |

No JSONB GIN indexes are created (ERD §6: only for demonstrated query patterns).

### 4.4 Append-only enforcement

The migration installs `cybersentinel_reject_mutation()` and `BEFORE UPDATE OR DELETE` / `BEFORE TRUNCATE` triggers
on `audit_logs` and `alert_reviews`. A retention purge must therefore be an explicit, privileged DBA operation
(e.g. `ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_append_only;` inside a reviewed maintenance window).

## 5. Verification performed

The migration was executed against a throwaway local PostgreSQL 16 cluster during development:
`alembic upgrade head` → Alembic `compare_metadata` against the ORM reported **no differences** → constraint and
trigger probes (invalid role, uppercase e-mail, duplicate e-mail, upload without owner, non-hex SHA-256, duplicate
model name/version, UPDATE/DELETE/TRUNCATE on `audit_logs`) were all rejected → `alembic downgrade base` →
`alembic upgrade head` again. The same checks are automated in
`backend/tests/migrations/test_postgres_migration.py` (runs when `TEST_POSTGRES_MIGRATION_URL` is set).

## 6. Retention, backup and restore

| Data class | Default retention | Mechanism |
|---|---|---|
| Uploaded CSV files | Until the dataset is deleted, or `DATASET_RETENTION_DAYS` (default 90) via `python -m app.cli purge-datasets` | File removed; metadata row kept (`status='deleted'`) |
| Rejected uploads | File deleted immediately; validation report kept | Automatic |
| Predictions, reviews, audit logs | Not purged automatically | Decide per policy (ERD §13 open decision) |

Backups (run by you; encrypt and access-control the output):

```bash
pg_dump --format=custom --file=cybersentinel_$(date +%Y%m%d).dump "postgresql://cybersentinel_owner@localhost/cybersentinel"
createdb --encoding=UTF8 --template=template0 cybersentinel_restore_test
pg_restore --dbname=cybersentinel_restore_test --no-owner cybersentinel_YYYYMMDD.dump
```

Back up `model_artifacts/registry.json` and the bundle directories together with the database: the database pins
manifest hashes, so restoring one without the other makes models unavailable (fail-closed).

## 7. Open decisions carried forward (ERD §13)

Partitioning `predictions` by job/date at large scale, multi-team tenant isolation, and the retention periods for
predictions/reviews/audit logs are left for your deployment decision; the schema does not preclude any of them.
