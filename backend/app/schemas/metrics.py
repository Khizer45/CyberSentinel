import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class MetricsWindow(BaseModel):
    date_from: datetime | None
    date_to: datetime | None


class MetricsSummary(BaseModel):
    window: MetricsWindow
    scope: Literal["organization"] = "organization"
    total_records: int
    benign_count: int
    malicious_count: int
    needs_review_count: int
    unclassified_count: int
    anomaly_count: int
    alert_count: int
    open_alert_count: int
    high_risk_count: int
    label_distribution: dict[str, int]
    risk_band_distribution: dict[str, int]
    jobs_by_status: dict[str, int]
    completed_jobs: int
    active_datasets: int
    approved_models: int


class TrendPoint(BaseModel):
    bucket: str
    records: int
    malicious: int
    anomalies: int
    alerts: int


class TrendsResponse(BaseModel):
    bucket: Literal["day", "hour"]
    points: list[TrendPoint]


class ModelMetricsRead(BaseModel):
    model_version_id: uuid.UUID
    model_name: str
    version: str
    dataset_family: str
    status: str
    metrics: dict[str, Any] | None
