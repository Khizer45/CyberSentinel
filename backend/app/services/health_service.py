"""Health and readiness without disclosing internals (FR-20)."""

from __future__ import annotations

import time
from typing import Literal

from sqlalchemy import text

from app import __version__
from app.core.config import Settings
from app.db.session import Database
from app.ml.artifacts import read_manifest
from app.ml.errors import ArtifactError
from app.repositories import model_versions as model_repo
from app.schemas.system import HealthResponse
from app.services.job_runner import JobRunner

STARTED_AT = time.monotonic()


def check(database: Database, settings: Settings, runner: JobRunner | None) -> HealthResponse:
    checks: dict[str, str] = {}
    try:
        with database.session() as session:
            session.execute(text("SELECT 1"))
            approved = model_repo.list_models(session, statuses=["approved"])
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001 - details are logged elsewhere, never returned
        checks["database"] = "unavailable"
        approved = []

    if checks["database"] == "ok":
        if not approved:
            checks["model_registry"] = "no_approved_models"
        else:
            problems = 0
            for model in approved[:10]:
                try:
                    read_manifest(settings.model_dir, model.artifact_uri, expected_sha256=model.artifact_sha256)
                except ArtifactError:
                    problems += 1
            checks["model_registry"] = "ok" if problems == 0 else "degraded"
    else:
        checks["model_registry"] = "unknown"
    checks["job_runner"] = "ok" if runner is not None and runner.running else "stopped"

    status: Literal["ok", "degraded", "unavailable"]
    if checks["database"] != "ok":
        status = "unavailable"
    elif checks["model_registry"] != "ok" or checks["job_runner"] != "ok":
        status = "degraded"
    else:
        status = "ok"
    return HealthResponse(
        status=status, version=__version__, uptime_seconds=round(time.monotonic() - STARTED_AT, 1), checks=checks
    )
