# API Documentation

Base path: **`/api/v1`**. The machine-readable contract is [`docs/api/openapi.json`](api/openapi.json), exported from
the code with `python -m app.cli export-openapi`. With `ENABLE_API_DOCS=true` the running API also serves
Swagger UI at `/api/docs` and the schema at `/api/v1/openapi.json`. This page explains the conventions and lists every
endpoint; request and response fields are defined in the OpenAPI document.

## 1. Conventions

### Authentication

```http
POST /api/v1/auth/login
Content-Type: application/json

{"email": "analyst@example.org", "password": "…"}
```

Response `200`: `{"access_token": "…", "token_type": "bearer", "expires_in": 900, "user": {…}}` plus an HttpOnly
refresh cookie (`cs_refresh`, path `/api/v1/auth`). Send the access token on every other request:

```http
Authorization: Bearer <access_token>
```

`POST /auth/refresh` (cookie only) returns a new access token; `POST /auth/logout` revokes all of the user's tokens.
Both check the `Origin` header against `CORS_ORIGINS`. Scripts that cannot keep cookies simply sign in again when the
access token expires.

### Roles

| Role | Access |
| --- | --- |
| `viewer` | Own profile; aggregate metrics, reports, approved models, experiments, risk policy, system info |
| `analyst` | Everything a viewer can do, plus datasets, analyses, predictions, alerts, reviews, quick analysis and exports — **own records** and shared system datasets |
| `admin` | Everything, all records, plus users, audit logs, model status changes and artifact verification |

A missing or invalid token returns `401`; an authenticated user without the role returns `403` (and the denial is
audited); a record outside the caller's scope returns `404`.

### Errors

Every error uses the same envelope:

```json
{"error": {"code": "dataset_rejected", "message": "the columns do not match any supported dataset schema", "details": {"reason": "feature_schema_error"}, "request_id": "4f0c…"}}
```

| Status | Typical `code` values |
| --- | --- |
| 400 | `validation_error` (malformed body or parameters; `details` lists `{field, message, type}`), `bad_request` |
| 401 | `authentication_required`, `invalid_credentials`, `session_expired`, `invalid_token` |
| 403 | `permission_denied`, `origin_not_allowed` |
| 404 | `not_found` |
| 409 | `duplicate_dataset`, `dataset_in_use`, `dataset_not_ready`, `model_not_approved`, `email_taken`, `last_admin`, `invalid_status_transition`, `job_finished`, `job_not_completed` |
| 413 | `payload_too_large` |
| 415 | `unsupported_media_type` |
| 422 | `dataset_rejected`, `incompatible_dataset`, `unsupported_mode`, `unsupported_schema`, `weak_password`, `too_many_records`, `model_verification_failed`, feature-contract errors for quick analysis |
| 429 | `rate_limited` (`Retry-After` header and `details.retry_after_seconds`) |
| 503 | `model_unavailable` (artifact missing, modified or incompatible — no fallback model is used), `queue_full`, `service_unavailable` |

Messages never contain stack traces, SQL, file-system paths, secrets or uploaded data. Quote the `request_id` (also
returned as the `X-Request-ID` header) when reporting a problem.

### Lists, sorting and filters

List endpoints accept `limit` (1–100, default 25) and `offset`, and return
`{"items": [...], "total": N, "limit": L, "offset": O}`. `sort` takes one allow-listed field, prefixed with `-`
for descending (for example `-created_at`, `-risk_score`). Repeated parameters express "any of"
(`?severity=high&severity=critical`). Dates are ISO 8601 (`date_from`, `date_to`).

### Rate limits

Per API process (see the [Configuration Guide](configuration_guide.md#rate-limits-per-api-process)): sign-in,
uploads, job submissions, quick analysis and exports have dedicated limits; every request also counts towards a
default limit.

### Score semantics

| Field | Meaning |
| --- | --- |
| `predicted_label` | Model class; `needs_review` when confidence is below the model's minimum; `unclassified` in anomaly-only mode |
| `probability` | Calibrated probability — **only** for models whose calibration was evaluated; otherwise `null` |
| `classifier_score` | Uncalibrated score (1 − score of the benign class); for ranking, not a likelihood |
| `anomaly_score`, `is_anomaly` | Higher = more unusual than the benign training traffic; flag = above the model threshold |
| `risk_score`, `risk_band` | Versioned policy score 0–100 and band `low` / `medium` / `high` / `critical` — not a probability |
| `is_alert` | The risk policy's alert rule fired (default: band ≥ high) |
| `explanation` | Attributions and reason codes for the selected rows, with a non-causal disclaimer and the risk breakdown |
| `true_label` | Label contained in the uploaded file — used only for evaluation, never as model input |

## 2. Endpoints

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | public | Readiness: `ok`, `degraded` (no approved/loadable model or job runner stopped) or `unavailable` (database down, HTTP 503). No internal details. |
| GET | `/health/live` | public | Liveness |
| POST | `/auth/login` | public | Sign in (rate limited, lockout after repeated failures) |
| POST | `/auth/refresh` | cookie | New access token from the refresh cookie |
| POST | `/auth/logout` | any | Revoke all of the user's tokens and clear the cookie |
| GET / PATCH | `/auth/me` | any | Own profile / change display name |
| POST | `/auth/change-password` | any | Change own password (revokes all sessions) |
| GET / POST | `/admin/users` | admin | List (filters `role`, `is_active`, `q`) / create users |
| GET / PATCH | `/admin/users/{user_id}` | admin | Read / update name, role, active flag (the last active admin is protected) |
| POST | `/admin/users/{user_id}/reset-password` | admin | Set a new password and revoke the user's sessions |
| GET | `/dataset-schemas` | any | Supported schemas with feature, identifier and label columns |
| POST | `/datasets` | analyst | Upload a CSV (`multipart/form-data`: `file`, optional `name`, `schema_version`) → `201` validated dataset, or `422 dataset_rejected` with reasons |
| GET | `/datasets` | analyst | List (filters `status`, `schema_version`, `q`, `include_deleted`) |
| GET / DELETE | `/datasets/{dataset_id}` | analyst | Details with validation report / delete the stored file (metadata kept) |
| GET | `/models` | any | Model versions (non-admins: approved only; filters `status`, `dataset_family`) |
| GET | `/models/{model_version_id}` | any | Model metadata, thresholds, recorded metrics (no file paths) |
| PATCH | `/models/{model_version_id}/status` | admin | `approved` (re-verified first), `retired` or `revoked` (with `reason`) |
| POST | `/models/{model_version_id}/verify` | admin | Integrity, runtime compatibility and golden-parity checks |
| POST | `/analyses` | analyst | Start a job (`dataset_id`, `model_version_id`, `requested_mode`) → `202` and `Location` |
| GET | `/analyses` | analyst | List jobs (filters `status`, `dataset_id`, `model_version_id`) |
| GET | `/analyses/{job_id}` | analyst | Status, progress and summary |
| POST | `/analyses/{job_id}/cancel` | analyst | Cancel a queued or running job (partial results are discarded) |
| GET | `/analyses/{job_id}/predictions` | analyst | Predictions (filters `label`, `risk_band`, `is_anomaly`, `is_alert`, `min_risk`, `max_risk`) |
| GET | `/analyses/{job_id}/export` | analyst | CSV or JSON export (`format`), same filters; `X-Export-Truncated` header |
| GET | `/predictions/{prediction_id}` | analyst | Prediction detail with explanation, context and reviews |
| GET / POST | `/predictions/{prediction_id}/reviews` | analyst | Review history / add a review (`disposition`, `notes`) — append-only |
| GET | `/alerts` | analyst | Alert queue (filters `severity`, `status`, `label`, `analysis_job_id`, `dataset_id`, `date_from`, `date_to`, `ip`) |
| GET | `/alerts/export` | analyst | CSV or JSON export of the filtered queue |
| GET | `/alerts/{alert_id}` | analyst | Alert detail (same shape as a prediction detail) |
| POST | `/analyze/record`, `/analyze/batch` | analyst | Quick analysis of JSON flow records (bounded, synchronous, not stored, audited) |
| GET | `/metrics/summary` | any | Organisation-wide aggregates for completed jobs (`date_from`, `date_to`) |
| GET | `/metrics/trends` | any | Per-day or per-hour counts (`bucket`) |
| GET | `/metrics/models` | any | Recorded metrics per model version |
| GET | `/reports/summary` | any | Summary report as JSON or CSV (`format`) |
| GET | `/experiments`, `/experiments/{experiment_id}` | any | Experiment records written by the notebooks |
| GET | `/audit-logs` | admin | Audit trail (filters `action`, `actor_user_id`, `resource_type`, `resource_id`, `outcome`, dates) |
| GET | `/risk-policy` | any | Active risk policy and its SHA-256 |
| GET | `/system/info` | any | Version, environment, supported schemas and limits for clients |

Alert status is derived from the latest review: no review → `open`; `needs_investigation` → `investigating`; any
other disposition (`true_positive`, `false_positive`, `benign`, `duplicate`) → `closed`.

## 3. Example: end-to-end with `curl`

```bash
API=http://127.0.0.1:8000/api/v1
TOKEN=$(curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"analyst@example.org","password":"<password>"}' | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl -s -H "Authorization: Bearer $TOKEN" -F "file=@flows.csv;type=text/csv" $API/datasets
curl -s -H "Authorization: Bearer $TOKEN" "$API/models"
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"dataset_id":"<id>","model_version_id":"<id>","requested_mode":"combined"}' $API/analyses
curl -s -H "Authorization: Bearer $TOKEN" "$API/analyses/<job_id>"
curl -s -H "Authorization: Bearer $TOKEN" "$API/analyses/<job_id>/predictions?is_alert=true&sort=-risk_score&limit=10"
curl -s -H "Authorization: Bearer $TOKEN" -o alerts.csv "$API/alerts/export?format=csv&severity=critical"
```

CSV exports neutralise spreadsheet formula prefixes (`=`, `+`, `-`, `@`, tab, carriage return, line feed) in text cells.
