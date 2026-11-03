"""Model metadata and governance (FR-06). Artifact locations are never returned."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, AnyUser, ClientIP, DbSession, Registry
from app.core.constants import AuditAction, AuditOutcome, ModelStatus, UserRole
from app.models import ModelVersion
from app.repositories import model_versions as model_repo
from app.schemas.common import ERROR_RESPONSES
from app.schemas.model_version import ModelStatusUpdate, ModelVerifyResult, ModelVersionRead, VerificationCheck
from app.services import audit_service, model_registry_service

router = APIRouter(prefix="/models", tags=["models"], responses=ERROR_RESPONSES)


@router.get("", response_model=list[ModelVersionRead])
def list_models(
    user: AnyUser,
    db: DbSession,
    status: Annotated[list[ModelStatus] | None, Query()] = None,
    dataset_family: Annotated[str | None, Query(max_length=40)] = None,
) -> list[dict[str, Any]]:
    """Approved model versions; administrators may also list draft/retired/revoked versions."""
    if user.role == UserRole.ADMIN:
        statuses = [s.value for s in status] if status else None
    else:
        statuses = [ModelStatus.APPROVED.value]
    return [model_registry_service.to_read_dict(m) for m in model_repo.list_models(db, statuses=statuses, family=dataset_family)]


@router.get("/{model_version_id}", response_model=ModelVersionRead)
def get_model(model_version_id: uuid.UUID, user: AnyUser, db: DbSession) -> dict[str, Any]:
    return model_registry_service.to_read_dict(model_registry_service.get_model(db, model_version_id, user=user))


@router.patch("/{model_version_id}/status", response_model=ModelVersionRead)
def change_status(
    model_version_id: uuid.UUID, payload: ModelStatusUpdate, admin: AdminUser, db: DbSession, registry: Registry, ip: ClientIP
) -> dict[str, Any]:
    """Approve (after verification), retire or revoke a model version."""
    model: ModelVersion = model_registry_service.change_status(
        db, registry, actor=admin, model_version_id=model_version_id, new_status=payload.status, reason=payload.reason, ip=ip
    )
    return model_registry_service.to_read_dict(model)


@router.post("/{model_version_id}/verify", response_model=ModelVerifyResult)
def verify_model(
    model_version_id: uuid.UUID, admin: AdminUser, db: DbSession, registry: Registry, ip: ClientIP
) -> ModelVerifyResult:
    """Re-verify integrity, compatibility and golden parity of a bundle (uncached)."""
    model = model_registry_service.get_model(db, model_version_id)
    checks = registry.verify(model)
    verified = all(c["passed"] for c in checks)
    audit_service.record(
        db,
        AuditAction.MODEL_VERIFY,
        actor_id=admin.id,
        ip_address=ip,
        resource_type="model_version",
        resource_id=model.id,
        outcome=AuditOutcome.SUCCESS if verified else AuditOutcome.FAILURE,
        details={"verified": verified},
    )
    db.commit()
    return ModelVerifyResult(model_version_id=model.id, verified=verified, checks=[VerificationCheck(**c) for c in checks])
