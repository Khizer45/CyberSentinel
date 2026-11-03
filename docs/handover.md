# Handover

What was built, where it is, how to bring it up, and what is still yours to do.

## 1. Delivery status

| Phase | Deliverable | State |
| --- | --- | --- |
| 1 | Requirements and architecture review (`docs/00_phase1_architecture_review.md`) | committed |
| 2 | PostgreSQL schema, ORM models, Alembic migration, database documentation | committed |
| 3 | Shared ML runtime library, six notebooks, artifact contract, training and integration guides | committed |
| 4 | FastAPI backend, operator CLI, backend tests, OpenAPI export | committed (`bd58a6b`) |
| 5 | React + TypeScript dashboard (13 pages), frontend tests, browser smoke test | committed (`580f315`) |
| 6 | Installation, configuration, backend/frontend developer, API, testing and security guides; traceability; this handover; README | committed (documentation only) |

Branch: `claude/upbeat-newton-qndgo6` of `Khizer45/CyberSentinel`; draft pull request
[Khizer45/CyberSentinel#1](https://github.com/Khizer45/CyberSentinel/pull/1). All code that was tested is in commit
`580f315`; the commits after it change documentation only.

## 2. File map

```
CyberSentinel/
├── README.md                       overview, quick start, documentation index
├── backend/
│   ├── app/
│   │   ├── main.py                 application factory (middleware, routers, job runner lifecycle)
│   │   ├── cli.py                  operator commands: create-admin, models, datasets, export-openapi, check-config
│   │   ├── api/deps.py             session, current user, role dependencies, pagination, rate limits
│   │   ├── api/v1/endpoints/       15 routers: auth, admin_users, datasets, dataset_schemas, models, analyses,
│   │   │                           predictions, alerts, analyze (quick analysis), metrics, reports, experiments,
│   │   │                           audit_logs, health, system
│   │   ├── core/                   config, constants, errors, logging, security, middleware, rate limiting
│   │   ├── db/                     base, portable types, engine/session
│   │   ├── models/                 7 ORM tables
│   │   ├── schemas/                request/response models
│   │   ├── repositories/           parameterised queries with ownership filters
│   │   ├── services/               business logic (auth, users, datasets, validation, storage, analyses, job runner,
│   │   │                           predictions, explanations, alerts, reviews, metrics, reports, audit, model registry,
│   │   │                           risk scoring, experiments, health)
│   │   ├── ml/                     runtime ML library shared with the notebooks:
│   │   │   ├── datasets/           CIC-IDS2017 and UNSW-NB15 schemas, label maps, schema detection
│   │   │   ├── preprocessing/      header normalisation, strict CSV reading, cleaning, label normalisation, transforms
│   │   │   ├── artifacts/          manifest model, integrity, compatibility, loader, golden parity, export, registry
│   │   │   ├── inference/          inference engine (labels, scores, abstention)
│   │   │   ├── risk/               versioned risk policy and scoring
│   │   │   ├── explain/            TreeSHAP / tree-path attribution / baseline deviation, reason codes
│   │   │   └── evaluation/         metrics and experiment records
│   │   └── utils/                  CSV formula safety, IP pseudonymisation, text helpers
│   ├── migrations/                 Alembic environment and 20261102_0001_initial_schema.py
│   ├── config/risk_policy.json     risk policy 1.0.0
│   ├── tests/                      api, core, ml, services, architecture, migrations (+ synthetic fixtures)
│   ├── requirements*.txt, constraints.txt, pyproject.toml, alembic.ini, .env.example
├── frontend/
│   ├── src/                        pages/, components/, features/, services/, hooks/, utils/, styles/, types/, test/
│   ├── e2e/smoke.mjs               optional Playwright smoke test (disposable databases only)
│   ├── package.json, package-lock.json, vite.config.ts, tsconfig*.json, eslint.config.js, .npmrc, .env.example
├── notebooks/
│   ├── 01_data_exploration … 06_model_evaluation.ipynb
│   ├── nb_utils/                   training-only helpers (raw data, audits, splits, models, semi-supervised, plots)
│   ├── tests/                      opt-in end-to-end smoke test on synthetic files
│   └── requirements.txt
├── model_artifacts/                MODEL_DIR: bundles/, experiments/, registry.json (empty until you export)
├── data/, reports/                 your datasets and notebook reports (contents ignored by git)
└── docs/                           all guides, dataset cards, api/openapi.json
```

## 3. Bring-up checklist

1. **Python environment** — `backend/.venv`, `pip install -r requirements.txt -c constraints.txt`
   ([Installation Guide §2](installation_guide.md#2-backend-environment)).
2. **PostgreSQL** — create the UTF-8 database and the owner/runtime roles
   ([Database Documentation §1](database_documentation.md#1-provisioning-you-run-these)).
3. **Configuration** — `backend/.env` from `.env.example` with your `DATABASE_URL`, a random `AUTH_SECRET` and
   `IP_PSEUDONYMIZATION_KEY` ([Configuration Guide](configuration_guide.md)).
4. **Schema** — `alembic upgrade head` with the owner role.
5. **Administrator** — `python -m app.cli create-admin …`.
6. **Datasets** — download CIC-IDS2017 and/or UNSW-NB15 into `data/raw/<family>/` (see the dataset cards for the
   expected files and licences).
7. **Training** — notebook environment (`notebooks/requirements.txt`), then run notebooks 01–06 per family
   ([Model Training Guide](model_training_guide.md)). Review the reports in `reports/<family>/`, including the
   shortcut-feature ablation and the risk-policy sweep, before exporting.
8. **Artifacts** — notebook 06 writes `model_artifacts/bundles/<name>/<version>/` and updates `registry.json`;
   then `python -m app.cli models sync`, `models verify`, `models approve`
   ([Model Artifact Integration Guide](model_artifact_integration_guide.md)).
9. **Run** — `uvicorn app.main:app --host 127.0.0.1 --port 8000` and `npm run dev` in `frontend/`.
10. **Test** — `pytest -q`, `npm test`, `npm run build`; optionally the PostgreSQL suite and the browser smoke test
    against disposable databases ([Testing Guide](testing_guide.md)).

## 4. Manual tasks that remain yours

* Review the draft pull request and merge it when you are satisfied.
* Provision PostgreSQL, set secrets, and connect the application to your database (nothing here did that for you).
* Obtain the datasets and run the notebooks; review and, if needed, tune the risk policy placeholders in
  `backend/config/risk_policy.json` using the notebook 06 sweep (bump `policy_version` when you change it).
* Decide whether to calibrate classifiers (`CS_CALIBRATE=1`) — without calibration the UI shows classifier scores
  instead of probabilities, by design.
* Deployment: TLS-terminating reverse proxy serving the SPA and `/api/` on one origin, production `.env` rules
  ([Security Guide §3](security_guide.md#3-your-responsibilities-when-operating-cybersentinel)), backups, log
  shipping, monitoring.
* Formal verification per RTM §7: run the checks on the commit you release and record the evidence
  ([Requirements Traceability §5](requirements_traceability.md#5-evidence-register-rtm-5)).
* Add a license file before distributing the code.

## 5. Known limitations

* No trained models or performance figures are included; every metric shown in the UI comes from bundles you export.
* Background jobs run inside the API process; a restart fails in-flight jobs (they can be resubmitted). Rate limits and
  the model cache are per process.
* Batch analysis only (no live capture); single organisation; no MFA/SSO.
* Pickle-based artifacts must come from your own trusted pipeline — integrity checks detect changes but are not a
  sandbox.
* Development-only `npm audit` advisory in `minimatch` (lint/codegen tooling); runtime dependencies are clean.
* Open RTM evidence: EXPLAIN-plan review on large tables (NFR-03), production-scale benchmark (NFR-02), and the ML
  evaluation items that require real-data runs (ML-01, ML-03, ML-04, ML-06, ML-08).
