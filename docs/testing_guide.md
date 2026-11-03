# Testing Guide

CyberSentinel has five layers of automated checks. None of them connects to your real database or downloads data or
models; fixtures are generated synthetically inside the tests.

| Layer | Location | Runs by default | What it proves |
| --- | --- | --- | --- |
| Backend unit + API tests | `backend/tests` | yes (`pytest`) | Auth, RBAC, uploads, validation, jobs, predictions, alerts, reviews, exports, models, audit, errors, config safety, ML library |
| Architecture tests | `backend/tests/architecture` | yes | The API package contains no training, tuning or network-download code paths |
| PostgreSQL migration tests | `backend/tests/migrations` | opt-in | Migration ↔ ORM equality, constraints, append-only triggers on a real PostgreSQL |
| Notebook smoke tests | `notebooks/tests` | opt-in | All six notebooks execute end to end and export bundles the API can load and verify |
| Frontend tests | `frontend/src/**/*.test.ts(x)` | yes (`npm test`) | Session handling, route guards, upload checks, review flow, score semantics, tables, charts, utilities |
| Browser smoke test | `frontend/e2e/smoke.mjs` | manual | The real UI against a running API (creates data — disposable databases only) |

## 1. Backend

```bash
cd backend
source .venv/bin/activate
pytest -q                                   # in-memory SQLite, fixture model bundles built on the fly
pytest tests/api/test_rbac.py -q            # a single module
pytest -q --cov=app --cov-report=term       # with coverage (pytest-cov)
```

`tests/conftest.py` builds settings with `_env_file=None`, so your `backend/.env` (and the database it points to) is
never read by the test-suite. Three small model bundles are fitted on synthetic data per test session (random forest
and XGBoost multi-class with an Isolation Forest, and a binary random forest) and exported through the same code path
as the notebooks; they exercise the full chain of trust and inference, but their numbers mean nothing.

### Against PostgreSQL (recommended before releases)

Create two **empty, disposable** databases (UTF-8). Tables are dropped and recreated for every test.

```bash
TEST_DATABASE_URL=postgresql+psycopg://user:pw@localhost:5432/cs_test \
TEST_POSTGRES_MIGRATION_URL=postgresql+psycopg://user:pw@localhost:5432/cs_migration_test \
pytest -q
```

### Static checks

```bash
ruff check . && ruff format --check .
mypy app
pip-audit -r requirements.txt
```

## 2. Notebooks

```bash
cd notebooks
CS_RUN_NOTEBOOK_SMOKE=1 python -m pytest tests -q
```

Requires the notebook environment (`notebooks/requirements.txt`). For each dataset family the test writes small
synthetic files in the official column layout to a temporary directory, runs notebooks 01–06 in fast mode, and checks
that the exported bundles load and pass golden parity. It validates the pipeline mechanics only; real metrics come
from running the notebooks on the real datasets (see the [Model Training Guide](model_training_guide.md)).

## 3. Frontend

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm test
npm run build
npm audit --omit=dev
```

Tests use Vitest with jsdom and Testing Library. Services are mocked per test (`vi.mock("../services/…")`);
`src/test/render.tsx` provides the app's providers with a fake session (`renderWithProviders(ui, { route, path, auth })`)
and `src/test/fixtures.ts` builds typed API objects. Plotly is mocked globally; charts are asserted through their data
tables.

## 4. Browser smoke test (optional, manual)

Runs the real UI in Chromium against a running stack: sign-in, upload with duplicate detection, analysis job,
filters and CSV export, prediction review, alerts, quick analysis, model verification, report download, user creation,
audit log, session reload, sign-out and viewer restrictions. **It creates data (a dataset, a job, a review and a
viewer account) — use a disposable database.**

```bash
cd frontend
npx playwright install chromium           # once
# API running with an approved model; frontend running with `npm run dev`
E2E_ADMIN_EMAIL=admin@example.org E2E_ADMIN_PASSWORD='…' E2E_CSV=/path/to/test-flows.csv npm run e2e:smoke
```

The CSV should match the approved model's schema and contain attack traffic (otherwise the alert step is skipped).
Screenshots are written to `frontend/e2e-output/` (ignored by git).

## 5. Verification record

Commands executed for this delivery on **2026-11-03** in an isolated Linux sandbox (Python 3.13, Node 22,
PostgreSQL 16 in a throwaway cluster). The code checked is commit `580f315` on branch `claude/upbeat-newton-qndgo6` (all backend,
notebook and frontend code); later commits change documentation only.

| Check | Result |
| --- | --- |
| Backend tests, SQLite | 159 passed, 11 skipped (PostgreSQL-only migration tests) |
| Backend tests, PostgreSQL 16 (`TEST_DATABASE_URL` + `TEST_POSTGRES_MIGRATION_URL`) | 170 passed |
| `ruff check` / `ruff format --check` | no findings / all files formatted |
| `mypy app` | no issues in 130 source files |
| `pip-audit -r requirements.txt` | no known vulnerabilities |
| Notebook smoke tests (`CS_RUN_NOTEBOOK_SMOKE=1`, both dataset families) | 2 passed (all six notebooks executed per family; exported bundles loaded and passed golden parity) |
| Frontend `typecheck`, `lint` | no errors |
| Frontend `npm test` | 15 files, 57 tests passed |
| Frontend `npm run build` | succeeded (main bundle 493 kB / 152 kB gzip; Plotly chunk 1.16 MB / 383 kB gzip, loaded on demand) |
| `npm audit --omit=dev` | 0 vulnerabilities |
| `npm audit` (including dev tools) | 11 moderate findings, all the `minimatch` advisory GHSA-g3hv-75wg-m249 in ESLint/typescript-eslint/openapi-typescript (see the [Security Guide](security_guide.md#4-dependency-audit-status)) |
| Browser smoke test (`npm run e2e:smoke`) against a live API, throwaway PostgreSQL and a synthetic test-fixture model | 16 of 16 steps passed; no browser console errors; the only HTTP errors were the expected 401 from the first session check and the deliberate duplicate-upload 409 |

Earlier in the project (2026-11-02, same sandbox) the operator workflow was also exercised end to end on a fresh
PostgreSQL database: `alembic upgrade head`, `create-admin`, fixture bundle export, `models sync/approve/verify`,
and a 12,000-row analysis job processed by the background worker pool.

What has **not** been run: the notebooks on the real CIC-IDS2017 and UNSW-NB15 datasets (no data or trained models
are included in the repository, and no model performance is claimed anywhere), load tests at production scale, and
EXPLAIN-plan reviews on large tables.
