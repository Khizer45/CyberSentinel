from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, Select, func, select, update
from sqlalchemy.orm import Session

from app.core.constants import JobStatus, UserRole
from app.db.types import utcnow
from app.models import AnalysisJob, User
from app.repositories.base import order_by_allowlisted, paginate_scalars

SORTS = {"created_at": AnalysisJob.created_at, "status": AnalysisJob.status, "completed_at": AnalysisJob.completed_at}


def visible(stmt: Select, user: User) -> Select:  # type: ignore[type-arg]
    return stmt if user.role == UserRole.ADMIN else stmt.where(AnalysisJob.submitted_by == user.id)


def get_visible(session: Session, job_id: uuid.UUID, user: User) -> AnalysisJob | None:
    return session.scalar(visible(select(AnalysisJob).where(AnalysisJob.id == job_id), user))


def list_jobs(
    session: Session,
    user: User,
    *,
    status: str | None,
    dataset_id: uuid.UUID | None,
    model_version_id: uuid.UUID | None,
    sort: str,
    limit: int,
    offset: int,
) -> tuple[Sequence[AnalysisJob], int]:
    stmt = visible(select(AnalysisJob), user)
    if status:
        stmt = stmt.where(AnalysisJob.status == status)
    if dataset_id:
        stmt = stmt.where(AnalysisJob.dataset_id == dataset_id)
    if model_version_id:
        stmt = stmt.where(AnalysisJob.model_version_id == model_version_id)
    stmt = stmt.order_by(*order_by_allowlisted(sort, SORTS), AnalysisJob.id)
    return paginate_scalars(session, stmt, limit=limit, offset=offset)


def transition(session: Session, job_id: uuid.UUID, from_statuses: Sequence[str], to_status: str, **values: object) -> bool:
    """Atomic compare-and-set status change; returns True if this caller won the transition."""
    now = utcnow()
    result = session.execute(
        update(AnalysisJob)
        .where(AnalysisJob.id == job_id, AnalysisJob.status.in_(list(from_statuses)))
        .values(status=to_status, updated_at=now, **values)
        .execution_options(synchronize_session=False)
    )
    return cast(CursorResult[Any], result).rowcount == 1


def current_status(session: Session, job_id: uuid.UUID) -> str | None:
    return session.scalar(select(AnalysisJob.status).where(AnalysisJob.id == job_id))


def stale_running(session: Session, older_than: datetime) -> Sequence[uuid.UUID]:
    return session.scalars(
        select(AnalysisJob.id).where(
            AnalysisJob.status.in_([JobStatus.VALIDATING.value, JobStatus.RUNNING.value]), AnalysisJob.updated_at < older_than
        )
    ).all()


def queued_ids(session: Session, limit: int) -> Sequence[uuid.UUID]:
    return session.scalars(
        select(AnalysisJob.id).where(AnalysisJob.status == JobStatus.QUEUED).order_by(AnalysisJob.created_at).limit(limit)
    ).all()


def status_counts(session: Session) -> dict[str, int]:
    rows = session.execute(select(AnalysisJob.status, func.count()).group_by(AnalysisJob.status)).all()
    return {str(status): int(count) for status, count in rows}
