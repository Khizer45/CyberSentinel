import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.constants import AlertStatus, Disposition


class AlertRead(BaseModel):
    id: uuid.UUID  # the prediction id
    analysis_job_id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_name: str
    model_name: str
    model_version: str
    record_index: int
    predicted_label: str
    risk_score: float | None
    risk_band: str | None
    anomaly_score: float | None
    is_anomaly: bool | None
    classifier_score: float | None
    probability: float | None
    status: AlertStatus
    latest_disposition: Disposition | None
    review_count: int
    created_at: datetime
