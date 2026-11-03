# Configuration Guide

CyberSentinel is configured through environment variables. The API reads them from the process environment and from
`backend/.env` (environment variables win). Templates: `backend/.env.example` and `frontend/.env.example`.
The authoritative definitions, defaults and limits are in `backend/app/core/config.py`.

Rules that apply everywhere:

* **Secrets** (`DATABASE_URL`, `AUTH_SECRET`, `IP_PSEUDONYMIZATION_KEY`) have no defaults, are held as secret
  strings (never printed, logged or returned by the API) and must never be committed.
* Relative paths are resolved against the `backend/` directory, not the current working directory.
* The API refuses to start on invalid values (wrong type, out of range, placeholder secrets) and tells you which
  variable is wrong.

## 1. API (`backend/.env`)

### Application

| Variable | Default | Allowed | Purpose |
| --- | --- | --- | --- |
| `APP_ENV` | `development` | `development`, `test`, `production` | `production` enables the strict rules in §3 |
| `LOG_LEVEL` | `INFO` | `DEBUG` … `ERROR` | Log verbosity |
| `LOG_JSON` | `true` | bool | One JSON object per log line (with request ID); secrets are redacted |
| `ENABLE_API_DOCS` | `true` | bool | Swagger UI at `/api/docs` and the schema at `/api/v1/openapi.json` |

### Database

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | **required, secret** | `postgresql+psycopg://user:password@host:5432/db` — the least-privilege runtime role |
| `DB_POOL_SIZE` | `10` (1–100) | Connection pool size |
| `DB_MAX_OVERFLOW` | `20` (0–200) | Extra connections allowed above the pool |
| `DB_POOL_TIMEOUT_SECONDS` | `30` | Wait for a pooled connection |
| `DB_STATEMENT_TIMEOUT_MS` | `60000` | Server-side statement timeout for API sessions |
| `DB_ECHO` | `false` | Log SQL (development only; never with real data) |

### Authentication and sessions

| Variable | Default | Purpose |
| --- | --- | --- |
| `AUTH_SECRET` | **required, secret** | JWT signing key, ≥ 32 characters. Rotating it signs everyone out. |
| `JWT_ALGORITHM` | `HS256` | `HS256`, `HS384` or `HS512` |
| `JWT_ISSUER` / `JWT_AUDIENCE` | `cybersentinel` / `cybersentinel-api` | Token claims checked on every request |
| `ACCESS_TOKEN_TTL_MINUTES` | `15` (1–120) | Access-token lifetime (kept in browser memory only) |
| `REFRESH_TOKEN_TTL_HOURS` | `12` (1–168) | Refresh-cookie lifetime |
| `REFRESH_COOKIE_NAME` | `cs_refresh` | HttpOnly cookie, path `/api/v1/auth` |
| `COOKIE_SECURE` | `true` | Send the cookie over HTTPS only. Set `false` only for local HTTP development. |
| `COOKIE_SAMESITE` | `strict` | `strict` or `lax` |
| `LOGIN_MAX_FAILED_ATTEMPTS` | `5` | Failed sign-ins before the account is locked |
| `LOGIN_LOCKOUT_MINUTES` | `15` | Lock duration |
| `PASSWORD_MIN_LENGTH` | `12` (8–64) | Minimum password length (plus letters and digits, not containing the e-mail name) |

### HTTP

| Variable | Default | Purpose |
| --- | --- | --- |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated explicit origins (no wildcards). Also the allowlist for the `Origin` check on refresh/logout. |
| `TRUST_PROXY_HEADERS` | `false` | Use `X-Forwarded-For` for the client IP — only behind a reverse proxy you control |
| `HSTS_ENABLED` | `false` | Send `Strict-Transport-Security` (enable when served over HTTPS) |
| `MAX_JSON_BODY_KB` | `1024` | Maximum JSON request body |

### Model artifacts (trusted, read-only)

| Variable | Default | Purpose |
| --- | --- | --- |
| `MODEL_DIR` | `../model_artifacts` | Directory containing `bundles/` and `registry.json` |
| `MODEL_MANIFEST` | `<MODEL_DIR>/registry.json` | Registry index read by `python -m app.cli models sync` |
| `EXPERIMENTS_DIR` | `<MODEL_DIR>/experiments` | Experiment records shown on the Models → Experiments tab |
| `MAX_ARTIFACT_MB` | `2048` | Refuse to load larger artifact files |
| `MODEL_CACHE_SIZE` | `4` | Loaded bundles kept in memory (LRU) |
| `MODEL_PRELOAD` | `false` | Load approved bundles at start-up instead of on first use |

### Dataset uploads

| Variable | Default | Purpose |
| --- | --- | --- |
| `UPLOAD_DIR` | `storage/uploads` | Where validated uploads are stored under random names (outside any web root) |
| `MAX_UPLOAD_MB` | `200` | Maximum upload size (enforced while streaming) |
| `MAX_UPLOAD_ROWS` | `1000000` | Maximum data rows per file |
| `MAX_INVALID_VALUE_FRACTION` | `0.2` | Reject the file if any feature column has a larger share of non-numeric/out-of-range values |
| `REJECT_UNKNOWN_COLUMNS` | `false` | Reject files with columns the schema does not know (otherwise they are ignored and reported) |
| `DATASET_RETENTION_DAYS` | `90` | Default for `python -m app.cli datasets purge` |

### Analysis jobs and explanations

| Variable | Default | Purpose |
| --- | --- | --- |
| `JOB_WORKERS` | `2` | Concurrent analysis jobs per API process |
| `JOB_QUEUE_MAX` | `20` | Queued jobs before new submissions get `503 queue_full` |
| `JOB_STALE_AFTER_SECONDS` | `600` | A running job without a heartbeat for this long is failed and its partial results removed |
| `JOB_EXECUTION` | `background` | `inline` runs jobs inside the request — **only allowed with `APP_ENV=test`** |
| `INFERENCE_BATCH_SIZE` | `5000` | Rows scored per chunk (memory vs. speed) |
| `EXPLAIN_SCOPE` | `alerts_and_review` | Which rows get stored explanations: `alerts`, `alerts_and_review`, `all`, `none` |
| `EXPLAIN_MAX_ROWS_PER_JOB` | `2000` | Upper bound on explained rows per job |
| `EXPLAIN_TOP_K` | `8` | Features listed per explanation |
| `QUICK_ANALYSIS_MAX_RECORDS` | `100` | Records per quick-analysis request |
| `EXPORT_MAX_ROWS` | `100000` | Rows per CSV/JSON export (truncation is signalled with `X-Export-Truncated: true`) |

### Risk policy

| Variable | Default | Purpose |
| --- | --- | --- |
| `RISK_POLICY_PATH` | `config/risk_policy.json` | Versioned policy that turns model outputs into 0–100 risk scores and bands. See [Risk Scoring Policy](risk_scoring_policy.md). Change the `policy_version` whenever you edit it; each job records the version it used. |

### Rate limits (per API process)

Format `<count>/<second|minute|hour|day>`.

| Variable | Default | Applies to |
| --- | --- | --- |
| `RATE_LIMIT_ENABLED` | `true` | Master switch |
| `RATE_LIMIT_LOGIN` | `10/minute` | Sign-in (per client IP and per account) and password changes |
| `RATE_LIMIT_UPLOAD` | `30/hour` | Dataset uploads, per user |
| `RATE_LIMIT_ANALYSIS` | `60/hour` | Analysis job submissions, per user |
| `RATE_LIMIT_QUICK_ANALYSIS` | `120/minute` | Quick analysis, per user |
| `RATE_LIMIT_EXPORT` | `30/hour` | Prediction, alert and report exports, per user |
| `RATE_LIMIT_DEFAULT` | `600/minute` | Baseline for every API request, and token refresh |

### Privacy

| Variable | Default | Purpose |
| --- | --- | --- |
| `IP_PSEUDONYMIZATION_KEY` | unset (secret) | HMAC key for IP addresses found in uploaded flows. Stored values look like `ip_<16 hex>`. If unset, IPs are dropped entirely. Changing the key breaks IP filtering for older results. |
| `AUDIT_CLIENT_IP` | `true` | Record the client IP address in audit-log entries |

## 2. Frontend (`frontend/.env.local`)

Only variables starting with `VITE_` are exposed to the browser bundle — never put secrets in frontend files.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api/v1` | API base URL as seen by the browser; keep the default with the dev proxy or a same-origin reverse proxy |
| `VITE_DEV_API_PROXY` | `http://127.0.0.1:8000` | Development server only: target for `/api` requests |

## 3. Production rules (enforced when `APP_ENV=production`)

The API refuses to start unless:

* `COOKIE_SECURE=true`,
* `DATABASE_URL` points to PostgreSQL (SQLite is for automated tests only),
* every `CORS_ORIGINS` entry uses `https://`.

Also recommended: `HSTS_ENABLED=true`, `ENABLE_API_DOCS=false` unless needed, `LOG_JSON=true`, a reverse proxy that
terminates TLS, and `TRUST_PROXY_HEADERS=true` only behind that proxy.

## 4. Notebooks (training environment)

The notebooks read `CS_*` variables (see `notebooks/nb_utils/config.py` and the
[Model Training Guide](model_training_guide.md#3-configuration)):

| Variable | Default | Purpose |
| --- | --- | --- |
| `CS_DATASET_FAMILY` | `cicids2017` | `cicids2017` or `unsw_nb15` |
| `CS_RANDOM_SEED` | `42` | Seed for splits, sampling and estimators |
| `CS_RAW_DIR` / `CS_PROCESSED_DIR` / `CS_REPORTS_DIR` | `data/raw/<family>` / `data/processed/<family>` / `reports/<family>` | Data and report locations |
| `CS_MODEL_DIR` | `model_artifacts` | Where bundles, the registry and experiment records are written (the API's `MODEL_DIR`) |
| `CS_MAX_ROWS_PER_FILE` | unset | Row cap per raw file — quick iteration only, never for reported results |
| `CS_N_JOBS` | `-1` | Parallelism |
| `CS_FAST_MODE` | `0` | `1` = tiny models for smoke tests only |
| `CS_LINEAR_SAMPLE` | `200000` | Training subsample for linear models |
| `CS_SEMI_POOL_SIZE` / `CS_SEMI_EVAL_SIZE` | `20000` / `20000` | Semi-supervised experiment sizes |
| `CS_SEMI_SEEDS` / `CS_LABEL_BUDGETS` | `0,1,2` / `0.01,0.05,0.1,0.2,0.4,1.0` | Repetitions and label fractions |
| `CS_DROP_SHORTCUT_FEATURES` | `0` | `1` = drop the schema's shortcut-feature candidates |
| `CS_RUN_HOLDOUT` | `1` | Run the unknown-attack hold-out experiment |
| `CS_CALIBRATE` | `0` | `1` = calibrate the selected classifier (probabilities then become available in the UI) |
| `CS_MODEL_VERSION` | `1.0.0` | Version written to the exported bundle |
| `CS_EXPORT_BINARY` | `0` | `1` = also export the binary classifier bundle (notebook 06) |
| `CS_EXPORT_SEMI` | `0` | `1` = notebook 05 stages a Label Spreading model, which notebook 06 exports as a `semi_supervised` bundle |
| `CS_SEMI_EXPORT_BUDGET` | `0.1` | Label fraction used for that staged semi-supervised model |
| `CS_OVERWRITE_BUNDLE` | `0` | `1` = replace an existing bundle with the same name and version |

## 5. Changing configuration safely

* Restart the API after changing `backend/.env`.
* Changing `AUTH_SECRET` invalidates every session.
* Changing the risk policy affects new jobs only; existing results keep the policy version they were scored with.
* Lowering upload limits does not affect datasets that were already accepted.
