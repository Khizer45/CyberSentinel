import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.core.constants import DatasetSourceType, DatasetStatus
from app.schemas.common import ApiModel
from app.schemas.user import UserRef


class DatasetRef(ApiModel):
    id: uuid.UUID
    name: str
    schema_version: str | None


class DatasetRead(ApiModel):
    id: uuid.UUID
    name: str
    source_type: DatasetSourceType
    original_filename: str | None
    sha256: str | None
    size_bytes: int | None
    row_count: int | None
    schema_version: str | None
    has_ground_truth: bool
    status: DatasetStatus
    validation_report: dict[str, Any] | None
    owner: UserRef | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class FeatureSpecRead(BaseModel):
    name: str
    dtype: str
    description: str = ""


class DatasetSchemaRead(BaseModel):
    schema_version: str
    family: str
    display_name: str
    source: str
    features: list[FeatureSpecRead]
    label_columns: list[str]
    identifier_columns: list[str]
    notes: list[str]
