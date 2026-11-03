"""Dataset upload and management (FR-03, FR-04, FR-05, FR-19)."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.api.deps import AnalystUser, ClientIP, DbSession, Pagination, SettingsDep, Storage, rate_limit
from app.core.constants import DatasetStatus
from app.models import Dataset
from app.repositories import datasets as dataset_repo
from app.schemas.common import ERROR_RESPONSES, ErrorResponse, Page
from app.schemas.dataset import DatasetRead
from app.services import dataset_service

router = APIRouter(prefix="/datasets", tags=["datasets"], responses=ERROR_RESPONSES)
DatasetSort = Literal["created_at", "-created_at", "name", "-name", "row_count", "-row_count", "status", "-status"]


@router.post(
    "",
    response_model=DatasetRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("upload", "rate_limit_upload", "user"))],
    responses={
        409: {"model": ErrorResponse, "description": "Identical dataset already uploaded"},
        413: {"model": ErrorResponse, "description": "File exceeds MAX_UPLOAD_MB"},
        415: {"model": ErrorResponse, "description": "Not a CSV file"},
        422: {"model": ErrorResponse, "description": "Dataset rejected by validation (details include the report)"},
    },
)
def upload_dataset(
    user: AnalystUser,
    db: DbSession,
    settings: SettingsDep,
    storage: Storage,
    ip: ClientIP,
    file: Annotated[UploadFile, File(description="CSV file of network-flow records")],
    name: Annotated[str | None, Form(max_length=180)] = None,
    schema_version: Annotated[
        str | None, Form(max_length=40, description="'auto' (default) or a supported schema version")
    ] = None,
) -> Dataset:
    """Upload and fully validate a CSV dataset. Rejected files are deleted; their validation report is kept."""
    return dataset_service.upload_dataset(
        db,
        settings,
        storage,
        user=user,
        source=file.file,
        filename=file.filename,
        content_type=file.content_type,
        name=name,
        schema_version=schema_version,
        ip=ip,
    )


@router.get("", response_model=Page[DatasetRead])
def list_datasets(
    user: AnalystUser,
    db: DbSession,
    page: Pagination,
    status_filter: Annotated[DatasetStatus | None, Query(alias="status")] = None,
    schema_version: Annotated[str | None, Query(max_length=40)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    include_deleted: bool = False,
    sort: DatasetSort = "-created_at",
) -> Page[DatasetRead]:
    items, total = dataset_repo.list_datasets(
        db,
        user,
        status=status_filter,
        schema_version=schema_version,
        q=q,
        include_deleted=include_deleted,
        sort=sort,
        limit=page.limit,
        offset=page.offset,
    )
    return Page[DatasetRead](
        items=[DatasetRead.model_validate(d) for d in items], total=total, limit=page.limit, offset=page.offset
    )


@router.get("/{dataset_id}", response_model=DatasetRead)
def get_dataset(dataset_id: uuid.UUID, user: AnalystUser, db: DbSession) -> Dataset:
    return dataset_service.get_dataset(db, user, dataset_id)


@router.delete(
    "/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={409: {"model": ErrorResponse, "description": "Dataset used by an active job"}},
)
def delete_dataset(dataset_id: uuid.UUID, user: AnalystUser, db: DbSession, storage: Storage, ip: ClientIP) -> Response:
    dataset_service.delete_dataset(db, storage, user=user, dataset_id=dataset_id, ip=ip)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
