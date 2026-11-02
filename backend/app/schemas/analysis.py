import uuid
from datetime import datetime
from typing import Any

from pydantic import computed_field

from app.core.constants import JobStatus
from app.ml.constants import AnalysisMode
from app.schemas.common import ApiModel, RequestModel
from app.schemas.dataset import DatasetRef
from app.schemas.model_version import ModelVersionSummary
from app.schemas.user import UserRef


class AnalysisCreate(RequestModel):
    dataset_id: uuid.UUID
    model_version_id: uuid.UUID
    requested_mode: AnalysisMode = AnalysisMode.COMBINED


class AnalysisJobRef(ApiModel):
    id: uuid.UUID
    status: JobStatus
    requested_mode: AnalysisMode
    risk_policy_version: str
    completed_at: datetime | None


class AnalysisJobRead(ApiModel):
    id: uuid.UUID
    status: JobStatus
    requested_mode: AnalysisMode
    input_rows: int | None
    processed_rows: int
    summary: dict[str, Any] | None
    risk_policy_version: str
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    dataset: DatasetRef
    model_version: ModelVersionSummary
    submitter: UserRef

    @computed_field  # type: ignore[prop-decorator]
    @property
    def progress(self) -> float:
        if self.status == JobStatus.COMPLETED:
            return 1.0
        if not self.input_rows:
            return 0.0
        return round(min(self.processed_rows / self.input_rows, 1.0), 4)
