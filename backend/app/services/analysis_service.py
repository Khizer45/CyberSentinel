"""Analysis job creation, listing and cancellation (FR-07, FR-09)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.constants import TERMINAL_JOB_STATUSES, AuditAction, DatasetStatus, JobStatus, ModelStatus
from app.core.errors import ConflictError, NotFoundError, ServiceUnavailableError
from app.db.types import utcnow
from app.models import AnalysisJob, User
from app.repositories import analysis_jobs as job_repo
from app.repositories import datasets as dataset_repo
from app.repositories import model_versions as model_repo
from app.schemas.analysis import AnalysisCreate
from app.services import audit_service
from app.services.job_runner import JobRunner
from app.services.model_registry_service import ModelRegistry
from app.services.preprocessing_adapter import ensure_compatible
from app.services.risk_scoring_service import RiskScoringService


def create_job(
    session: Session,
    *,
    user: User,
    payload: AnalysisCreate,
    registry: ModelRegistry,
    runner: JobRunner,
    risk: RiskScoringService,
    ip: str | None,
) -> AnalysisJob:
    dataset = dataset_repo.get_visible(session, payload.dataset_id, user)
    if dataset is None or dataset.status == DatasetStatus.DELETED:
        raise NotFoundError("Dataset not found.")
    if dataset.status != DatasetStatus.VALIDATED:
        raise ConflictError("Only validated datasets can be analysed.", code="dataset_not_ready")
    model = model_repo.get(session, payload.model_version_id)
    if model is None:
        raise NotFoundError("Model version not found.")
    if model.status != ModelStatus.APPROVED:
        raise ConflictError("Only approved model versions can be used for analysis.", code="model_not_approved")
    ensure_compatible(dataset, model, payload.requested_mode.value)
    registry.get_bundle(model)  # fail fast (503) if the artifact is missing, tampered or incompatible
    if not runner.has_capacity():
        raise ServiceUnavailableError("The analysis queue is full. Try again shortly.", code="queue_full")

    job = AnalysisJob(
        dataset_id=dataset.id,
        submitted_by=user.id,
        model_version_id=model.id,
        status=JobStatus.QUEUED.value,
        requested_mode=payload.requested_mode.value,
        input_rows=dataset.row_count,
        processed_rows=0,
        risk_policy_version=risk.version,
    )
    session.add(job)
    session.flush()
    audit_service.record(
        session,
        AuditAction.ANALYSIS_CREATE,
        actor_id=user.id,
        ip_address=ip,
        resource_type="analysis_job",
        resource_id=job.id,
        details={"dataset_id": str(dataset.id), "model": model.model_name, "version": model.version, "mode": job.requested_mode},
    )
    session.commit()
    runner.submit(job.id)
    session.refresh(job)
    return job


def get_job(session: Session, user: User, job_id: uuid.UUID) -> AnalysisJob:
    job = job_repo.get_visible(session, job_id, user)
    if job is None:
        raise NotFoundError("Analysis job not found.")
    return job


def cancel_job(session: Session, *, user: User, job_id: uuid.UUID, ip: str | None) -> AnalysisJob:
    job = get_job(session, user, job_id)
    if JobStatus(job.status) in TERMINAL_JOB_STATUSES:
        raise ConflictError(f"The job is already {job.status}.", code="job_finished")
    changed = job_repo.transition(
        session,
        job.id,
        [JobStatus.QUEUED.value, JobStatus.VALIDATING.value, JobStatus.RUNNING.value],
        JobStatus.CANCELLED.value,
        completed_at=utcnow(),
    )
    if not changed:
        session.rollback()
        raise ConflictError("The job finished before it could be cancelled.", code="job_finished")
    audit_service.record(
        session, AuditAction.ANALYSIS_CANCEL, actor_id=user.id, ip_address=ip, resource_type="analysis_job", resource_id=job.id
    )
    session.commit()
    session.refresh(job)
    return job
