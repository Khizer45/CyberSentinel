"""NFR-02 / FR-09: job state machine, all-or-nothing results, cancellation, stale-worker recovery."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.core.constants import JobStatus
from app.db.session import Database
from app.db.types import utcnow
from app.models import AnalysisJob, Dataset, ModelVersion, Prediction
from app.repositories import analysis_jobs as job_repo
from tests.conftest import Actor, upload
from tests.fixtures.data import unsw_csv


def queued_job(database: Database, dataset_id: str, model: ModelVersion, user_id) -> AnalysisJob:  # type: ignore[no-untyped-def]
    import uuid

    with database.session() as session:
        job = AnalysisJob(
            dataset_id=uuid.UUID(dataset_id),
            submitted_by=user_id,
            model_version_id=model.id,
            status="queued",
            requested_mode="combined",
            input_rows=100,
            processed_rows=0,
            risk_policy_version="1.0.0",
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job


def prediction_count(database: Database, job_id) -> int:  # type: ignore[no-untyped-def]
    import uuid

    job_id = uuid.UUID(str(job_id))
    with database.session() as session:
        return int(session.scalar(select(func.count()).select_from(Prediction).where(Prediction.analysis_job_id == job_id)) or 0)


def test_missing_dataset_file_fails_safely(
    app,
    client: TestClient,
    actors: dict[str, Actor],
    models: dict[str, ModelVersion],  # type: ignore[no-untyped-def]
    database: Database,
    settings,
) -> None:
    dataset = upload(client, actors["analyst"], unsw_csv(rows=50)).json()
    for path in settings.upload_dir.rglob("*.csv"):
        path.unlink()
    job = client.post(
        "/api/v1/analyses",
        headers=actors["analyst"].headers,
        json={"dataset_id": dataset["id"], "model_version_id": str(models["unsw"].id)},
    ).json()
    assert job["status"] == "failed" and job["error_code"] == "dataset_integrity_failed"
    assert "Traceback" not in (job["error_message"] or "") and prediction_count(database, job["id"]) == 0


def test_cancellation_mid_run_removes_partial_results(
    app,
    client: TestClient,
    actors: dict[str, Actor],  # type: ignore[no-untyped-def]
    models: dict[str, ModelVersion],
    database: Database,
    monkeypatch,
) -> None:
    dataset = upload(client, actors["analyst"], unsw_csv(rows=120, seed=3)).json()
    runner = app.state.runner
    runner.settings = runner.settings.model_copy(update={"inference_batch_size": 100})
    calls = {"n": 0}
    original = job_repo.current_status

    def cancel_after_first_chunk(session, job_id):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 2:  # first chunk already persisted -> user cancels now
            session.execute(update(AnalysisJob).where(AnalysisJob.id == job_id).values(status="cancelled", completed_at=utcnow()))
            session.commit()
        return original(session, job_id)

    monkeypatch.setattr(job_repo, "current_status", cancel_after_first_chunk)
    job = client.post(
        "/api/v1/analyses",
        headers=actors["analyst"].headers,
        json={"dataset_id": dataset["id"], "model_version_id": str(models["unsw"].id)},
    ).json()
    assert job["status"] == "cancelled" and prediction_count(database, job["id"]) == 0


def test_stale_running_jobs_are_recovered(
    app,
    client: TestClient,
    actors: dict[str, Actor],
    models: dict[str, ModelVersion],  # type: ignore[no-untyped-def]
    database: Database,
) -> None:
    dataset = upload(client, actors["analyst"], unsw_csv(rows=40, seed=4)).json()
    job = queued_job(database, dataset["id"], models["unsw"], actors["analyst"].user.id)
    with database.session() as session:
        session.execute(
            update(AnalysisJob)
            .where(AnalysisJob.id == job.id)
            .values(status="running", started_at=utcnow() - timedelta(hours=2), updated_at=utcnow() - timedelta(hours=1))
        )
        session.commit()
    app.state.runner.recover_stale()
    with database.session() as session:
        recovered = session.get(AnalysisJob, job.id)
        assert recovered.status == "failed" and recovered.error_code == "worker_interrupted"


def test_compare_and_set_prevents_double_execution(
    app,
    client: TestClient,
    actors: dict[str, Actor],  # type: ignore[no-untyped-def]
    models: dict[str, ModelVersion],
    database: Database,
) -> None:
    dataset = upload(client, actors["analyst"], unsw_csv(rows=40, seed=5)).json()
    job = queued_job(database, dataset["id"], models["unsw"], actors["analyst"].user.id)
    app.state.runner.process(job.id)
    first = prediction_count(database, job.id)
    app.state.runner.process(job.id)  # second worker: claim fails, nothing re-inserted
    assert first == 40 and prediction_count(database, job.id) == 40
    with database.session() as session:
        assert session.get(AnalysisJob, job.id).status == JobStatus.COMPLETED
        assert not job_repo.transition(session, job.id, ["queued"], "validating")


def test_revoked_model_fails_queued_job(
    app,
    client: TestClient,
    actors: dict[str, Actor],
    models: dict[str, ModelVersion],  # type: ignore[no-untyped-def]
    database: Database,
) -> None:
    dataset = upload(client, actors["analyst"], unsw_csv(rows=40, seed=6)).json()
    job = queued_job(database, dataset["id"], models["unsw"], actors["analyst"].user.id)
    client.patch(
        f"/api/v1/models/{models['unsw'].id}/status",
        headers=actors["admin"].headers,
        json={"status": "revoked", "reason": "test"},
    )
    app.state.runner.process(job.id)
    with database.session() as session:
        failed = session.get(AnalysisJob, job.id)
        assert failed.status == "failed" and failed.error_code == "model_revoked"
        assert session.get(Dataset, failed.dataset_id).status == "validated"
