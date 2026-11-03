# Installation Guide

This guide takes a fresh machine to a running CyberSentinel instance: database, API, trained model bundle, and the
analyst dashboard. Nothing here uses Docker, and nothing connects to a database you have not created yourself.

| Component | Version | Notes |
| --- | --- | --- |
| Python | **3.12 or newer** (verified on 3.13) | Required by numpy 2.5, scipy 1.18 and xgboost 3.4 |
| PostgreSQL | 14 or newer (verified on 16) | Database must use **UTF-8** encoding |
| Node.js | **22.22 or newer** | Frontend only; enforced by `frontend/.npmrc` (`engine-strict`) |
| Disk / RAM | ≥ 16 GB RAM recommended for training on the full datasets | The API itself is modest; see `MAX_UPLOAD_MB` |

Commands are shown for Linux/macOS. On Windows use `py -3.13` instead of `python3`, `.venv\Scripts\activate` instead
of `source .venv/bin/activate`, and `set NAME=value` (cmd) or `$env:NAME="value"` (PowerShell) instead of `export`.

---

## 1. Get the code

```bash
git clone https://github.com/Khizer45/CyberSentinel.git
cd CyberSentinel
```

## 2. Backend environment

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt -c constraints.txt        # runtime (API + shared ML library)
pip install -r requirements-dev.txt -c constraints.txt    # tests, ruff, mypy, pip-audit (development machines)
```

`constraints.txt` pins every transitive dependency to the versions the test-suite was run with. Keep it when you
install so the API and the notebooks use identical library versions — model bundles record the versions they were
trained with and the API refuses to load a bundle whose scikit-learn/XGBoost/numpy versions are incompatible.

## 3. PostgreSQL (you do this)

Create the database and two roles exactly as described in
[Database Documentation §1](database_documentation.md#1-provisioning-you-run-these): an **owner** role used only
for migrations and a least-privilege **runtime** role used by the API. The database must be created with
`ENCODING 'UTF8'`.

## 4. Configure the API

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"     # paste into AUTH_SECRET
python -c "import secrets; print(secrets.token_urlsafe(32))"     # paste into IP_PSEUDONYMIZATION_KEY
```

Edit `backend/.env`:

* `DATABASE_URL=postgresql+psycopg://cybersentinel_app:<password>@localhost:5432/cybersentinel` (runtime role)
* `AUTH_SECRET` and `IP_PSEUDONYMIZATION_KEY` from the commands above
* `COOKIE_SECURE=false` for local HTTP development (must be `true` in production)

Every variable is explained in the [Configuration Guide](configuration_guide.md). `backend/.env` is ignored by git;
never commit it. Check what the API will use (secrets are not printed):

```bash
python -m app.cli check-config
```

## 5. Create the schema and the first administrator

```bash
# Owner credentials for this step only (do not put them in backend/.env):
DATABASE_URL="postgresql+psycopg://cybersentinel_owner:<password>@localhost:5432/cybersentinel" alembic upgrade head

python -m app.cli create-admin --email admin@example.org --display-name "Platform Admin"
```

`create-admin` prompts for the password twice (minimum 12 characters, letters and digits, not containing the e-mail
name). For scripted setups use `--password-stdin`.

## 6. Model bundles

The API never trains, tunes or downloads models. A model becomes usable only after you:

1. **Train and export** a bundle with the notebooks — see the [Model Training Guide](model_training_guide.md).
   Download the CIC-IDS2017 and/or UNSW-NB15 CSV files yourself into `data/raw/<family>/` (see `data/README.md`
   and the dataset cards in `docs/dataset_cards/`).
2. **Register** it (reads `model_artifacts/registry.json`, verifies hashes, records it as `draft`):

   ```bash
   python -m app.cli models sync
   python -m app.cli models verify <model-name> <version>      # integrity, runtime compatibility, golden parity
   python -m app.cli models approve <model-name> <version>     # or approve in the UI (Models page, admin)
   ```

Bundle layout, checks and roll-back are described in the
[Model Artifact Integration Guide](model_artifact_integration_guide.md). Until a model is approved the application
runs normally but analysis features report that no approved model is available — no substitute or fake model is
ever used.

## 7. Run the API

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

* Health: <http://127.0.0.1:8000/api/v1/health>
* Interactive API docs (when `ENABLE_API_DOCS=true`): <http://127.0.0.1:8000/api/docs>

Run **one** API process. Analysis jobs execute in a bounded in-process worker pool (`JOB_WORKERS`); several processes
are safe (jobs are claimed atomically) but rate limits and model caches are per process.

## 8. Run the dashboard

```bash
cd frontend
npm ci
npm run dev            # http://localhost:5173 — proxies /api to http://127.0.0.1:8000
```

Sign in with the administrator created in step 5. See `frontend/README.md` for production builds; serve the built
files and the API from the **same origin** (a reverse proxy routing `/api/` to Uvicorn) and add that origin to
`CORS_ORIGINS`.

## 9. Verify the installation

```bash
cd backend && pytest -q                     # backend suite (in-memory SQLite; never touches your database)
cd ../frontend && npm test && npm run build # frontend unit tests and production build
```

Then in the browser: upload a CSV from your test split (Datasets → Upload), start an analysis with the approved
model, open the results and an alert. The [Testing Guide](testing_guide.md) lists every automated check, including
an optional browser smoke test that you can run against a **disposable** database.

## 10. Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `AUTH_SECRET must be at least 32 characters` at start-up | Generate a secret as in step 4. |
| `DATABASE_URL must be a PostgreSQL URL` | Use the `postgresql+psycopg://` scheme. |
| `TypeError` mentioning bytes from psycopg | The database is not UTF-8; recreate it with `ENCODING 'UTF8'`. |
| Session lost on every reload (Safari) | Safari ignores `Secure` cookies on `http://localhost`; set `COOKIE_SECURE=false` locally. |
| `origin_not_allowed` when signing in again | The page's origin is missing from `CORS_ORIGINS`. |
| `model_unavailable` (HTTP 503) | Bundle missing, modified or built with incompatible library versions; run `python -m app.cli models verify`. |
| `No approved models` in the analysis dialog | Run `models sync`, then approve the version. |
| Upload rejected | The response lists the reason (schema not recognised, too many invalid values, size/row limits). Check the dataset card for the expected columns. |
