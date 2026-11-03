import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.constants import ModelStatus
from app.ml.constants import ModelType
from app.schemas.common import ApiModel, RequestModel


class ModelVersionSummary(ApiModel):
    id: uuid.UUID
    model_name: str
    version: str
    model_type: ModelType


class ModelVersionRead(ApiModel):
    """Model metadata. The artifact location is deliberately not part of this schema (FR-06)."""

    id: uuid.UUID
    model_name: str
    version: str
    model_type: ModelType
    task: str | None
    dataset_family: str
    feature_schema_version: str
    preprocessing_version: str
    description: str | None
    status: ModelStatus
    status_reason: str | None
    probability_calibrated: bool
    explanation_method: str | None
    label_map: dict[str, Any] | None
    threshold_config: dict[str, Any] | None
    metrics: dict[str, Any] | None
    supported_modes: list[str]
    artifact_sha256: str
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ModelStatusUpdate(RequestModel):
    status: ModelStatus
    reason: str | None = Field(default=None, max_length=500)


class VerificationCheck(BaseModel):
    name: str
    passed: bool
    detail: str | None = None


class ModelVerifyResult(BaseModel):
    model_version_id: uuid.UUID
    verified: bool
    checks: list[VerificationCheck]
