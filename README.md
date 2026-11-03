# CyberSentinel

**ML-based network threat detection platform.** Analysts upload network-flow datasets (CIC-IDS2017 or UNSW-NB15
format), run approved machine-learning models over them, and triage prioritised alerts with explanations, while every
security-relevant action is recorded in an append-only audit trail.

* **Supervised** classification (random forest / XGBoost, binary and multi-class), **unsupervised** anomaly detection
  (Isolation Forest) and **semi-supervised** experiments (Label Propagation / Label Spreading), trained in Jupyter
  notebooks that share their preprocessing code with the API.
* A versioned **risk policy** turns model outputs into 0–100 risk scores and bands; probabilities are shown only for
  calibrated models, and every result records the model, preprocessing, schema and policy versions that produced it.
* **FastAPI** backend with PostgreSQL, Argon2id + JWT authentication, role-based access (admin / analyst / viewer),
  asynchronous analysis jobs, integrity-checked model artifacts and an append-only audit log.
* **React + TypeScript** dashboard with 13 pages: dashboard, dataset management and upload, analysis jobs and quick
  analysis, prediction results, alerts and alert details, model information and experiments, analytics and reports,
  user management, audit logs, settings, plus sign-in.

> Model outputs are decision support, not proof of compromise. No trained models, datasets or performance figures are
> included in this repository: you download the public datasets, run the notebooks, and the metrics you see are the
> ones those runs measure.

## Architecture

```
Browser (React + TS) ──HTTPS──▶ FastAPI /api/v1 ──▶ services ──▶ repositories ──▶ PostgreSQL (7 tables, Alembic)
  in-memory access token          auth, RBAC,       │
  HttpOnly refresh cookie         validation        ├──▶ bounded in-process job runner
                                                    └──▶ app.ml runtime library ──▶ model_artifacts/ (trusted, read-only)
Offline: notebooks/ ──import──▶ backend/app/ml (same preprocessing = train/serve parity) ──export──▶ model_artifacts/bundles/
```

The running API never trains, tunes or downloads models (enforced by an architecture test). Bundles are registered by
an administrator and loaded only after their hashes, library versions and golden-parity outputs check out; a missing
or modified bundle makes analysis fail with a clear error instead of falling back to anything else.

## Repository layout

| Path | Contents |
| --- | --- |
| `backend/` | FastAPI app (`app/`), shared ML library (`app/ml/`), Alembic migrations, risk policy, operator CLI, tests |
| `frontend/` | React + TypeScript single-page app, unit tests, optional browser smoke test |
| `notebooks/` | Six notebooks (exploration → preprocessing → supervised → unsupervised → semi-supervised → evaluation/export) and training helpers |
| `model_artifacts/` | Where exported model bundles, the registry index and experiment records live (`MODEL_DIR`) |
| `data/`, `reports/` | Your raw/processed datasets and notebook reports (git-ignored contents) |
| `docs/` | All documentation (below) and the OpenAPI document |

## Getting started

Requirements: Python ≥ 3.12, PostgreSQL ≥ 14 (UTF-8), Node.js ≥ 22.22. No Docker.

```bash
# backend
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -c constraints.txt
cp .env.example .env          # set DATABASE_URL, AUTH_SECRET, IP_PSEUDONYMIZATION_KEY
alembic upgrade head          # with the database owner role
python -m app.cli create-admin --email admin@example.org --display-name "Platform Admin"
uvicorn app.main:app --host 127.0.0.1 --port 8000

# frontend (second terminal)
cd frontend && npm ci && npm run dev    # http://localhost:5173
```

Then train and register a model (the dashboard works without one, but analysis needs an approved model):
download the datasets into `data/raw/<family>/`, run the notebooks, and register the exported bundle with
`python -m app.cli models sync` and `models approve`. The full procedure, including database roles, is in the
[Installation Guide](docs/installation_guide.md).

## Documentation

| Guide | Covers |
| --- | --- |
| [Installation Guide](docs/installation_guide.md) | From a fresh machine to a running instance |
| [Configuration Guide](docs/configuration_guide.md) | Every environment variable, production rules, notebook settings |
| [Database Documentation](docs/database_documentation.md) | Provisioning, roles, migrations, schema, indexes, retention |
| [Model Training Guide](docs/model_training_guide.md) | Datasets, notebooks, experiments and metrics |
| [Model Artifact Integration Guide](docs/model_artifact_integration_guide.md) | Bundle format, registration, approval, integrity checks, roll-back |
| [Risk Scoring Policy](docs/risk_scoring_policy.md) | How risk scores and bands are computed |
| [API Documentation](docs/api_documentation.md) | Conventions, roles, errors, every endpoint ([OpenAPI](docs/api/openapi.json)) |
| [Backend Developer Guide](docs/backend_developer_guide.md) | Layers, request lifecycle, jobs, adding endpoints, migrations |
| [Frontend Developer Guide](docs/frontend_developer_guide.md) | Structure, session handling, data flow, conventions |
| [Testing Guide](docs/testing_guide.md) | How to run every check, plus the recorded verification results |
| [Security Guide](docs/security_guide.md) | Threat model, implemented controls, operator responsibilities |
| [Requirements Traceability](docs/requirements_traceability.md) | Every RTM requirement → implementation → evidence → status |
| [Phase 1 Review](docs/00_phase1_architecture_review.md) | Requirements analysis and the 33 resolved conflicts between the source documents |
| [Handover](docs/handover.md) | File map, setup checklist, manual tasks and known limitations |
| Dataset cards | [CIC-IDS2017](docs/dataset_cards/cicids2017.md), [UNSW-NB15](docs/dataset_cards/unsw_nb15.md) |

## Verification

Backend: 170 tests pass on PostgreSQL 16 (159 on in-memory SQLite, where the PostgreSQL-only migration tests are
skipped); ruff, mypy and pip-audit report no issues. All six notebooks run end to end on synthetic files for both
dataset families and export bundles that pass golden parity. Frontend: 57 unit tests, type checks, lint and the
production build pass, and a browser smoke test exercised the full workflow against a live API. Details and dates
are in the [Testing Guide](docs/testing_guide.md#5-verification-record).

## Scope notes

* Batch analysis of flow records; no live packet capture.
* Single organisation with per-user ownership of datasets and results.
* No license file is included yet; add one before distributing the code.
