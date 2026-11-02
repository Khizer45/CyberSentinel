"""Dataset upload, import, listing, deletion and retention (FR-03, FR-04, FR-05, FR-19, SEC-04, SEC-11)."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import AuditAction, AuditOutcome, DatasetSourceType, DatasetStatus, UserRole
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, UnprocessableError, UnsupportedMediaTypeError
from app.db.types import utcnow
from app.ml.datasets import is_supported_schema
from app.ml.errors import DatasetFormatError, FeatureSchemaError
from app.models import Dataset, User
from app.repositories import datasets as dataset_repo
from app.services import audit_service
from app.services.storage_service import UploadStorage
from app.services.validation_service import validate_dataset_file
from app.utils.text import clean_text, display_filename

logger = logging.getLogger("cybersentinel.datasets")

ALLOWED_CONTENT_TYPES = frozenset(
    {"text/csv", "application/csv", "text/plain", "application/vnd.ms-excel", "application/octet-stream", ""}
)


def _dataset_name(name: str | None, filename: str | None) -> str:
    if name and name.strip():
        return clean_text(name, max_length=180)
    if filename:
        stem = filename.rsplit(".", 1)[0]
        return clean_text(stem, max_length=180) or "dataset"
    return "dataset"


def _ingest(
    session: Session,
    settings: Settings,
    storage: UploadStorage,
    *,
    source: BinaryIO,
    filename: str | None,
    name: str | None,
    schema_version: str | None,
    owner: User | None,
    source_type: DatasetSourceType,
    actor_id: uuid.UUID | None,
    ip: str | None,
) -> Dataset:
    if schema_version and not is_supported_schema(schema_version):
        raise UnprocessableError(
            "Unsupported schema version.", code="unsupported_schema", details={"schema_version": schema_version}
        )
    stored = storage.save_stream(source, max_bytes=settings.max_upload_bytes)
    owner_id = owner.id if owner else None
    base = {
        "owner_user_id": owner_id,
        "name": _dataset_name(name, filename),
        "source_type": source_type.value,
        "original_filename": filename,
        "sha256": stored.sha256,
        "size_bytes": stored.size_bytes,
    }
    try:
        duplicate = dataset_repo.find_duplicate(session, owner_id, stored.sha256)
        if duplicate is not None:
            raise ConflictError(
                "An identical dataset has already been uploaded.",
                code="duplicate_dataset",
                details={"dataset_id": str(duplicate.id)},
            )
        validation = validate_dataset_file(storage.path_for(stored.storage_key), settings, schema_version)
    except (DatasetFormatError, FeatureSchemaError) as exc:
        storage.delete(stored.storage_key)
        rejected = Dataset(
            **base,
            status=DatasetStatus.REJECTED.value,
            validation_report={"accepted": False, "error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )
        session.add(rejected)
        session.flush()
        audit_service.record(
            session,
            AuditAction.DATASET_REJECT,
            actor_id=actor_id,
            outcome=AuditOutcome.FAILURE,
            ip_address=ip,
            resource_type="dataset",
            resource_id=rejected.id,
            details={"reason": exc.code, "size_bytes": stored.size_bytes},
        )
        session.commit()
        raise UnprocessableError(
            exc.message, code="dataset_rejected", details={"dataset_id": str(rejected.id), "reason": exc.code, **exc.details}
        ) from exc
    except Exception:
        storage.delete(stored.storage_key)
        raise

    dataset = Dataset(
        **base,
        storage_key=stored.storage_key,
        row_count=validation.row_count,
        schema_version=validation.schema.schema_version,
        has_ground_truth=validation.has_ground_truth,
        validation_report=validation.report,
        status=DatasetStatus.VALIDATED.value,
    )
    session.add(dataset)
    session.flush()
    action = AuditAction.DATASET_UPLOAD if source_type == DatasetSourceType.UPLOAD else AuditAction.DATASET_IMPORT
    audit_service.record(
        session,
        action,
        actor_id=actor_id,
        ip_address=ip,
        resource_type="dataset",
        resource_id=dataset.id,
        details={"rows": validation.row_count, "schema_version": dataset.schema_version, "size_bytes": stored.size_bytes},
    )
    session.commit()
    return dataset


def upload_dataset(
    session: Session,
    settings: Settings,
    storage: UploadStorage,
    *,
    user: User,
    source: BinaryIO,
    filename: str | None,
    content_type: str | None,
    name: str | None,
    schema_version: str | None,
    ip: str | None,
) -> Dataset:
    display_name = display_filename(filename)
    if not display_name or not display_name.lower().endswith(".csv"):
        raise UnsupportedMediaTypeError("Only .csv files are accepted.")
    if (content_type or "").split(";")[0].strip().lower() not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedMediaTypeError("Only CSV content is accepted.")
    return _ingest(
        session,
        settings,
        storage,
        source=source,
        filename=display_name,
        name=name,
        schema_version=None if schema_version in (None, "", "auto") else schema_version,
        owner=user,
        source_type=DatasetSourceType.UPLOAD,
        actor_id=user.id,
        ip=ip,
    )


def import_local_file(
    session: Session,
    settings: Settings,
    storage: UploadStorage,
    *,
    path: Path,
    name: str | None,
    schema_version: str | None,
    owner: User | None,
    source_type: DatasetSourceType,
) -> Dataset:
    """CLI import of a local CSV (e.g. a held-out test file) as a shared system dataset or for an owner."""
    if source_type == DatasetSourceType.UPLOAD:
        raise ValueError("use upload_dataset for uploads")
    with path.open("rb") as handle:
        return _ingest(
            session,
            settings,
            storage,
            source=handle,
            filename=display_filename(path.name),
            name=name,
            schema_version=schema_version,
            owner=owner,
            source_type=source_type,
            actor_id=None,
            ip=None,
        )


def get_dataset(session: Session, user: User, dataset_id: uuid.UUID) -> Dataset:
    dataset = dataset_repo.get_visible(session, dataset_id, user)
    if dataset is None:
        raise NotFoundError("Dataset not found.")
    return dataset


def delete_dataset(session: Session, storage: UploadStorage, *, user: User, dataset_id: uuid.UUID, ip: str | None) -> None:
    """Soft-delete: metadata is kept for traceability; the stored file is removed (FR-19)."""
    dataset = get_dataset(session, user, dataset_id)
    if dataset.status == DatasetStatus.DELETED:
        raise NotFoundError("Dataset not found.")
    if user.role != UserRole.ADMIN and dataset.owner_user_id != user.id:
        audit_service.record_independent(
            AuditAction.ACCESS_DENIED,
            actor_id=user.id,
            outcome=AuditOutcome.DENIED,
            ip_address=ip,
            resource_type="dataset",
            resource_id=dataset.id,
            details={"operation": "delete"},
        )
        raise PermissionDeniedError("Only the owner or an administrator can delete this dataset.")
    if dataset_repo.active_job_count(session, dataset.id):
        raise ConflictError("The dataset is used by a queued or running analysis job.", code="dataset_in_use")
    storage.delete(dataset.storage_key)
    dataset.storage_key = None
    dataset.status = DatasetStatus.DELETED.value
    dataset.deleted_at = utcnow()
    dataset.deleted_by = user.id
    audit_service.record(
        session, AuditAction.DATASET_DELETE, actor_id=user.id, ip_address=ip, resource_type="dataset", resource_id=dataset.id
    )
    session.commit()


def purge_expired(session: Session, settings: Settings, storage: UploadStorage, *, older_than_days: int) -> int:
    """Retention job (CLI): soft-delete validated datasets older than the cutoff that no active job uses."""
    cutoff = utcnow() - timedelta(days=older_than_days)
    purged = 0
    for dataset in dataset_repo.expired_datasets(session, cutoff):
        if dataset_repo.active_job_count(session, dataset.id):
            continue
        storage.delete(dataset.storage_key)
        dataset.storage_key = None
        dataset.status = DatasetStatus.DELETED.value
        dataset.deleted_at = utcnow()
        audit_service.record(
            session,
            AuditAction.DATASET_PURGE,
            actor_id=None,
            resource_type="dataset",
            resource_id=dataset.id,
            details={"retention_days": older_than_days},
        )
        purged += 1
    session.commit()
    return purged
