# Backend Developer Guide

The backend is a FastAPI application (`backend/app`) on Python ≥ 3.12, SQLAlchemy 2 and PostgreSQL, plus a shared
machine-learning runtime library (`backend/app/ml`) that the training notebooks also import. This guide explains how
the pieces fit together and how to change them safely. Setup is covered in the [Installation Guide](installation_guide.md).

## 1. Layers and responsibilities

```
HTTP ─▶ middleware ─▶ api/v1/endpoints ─▶ services ─▶ repositories ─▶ models (SQLAlchemy) ─▶ PostgreSQL
                         │                   │
                         │                   ├─▶ job_runner (bounded worker pool, DB-backed job state)
                         │                   └─▶ app.ml (schemas, cleaning, artifact loading, inference, risk, explanations)
                         └─ api/deps.py: settings, database session, current user, roles, pagination, rate limits
```

| Package | Responsibility | Must not |
| --- | --- | --- |
| `core/` | Settings, constants/vocabularies, error hierarchy + envelope, JSON logging with redaction, password hashing and JWTs, middleware (request IDs, security headers, streamed body limits), rate limiter | Import services or endpoints |
| `db/` | Declarative base with naming conventions, portable column types (UUID, JSONB/JSON, INET), engine/session factory | Contain queries |
| `models/` | ORM tables mirroring the migration (7 tables, CHECK constraints) | Contain business rules |
| `schemas/` | Pydantic request/response models — the HTTP contract | Expose internal fields (paths, hashes of secrets) |
| `repositories/` | Parameterised queries (SQLAlchemy expressions only), visibility/ownership filters | Commit transactions |
| `services/` | Business rules, transactions, audit records, orchestration of `app.ml` | Know about HTTP |
| `api/` | Routers: validation, authentication, authorization, status codes, response models | Contain business logic |
| `ml/` | Runtime ML library shared with the notebooks | Fit, tune or download models (enforced by tests) |
| `cli.py` | Operator commands (admin creation, model registry, dataset import/purge, OpenAPI export) | Train models |

## 2. Request lifecycle

1. `RequestContextMiddleware` assigns or accepts an `X-Request-ID`, binds it to the logging context and returns it.
2. `SecurityHeadersMiddleware` adds `nosniff`, `DENY` framing, `no-referrer`, a restrictive CSP and `no-store`
   (HSTS when enabled).
3. `BodySizeLimitMiddleware` enforces `MAX_JSON_BODY_KB` (and `MAX_UPLOAD_MB` on `/api/v1/datasets`) while the body
   streams — a forged `Content-Length` cannot bypass it.
4. The router-level dependency applies `RATE_LIMIT_DEFAULT`; endpoints add stricter limits.
5. `get_current_user` decodes the bearer token (issuer, audience, expiry, type) and checks the user is active and
   `token_version` still matches (logout, password change and role changes bump it).
6. `require_roles(...)` enforces the role matrix; repositories enforce record ownership.
7. Errors are raised as `AppError` subclasses (`core/errors.py`) and rendered as
   `{"error": {"code", "message", "details", "request_id"}}`. Unexpected exceptions are logged with the request ID and
   returned as a generic 500 — stack traces, SQL and file paths never reach the client.

## 3. Authentication and authorization

* Passwords: Argon2id (`argon2-cffi`), policy in `core/security.password_policy_errors`.
* Tokens: short-lived access JWT (default 15 min) in the `Authorization` header; refresh JWT in an HttpOnly,
  `SameSite=Strict` cookie scoped to `/api/v1/auth`. `/auth/refresh` and `/auth/logout` also check the `Origin`
  header against `CORS_ORIGINS`.
* Lockout: `LOGIN_MAX_FAILED_ATTEMPTS` failures lock the account for `LOGIN_LOCKOUT_MINUTES`; the response is the
  same `invalid_credentials` error either way (no account enumeration).
* Roles: `admin`, `analyst`, `viewer` (matrix in `docs/00_phase1_architecture_review.md` §5.3). Use the typed
  dependencies `AdminUser`, `AnalystUser` and `AnyUser` from `api/deps.py`; denials are audited.
* Ownership: analysts see their own datasets, jobs, predictions and alerts plus shared system datasets
  (`owner_user_id IS NULL`); viewers only receive aggregates.

## 4. Analysis jobs

`POST /analyses` validates the dataset/model/mode combination, verifies the model bundle can be loaded (fail fast
with `503 model_unavailable`), stores a `queued` job and returns `202`. `services/job_runner.py`:

* runs jobs in a `ThreadPoolExecutor` of `JOB_WORKERS`, with at most `JOB_QUEUE_MAX` waiting;
* claims jobs with an atomic status transition (`queued → validating → running → completed|failed|cancelled`), so
  several API processes never process the same job;
* reads the CSV in chunks of `INFERENCE_BATCH_SIZE`, scores them, applies the risk policy, selects rows to explain
  (`EXPLAIN_SCOPE`), and writes predictions; `updated_at` is the heartbeat;
* checks for cancellation between chunks; failure or cancellation deletes partial predictions (all-or-nothing);
* a maintenance thread (every 30 s) fails jobs whose heartbeat is older than `JOB_STALE_AFTER_SECONDS` and dispatches
  queued jobs;
* stores a bounded `summary` (label and band counts, risk statistics, data quality, evaluation against dataset labels
  when present, timing) — never per-row data.

Tests run jobs inline (`JOB_EXECUTION=inline`, allowed only with `APP_ENV=test`).

## 5. Model artifacts and inference

`services/model_registry_service.py` and `app/ml/artifacts/*` implement the chain of trust described in the
[Model Artifact Integration Guide](model_artifact_integration_guide.md): DB-pinned manifest hash → per-file hashes →
runtime library compatibility → class allowlist → interface checks → golden parity on verification. Loaded bundles are
cached (`MODEL_CACHE_SIZE`). `app/ml/inference/engine.py` produces label, calibrated probability (only when the bundle
declares calibration), uncalibrated classifier score, anomaly score/flag and abstention (`needs_review`);
`app/ml/risk` converts these into policy risk scores; `app/ml/explain` builds attributions (XGBoost TreeSHAP,
tree-path attribution for forests, or the baseline-deviation heuristic).

## 6. Adding an endpoint (checklist)

1. Schema(s) in `app/schemas/` — explicit fields, bounded strings/lists, no internal data.
2. Repository function(s) with bound parameters and the visibility filter for the caller.
3. Service function: business rules, `audit_service.record(...)` for security-relevant actions, one commit.
4. Router in `app/api/v1/endpoints/`: role dependency, `response_model`, `responses=ERROR_RESPONSES`, rate limit if
   the operation is expensive; register it in `api/v1/router.py`.
5. Tests: happy path, validation errors, RBAC (`tests/api/test_rbac.py` route matrix), ownership isolation.
6. Export the schema and regenerate frontend types:

   ```bash
   python -m app.cli export-openapi --output ../docs/api/openapi.json
   cd ../frontend && npm run generate:api && npm run typecheck
   ```

## 7. Database changes

The ORM and the migration must stay identical (a test compares them on PostgreSQL).

```bash
alembic revision --autogenerate -m "describe the change"   # against a disposable database
# review the generated file: constraints, server defaults, data migrations, downgrade
alembic upgrade head
TEST_DATABASE_URL=postgresql+psycopg://...disposable... pytest tests/migrations
```

Keep the append-only triggers on `audit_logs` and `alert_reviews`. Details: [Database Documentation](database_documentation.md).

## 8. Logging and auditing

* Application logs: JSON lines with `request_id`, `user_id` and `job_id` context; values that look like secrets,
  tokens or passwords are redacted by the formatter. Uploaded data is never logged.
* Audit log: `services/audit_service.py` writes the controlled vocabulary in `core/constants.AuditAction`
  (sign-ins, uploads, jobs, reviews, exports, model status changes, access denials) without secrets or raw flows.
  `record_independent(...)` writes in its own transaction so denials and failures are kept even when the request
  fails.

## 9. Code quality

```bash
ruff check . && ruff format --check .
mypy app
pytest -q
pip-audit -r requirements.txt
```

Conventions: type hints everywhere; no bare `except`; errors as `AppError` subclasses with stable `code` values;
UTC-aware datetimes (`db.types.utcnow`); no `print` in application code (CLI only).

## 10. Operator CLI

```bash
python -m app.cli create-admin --email E --display-name N [--password-stdin]
python -m app.cli models sync | list | verify NAME VERSION | approve NAME VERSION | retire NAME VERSION
python -m app.cli models revoke NAME VERSION --reason TEXT
python -m app.cli datasets import --file PATH [--name N] [--schema-version V] [--source-type import|sample] [--owner-email E]
python -m app.cli datasets purge --older-than-days N
python -m app.cli export-openapi --output ../docs/api/openapi.json
python -m app.cli check-config
```

None of these commands trains, tunes or downloads models.
