from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import ACTIVE_JOB_STATUSES, DatasetStatus, UserRole
from app.models import AnalysisJob, Dataset, User
from app.repositories.base import order_by_allowlisted, paginate_scalars
from app.utils.text import escape_like

SORTS = {"created_at": Dataset.created_at, "name": Dataset.name, "row_count": Dataset.row_count, "status": Dataset.status}


def visible(stmt: Select, user: User) -> Select:  # type: ignore[type-arg]
    """Admins see everything; analysts see their own datasets and shared system datasets (owner IS NULL)."""
    if user.role == UserRole.ADMIN:
        return stmt
    return stmt.where(or_(Dataset.owner_user_id == user.id, Dataset.owner_user_id.is_(None)))


def get_visible(session: Session, dataset_id: uuid.UUID, user: User) -> Dataset | None:
    return session.scalar(visible(select(Dataset).where(Dataset.id == dataset_id), user))


def list_datasets(
    session: Session,
    user: User,
    *,
    status: str | None,
    schema_version: str | None,
    q: str | None,
    include_deleted: bool,
    sort: str,
    limit: int,
    offset: int,
) -> tuple[Sequence[Dataset], int]:
    stmt = visible(select(Dataset), user)
    if status:
        stmt = stmt.where(Dataset.status == status)
    elif not include_deleted:
        stmt = stmt.where(Dataset.status != DatasetStatus.DELETED)
    if schema_version:
        stmt = stmt.where(Dataset.schema_version == schema_version)
    if q:
        stmt = stmt.where(Dataset.name.ilike(f"%{escape_like(q)}%", escape="\\"))
    stmt = stmt.order_by(*order_by_allowlisted(sort, SORTS), Dataset.id)
    return paginate_scalars(session, stmt, limit=limit, offset=offset)


def find_duplicate(session: Session, owner_id: uuid.UUID | None, sha256: str) -> Dataset | None:
    stmt = select(Dataset).where(Dataset.sha256 == sha256, Dataset.status == DatasetStatus.VALIDATED)
    stmt = stmt.where(Dataset.owner_user_id == owner_id) if owner_id else stmt.where(Dataset.owner_user_id.is_(None))
    return session.scalar(stmt.limit(1))


def active_job_count(session: Session, dataset_id: uuid.UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(AnalysisJob)
            .where(AnalysisJob.dataset_id == dataset_id, AnalysisJob.status.in_([s.value for s in ACTIVE_JOB_STATUSES]))
        )
        or 0
    )


def expired_datasets(session: Session, older_than: datetime) -> Sequence[Dataset]:
    return session.scalars(
        select(Dataset).where(Dataset.status == DatasetStatus.VALIDATED, Dataset.created_at < older_than)
    ).all()


def count_active(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(Dataset).where(Dataset.status == DatasetStatus.VALIDATED)) or 0)
