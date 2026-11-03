# Security Guide

CyberSentinel processes network-flow data and produces decisions that analysts act on, so it protects three things:
the **data** (uploaded flows, results, reviews), the **decision pipeline** (model artifacts, risk policy) and the
**accounts** that use it. This guide lists the controls that are implemented, where they live in the code, how they
are tested, and what you must still do when you operate the system.

## 1. Threat model (summary)

| Asset | Main threats | Primary controls |
| --- | --- | --- |
| Accounts and sessions | Credential stuffing, token theft, CSRF, privilege escalation | Argon2id, lockout, rate limits, short-lived in-memory access tokens, HttpOnly SameSite=Strict refresh cookie, Origin check, server-side RBAC, token revocation |
| Uploaded datasets | Malicious files, resource exhaustion, cross-user access | Streamed size limit, row limit, strict CSV structure validation, data-only parsing, opaque storage keys, owner scoping |
| Model artifacts | Tampered pickles (code execution), silent model swaps, train/serve skew | Trusted directory only, no upload endpoint, DB-pinned manifest hash, per-file hashes, class allowlist, runtime version checks, golden parity |
| Results and audit trail | Tampering, repudiation, data leakage through exports | Append-only triggers, audited actions, formula-safe CSV, scoped exports with row caps |
| Personal data in flows | Exposure of IP addresses | HMAC pseudonymisation (or dropping) before storage; raw IPs never stored |

Joblib/pickle deserialization can execute code. The integrity chain makes it hard to load anything other than the
artifact that was approved, but it is **not a sandbox**: only place bundles you produced yourself in `MODEL_DIR`, keep
the directory read-only for the API user, and never load user-supplied serialized models.

## 2. Implemented controls

| ID | Control | Implementation | Tests |
| --- | --- | --- | --- |
| SEC-01 | Passwords hashed with Argon2id; policy (length, letters + digits, not containing the e-mail name); plaintext never stored or logged | `core/security.py`, `services/auth_service.py` | `tests/core/test_security.py`, `tests/api/test_auth_api.py` |
| SEC-02 | Role-based access control enforced server-side on every route; ownership isolation for analysts | `api/deps.py` (`AdminUser`, `AnalystUser`, `AnyUser`), repositories' visibility filters | `tests/api/test_rbac.py` (full route × role matrix) |
| SEC-03 | Parameterised queries only (SQLAlchemy expressions), allow-listed sort fields | `repositories/*` | `tests/api/test_datasets_api.py` (SQL-injection-style search string is treated as text) |
| SEC-04 | Upload validation: `.csv` only, content-type allowlist, streamed size cap, row cap, encoding detection, strict per-row field counts, schema detection, invalid-value thresholds; files stored under random names outside any web root and never executed | `services/dataset_service.py`, `services/validation_service.py`, `services/storage_service.py`, `ml/preprocessing/reader.py`, `core/middleware.py` | `tests/api/test_datasets_api.py`, `tests/ml/test_cleaning_and_reader.py` |
| SEC-05 | Secrets only from the environment; no defaults; `SecretStr`; start-up refuses weak/placeholder secrets and insecure production settings | `core/config.py` | `tests/core/test_config.py` |
| SEC-06 | Model artifact chain of trust (manifest hash in DB → per-file SHA-256 → runtime compatibility → class allowlist → interface checks; golden parity on verification); fail closed with `503 model_unavailable` | `ml/artifacts/*`, `services/model_registry_service.py` | `tests/ml/test_artifacts.py`, `tests/api/test_models_api.py` |
| SEC-07 | The API never trains, tunes or downloads models | no `fit`/tuners/network clients in `backend/app` | `tests/architecture/test_runtime_boundaries.py` |
| SEC-08 | Resource limits: rate limits, body limits, statement timeout, bounded job queue and workers, chunked inference, export and quick-analysis caps | `core/rate_limit.py`, `core/middleware.py`, `db/session.py`, `services/job_runner.py` | `tests/api/test_errors_and_security.py`, `tests/services/test_job_runner.py` |
| SEC-09 | Audit trail of security-relevant actions without secrets or raw flows; append-only at the database level; structured logs with redaction | `services/audit_service.py`, migration triggers, `core/logging.py` | `tests/api/test_users_and_audit.py`, `tests/migrations/` |
| SEC-10 | Token handling: access JWT (issuer, audience, expiry, type) in memory; refresh JWT in HttpOnly `SameSite=Strict` cookie scoped to `/api/v1/auth`; `Origin` check on refresh/logout; revocation via `token_version` on logout, password change, role change and deactivation; lockout | `core/security.py`, `api/v1/endpoints/auth.py`, `api/deps.py` | `tests/api/test_auth_api.py`, `tests/api/test_errors_and_security.py` |
| SEC-11 | Data lifecycle: soft deletion removes stored files and keeps metadata; rejected uploads are deleted immediately; retention purge CLI; IP pseudonymisation | `services/dataset_service.py`, `utils/ip.py`, `cli.py` | `tests/api/test_datasets_api.py`, `tests/core/test_utils.py` |

### HTTP hardening

* Response headers on every API response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy: same-origin`, a restrictive `Permissions-Policy`,
  `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, `Cache-Control: no-store`;
  `Strict-Transport-Security` when `HSTS_ENABLED=true`.
* CORS: explicit origin allowlist with credentials; wildcards are rejected at start-up.
* Errors: a fixed envelope; stack traces, SQL, file paths and uploaded values are never returned (validation errors do
  not echo input values).
* Account enumeration: wrong password, unknown e-mail, locked and deactivated accounts all return the same
  `invalid_credentials` response.

### Frontend

* Access token in memory only; nothing sensitive in `localStorage`. The theme preference is the only stored value.
* No HTML injection: untrusted values are rendered as text (`dangerouslySetInnerHTML` is banned by ESLint).
* Same-origin post-login redirects only; downloads through Blob URLs with sanitised names.
* Role-aware UI is a convenience — the API remains the enforcement point.

### Responsible ML output

* `probability` is only reported for calibrated models; uncalibrated scores are labelled as such.
* Risk scores are versioned policy scores, recorded per job (`risk_policy_version`).
* Explanations carry a non-causal disclaimer; the UI states that outputs are decision support, not proof of
  compromise.
* Ground-truth labels in uploaded files are used only for evaluation, never as model input.

## 3. Your responsibilities when operating CyberSentinel

1. **Transport security.** Serve the SPA and the API over HTTPS from the same origin behind a reverse proxy; set
   `COOKIE_SECURE=true`, `HSTS_ENABLED=true`, `CORS_ORIGINS=https://your-host`, and `TRUST_PROXY_HEADERS=true` only
   behind that proxy.
2. **Secrets.** Generate `AUTH_SECRET` and `IP_PSEUDONYMIZATION_KEY` randomly, store them in a secret manager or a
   root-owned `.env` readable only by the service account, and rotate them if exposed.
3. **Database.** Use the two-role setup from the [Database Documentation](database_documentation.md): migrations with
   the owner role, the API with the least-privilege runtime role. Enable backups and encryption at rest.
4. **Model directory.** Make `MODEL_DIR` writable only by the people who export bundles and read-only for the API
   process. Approve versions only after `models verify` passes.
5. **Frontend hosting.** Add a Content-Security-Policy to the static host. Plotly injects inline styles, so allow
   `style-src 'self' 'unsafe-inline'`; scripts can stay `script-src 'self'`.
6. **Logs.** Ship JSON logs to your log platform; they contain request IDs and user IDs but no secrets or flow
   contents. Review `access.denied`, `auth.login.locked` and `model.integrity.failure` audit events.
7. **Accounts.** Keep at least two administrators, deactivate leavers (accounts are never deleted so audit history
   stays attributable), and require analysts to change initial passwords.
8. **Dependencies.** Re-run `pip-audit` and `npm audit` regularly and update pinned versions deliberately.

## 4. Dependency audit status

Results of the checks run for this delivery are recorded in the [Testing Guide](testing_guide.md#5-verification-record):
`pip-audit` on the backend requirements and `npm audit --omit=dev` on the frontend runtime dependencies. The full
`npm audit` (including development tools) reports a moderate advisory in `minimatch` (GHSA-g3hv-75wg-m249) pulled in
by ESLint, typescript-eslint and openapi-typescript. These tools run only on developer machines and are not part of the
built application; the fixed `minimatch` 11 line was released in late October 2026 and is not yet used by those tools,
so update them when they adopt it.

## 5. Known limitations

* Rate limits and the model cache are per API process; with several processes, limits multiply. Run one API process
  or put a shared rate limiter in your reverse proxy.
* Analysis jobs run in-process; a restart fails running jobs (partial results are removed and the user can resubmit).
* No multi-factor authentication or single sign-on; add them at the reverse proxy or identity provider if required.
* Pickle-based artifacts must come from a trusted pipeline (see §1); the integrity checks detect changes but cannot make
  an untrusted pickle safe.
* The application is single-organisation: aggregates on the dashboard cover all users' completed jobs.
