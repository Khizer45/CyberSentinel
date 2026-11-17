# Docker Guide

Run CyberSentinel with only **Docker Desktop** (Windows/macOS) or Docker Engine + Compose (Linux) installed — no
Python, Node.js or PostgreSQL on your computer. Docker is optional: the [Installation Guide](installation_guide.md)
still describes running everything natively.

| Container | What it runs | Address |
| --- | --- | --- |
| `db` | PostgreSQL 16 (data in the `pgdata` volume) | internal only |
| `backend` | FastAPI API; applies migrations and creates the first administrator on start | <http://localhost:8000/api/docs> |
| `frontend` | nginx serving the dashboard and forwarding `/api` to the backend | <http://localhost:8080> |
| `notebooks` (optional) | JupyterLab with the training environment | <http://localhost:8888> |

## 1. First start

```bash
git clone https://github.com/Khizer45/CyberSentinel.git
cd CyberSentinel
cp .env.docker.example .env          # Windows (cmd): copy .env.docker.example .env
```

Edit `.env` and fill in:

* `POSTGRES_PASSWORD` — letters and digits only.
* `AUTH_SECRET` — a random string of at least 32 characters.
* `IP_PSEUDONYMIZATION_KEY` — another random string (or leave empty to drop IP addresses).
* `ADMIN_EMAIL` / `ADMIN_PASSWORD` — your first administrator (12+ characters with letters and digits; must not
  contain the part of the e-mail before `@`).

To generate random strings without Python, use `openssl rand -base64 48`, a password manager, or
`docker run --rm python:3.13-slim python -c "import secrets; print(secrets.token_urlsafe(48))"`.

Then:

```bash
docker compose up -d --build
docker compose ps                    # db and backend should show "healthy"
```

The first build downloads the base images and libraries and takes several minutes. Open <http://localhost:8080> and
sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

## 2. Get a model (needed for analysis)

### Option A — demo model, to try the UI (meaningless results)

```bash
docker compose exec -u root backend python scripts/demo_setup.py
docker compose exec backend python -m app.cli models sync
docker compose exec backend python -m app.cli models approve unsw-nb15-demo 1.0.0
```

This writes a small model trained on **synthetic** data and a demo file `model_artifacts/demo/demo-flows.csv`. Upload
that file under **Datasets → Upload dataset**, then click **Analyze**. Use it only to explore the screens.
`models sync` adds the demo to `model_artifacts/registry.json`; do not commit that change.

### Option B — a real model from the notebooks

1. Download CIC-IDS2017 and/or UNSW-NB15 into `data/raw/<family>/` (see `docs/dataset_cards/`).
2. Start JupyterLab and open the link printed in the log:

   ```bash
   docker compose --profile notebooks up -d --build notebooks
   docker compose logs notebooks | grep "JupyterLab:"
   ```

3. Run notebooks 01–06 in order ([Model Training Guide](model_training_guide.md)). Set notebook options
   (`CS_DATASET_FAMILY=unsw_nb15`, etc.) by adding them under `notebooks.environment` in `docker-compose.yml`, then
   `docker compose --profile notebooks up -d notebooks` again. Results are written to `data/`, `reports/` and
   `model_artifacts/` on your computer.
4. Register and approve the exported bundle:

   ```bash
   docker compose exec backend python -m app.cli models sync
   docker compose exec backend python -m app.cli models verify <model-name> <version>
   docker compose exec backend python -m app.cli models approve <model-name> <version>
   ```

Training on the full datasets needs plenty of memory; raise Docker Desktop's memory limit (Settings → Resources) to
at least 8–16 GB.

## 3. Everyday commands

| Task | Command |
| --- | --- |
| Start / stop | `docker compose up -d` / `docker compose stop` |
| Logs | `docker compose logs -f backend` |
| Rebuild after pulling new code | `docker compose up -d --build` |
| Operator CLI | `docker compose exec backend python -m app.cli <command>` |
| Database shell | `docker compose exec db psql -U cybersentinel -d cybersentinel` |
| Back up the database | `docker compose exec db pg_dump -U cybersentinel cybersentinel > backup.sql` |
| Remove containers, keep data | `docker compose down` |
| Remove **everything including data** | `docker compose down -v` |

## 4. Configuration

Docker reads `.env` in the repository root (template: `.env.docker.example`). The compose file passes these values,
plus fixed container paths (`MODEL_DIR=/models`, `UPLOAD_DIR=/data/uploads`), to the backend. Any other variable from
the [Configuration Guide](configuration_guide.md) can be added under `backend.environment` in `docker-compose.yml`.

* `PUBLIC_URL` must be exactly the address in your browser (default `http://localhost:8080`); it becomes
  `CORS_ORIGINS`, which the sign-in refresh check uses.
* To use another port, set `WEB_PORT` and change `PUBLIC_URL` to match.
* The API port 8000 and JupyterLab port 8888 are bound to `127.0.0.1` only.

## 5. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `required variable ... is missing a value` | Fill that variable in `.env`. |
| Signed out on every reload / `origin_not_allowed` | `PUBLIC_URL` does not match the browser address. |
| Backend restarts with "Database migrations failed" | `POSTGRES_PASSWORD` changed after the first start. Use the original, or `docker compose down -v` to start over (deletes data). |
| No administrator after start | Check `docker compose logs backend` for the password-policy message, fix `ADMIN_PASSWORD`, restart. |
| `Permission denied` writing to `/models` | Run that command with `-u root` (Linux bind-mount permissions). |
| Upload rejected as too large | Default limit 200 MB (`MAX_UPLOAD_MB`). |

## 6. Production note

This setup is for running the application on your own computer. For a server deployment put a TLS-terminating
reverse proxy in front, set `PUBLIC_URL` to the `https://` address, `COOKIE_SECURE=true`, `APP_ENV=production`, and
follow the [Security Guide](security_guide.md).
