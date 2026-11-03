from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import ModelStatus
from app.models import ModelVersion


def get(session: Session, model_version_id: uuid.UUID) -> ModelVersion | None:
    return session.get(ModelVersion, model_version_id)


def get_by_name_version(session: Session, model_name: str, version: str) -> ModelVersion | None:
    return session.scalar(select(ModelVersion).where(ModelVersion.model_name == model_name, ModelVersion.version == version))


def list_models(session: Session, *, statuses: Sequence[str] | None, family: str | None = None) -> Sequence[ModelVersion]:
    stmt = select(ModelVersion)
    if statuses:
        stmt = stmt.where(ModelVersion.status.in_(list(statuses)))
    if family:
        stmt = stmt.where(ModelVersion.dataset_family == family)
    return session.scalars(stmt.order_by(ModelVersion.model_name, ModelVersion.created_at.desc())).all()


def count_approved(session: Session) -> int:
    return int(
        session.scalar(select(func.count()).select_from(ModelVersion).where(ModelVersion.status == ModelStatus.APPROVED)) or 0
    )
