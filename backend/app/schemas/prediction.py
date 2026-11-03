import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.constants import AlertStatus, Disposition
from app.schemas.analysis import AnalysisJobRef
from app.schemas.common import ApiModel
from app.schemas.dataset import DatasetRef
from app.schemas.model_version import ModelVersionSummary
from app.schemas.user import UserRef


class _Open(BaseModel):
    """Explanation documents are versioned JSON; tolerate additive fields."""

    model_config = ConfigDict(extra="allow")


class TopFeature(_Open):
    feature: str
    value: float | str | None = None
    contribution: float
    direction: str
    baseline: float | str | None = None


class ReasonCode(_Open):
    code: str
    feature: str = ""
    text: str


class ClassScore(_Open):
    label: str
    score: float


class AnomalyInfo(_Open):
    score: float
    threshold: float
    is_anomaly: bool
    score_direction: str


class Explanation(_Open):
    method: str
    method_family: str
    target_label: str
    units: str
    top_features: list[TopFeature] = []
    reason_codes: list[ReasonCode] = []
    anomaly: AnomalyInfo | None = None
    class_scores: list[ClassScore] | None = None
    scores_calibrated: bool = False
    fallback_reason: str | None = None
    disclaimer: str
    risk: dict[str, Any] | None = None


class ReviewRead(ApiModel):
    id: uuid.UUID
    prediction_id: uuid.UUID
    disposition: Disposition
    notes: str | None
    reviewer: UserRef
    created_at: datetime


class PredictionRead(ApiModel):
    id: uuid.UUID
    analysis_job_id: uuid.UUID
    record_index: int
    predicted_label: str
    probability: float | None
    classifier_score: float | None
    anomaly_score: float | None
    is_anomaly: bool | None
    risk_score: float | None
    risk_band: str | None
    is_alert: bool
    true_label: str | None
    created_at: datetime


class PredictionDetail(PredictionRead):
    explanation: Explanation | None
    flow_context: dict[str, Any] | None
    job: AnalysisJobRef
    dataset: DatasetRef
    model_version: ModelVersionSummary
    reviews: list[ReviewRead]
    alert_status: AlertStatus | None
    scores_calibrated: bool
