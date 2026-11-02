import uuid
from typing import Annotated

from pydantic import BaseModel, Field, StrictFloat, StrictInt, StrictStr

from app.ml.constants import AnalysisMode
from app.schemas.common import RequestModel
from app.schemas.model_version import ModelVersionSummary
from app.schemas.prediction import Explanation

# Strict types: JSON booleans are rejected instead of being coerced to 0/1 (Security Requirements 5.3).
FeatureValue = StrictInt | StrictFloat | StrictStr | None
FeatureMap = Annotated[dict[str, FeatureValue], Field(min_length=1, max_length=256)]


class QuickRecord(RequestModel):
    features: FeatureMap


class QuickRecordRequest(RequestModel):
    model_version_id: uuid.UUID
    mode: AnalysisMode = AnalysisMode.COMBINED
    features: FeatureMap


class QuickBatchRequest(RequestModel):
    model_version_id: uuid.UUID
    mode: AnalysisMode = AnalysisMode.COMBINED
    records: list[QuickRecord] = Field(min_length=1, max_length=10_000)


class QuickResult(BaseModel):
    index: int
    predicted_label: str
    top_label: str | None
    label_confidence: float | None
    classifier_score: float | None
    probability: float | None
    scores_calibrated: bool
    anomaly_score: float | None
    is_anomaly: bool | None
    risk_score: float
    risk_band: str
    is_alert: bool
    explanation: Explanation | None


class QuickAnalysisResponse(BaseModel):
    model: ModelVersionSummary
    mode: AnalysisMode
    risk_policy_version: str
    results: list[QuickResult]
    ignored_features: list[str]
    warnings: list[str] = []
    persisted: bool = False
    disclaimer: str = (
        "Decision-support output only. Scores are not proof of compromise; risk scores are policy scores, "
        "not probabilities. Quick analyses are not stored — upload a dataset for reviewable results."
    )
