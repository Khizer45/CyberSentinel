"""Prediction detail views and synchronous quick analysis (UC1, PRD analyze/record and analyze/batch)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import AuditAction, ModelStatus
from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.ml.constants import AnalysisMode
from app.ml.datasets import get_schema
from app.ml.inference import InferenceEngine
from app.models import AnalysisJob, Prediction, User
from app.repositories import model_versions as model_repo
from app.repositories import predictions as prediction_repo
from app.schemas.analysis import AnalysisJobRef
from app.schemas.dataset import DatasetRef
from app.schemas.model_version import ModelVersionSummary
from app.schemas.prediction import Explanation, PredictionDetail, ReviewRead
from app.schemas.quick_analysis import QuickAnalysisResponse, QuickResult
from app.services import audit_service
from app.services.explanation_service import explain
from app.services.model_registry_service import ModelRegistry
from app.services.risk_scoring_service import RiskScoringService
from app.services.validation_service import records_to_frame


def get_visible(session: Session, user: User, prediction_id: uuid.UUID) -> tuple[Prediction, AnalysisJob]:
    found = prediction_repo.get_visible_prediction(session, prediction_id, user)
    if found is None:
        raise NotFoundError("Prediction not found.")
    return found


def build_detail(session: Session, prediction: Prediction, job: AnalysisJob) -> PredictionDetail:
    reviews = prediction_repo.reviews_for(session, prediction.id)
    status = None
    if prediction.is_alert:
        status = prediction_repo.status_from_disposition(reviews[0].disposition if reviews else None)
    explanation = Explanation.model_validate(prediction.explanation) if prediction.explanation else None
    return PredictionDetail(
        id=prediction.id,
        analysis_job_id=prediction.analysis_job_id,
        record_index=prediction.record_index,
        predicted_label=prediction.predicted_label,
        probability=prediction.probability,
        classifier_score=prediction.classifier_score,
        anomaly_score=prediction.anomaly_score,
        is_anomaly=prediction.is_anomaly,
        risk_score=prediction.risk_score,
        risk_band=prediction.risk_band,
        is_alert=prediction.is_alert,
        true_label=prediction.true_label,
        created_at=prediction.created_at,
        explanation=explanation,
        flow_context=prediction.flow_context,
        job=AnalysisJobRef.model_validate(job),
        dataset=DatasetRef.model_validate(job.dataset),
        model_version=ModelVersionSummary.model_validate(job.model_version),
        reviews=[ReviewRead.model_validate(r) for r in reviews],
        alert_status=status,
        scores_calibrated=bool(job.model_version.probability_calibrated),
    )


def quick_analyze(
    session: Session,
    settings: Settings,
    *,
    user: User,
    model_version_id: uuid.UUID,
    mode: AnalysisMode,
    records: list[dict[str, Any]],
    registry: ModelRegistry,
    risk: RiskScoringService,
    ip: str | None,
) -> QuickAnalysisResponse:
    if len(records) > settings.quick_analysis_max_records:
        raise UnprocessableError(
            f"At most {settings.quick_analysis_max_records} records can be analysed synchronously; upload a dataset instead.",
            code="too_many_records",
        )
    model = model_repo.get(session, model_version_id)
    if model is None:
        raise NotFoundError("Model version not found.")
    if model.status != ModelStatus.APPROVED:
        raise ConflictError("Only approved model versions can be used for analysis.", code="model_not_approved")
    bundle = registry.get_bundle(model)
    engine = InferenceEngine(bundle)
    mode = engine.check_mode(mode)
    schema = get_schema(model.feature_schema_version)
    frame, ignored, warnings = records_to_frame(records, bundle, schema)
    output = engine.predict(frame, mode, keep_transformed=True)
    scores = risk.score(bundle, output)
    explanations = explain(
        bundle, engine.prepare(frame), output, list(range(output.size)), scores, risk.policy, top_k=settings.explain_top_k
    )
    calibrated = bool(bundle.manifest.components.classifier and bundle.manifest.components.classifier.probability_calibrated)
    results = []
    for i in range(output.size):
        results.append(
            QuickResult(
                index=i,
                predicted_label=str(output.predicted_label[i]),
                top_label=str(output.top_label[i]) if output.top_label is not None else None,
                label_confidence=float(output.label_confidence[i]) if output.label_confidence is not None else None,
                classifier_score=float(output.classifier_score[i]) if output.classifier_score is not None else None,
                probability=float(output.probability[i]) if output.probability is not None else None,
                scores_calibrated=calibrated,
                anomaly_score=float(output.anomaly_score[i]) if output.anomaly_score is not None else None,
                is_anomaly=bool(output.is_anomaly[i]) if output.is_anomaly is not None else None,
                risk_score=float(scores.score[i]),
                risk_band=str(scores.band[i]),
                is_alert=bool(scores.is_alert[i]),
                explanation=Explanation.model_validate(explanations[i]) if i in explanations else None,
            )
        )
    audit_service.record(
        session,
        AuditAction.QUICK_ANALYSIS,
        actor_id=user.id,
        ip_address=ip,
        resource_type="model_version",
        resource_id=model.id,
        details={
            "records": output.size,
            "alerts": int(scores.is_alert.sum()),
            "mode": mode.value,
            "model": model.model_name,
            "version": model.version,
        },
    )
    session.commit()
    return QuickAnalysisResponse(
        model=ModelVersionSummary.model_validate(model),
        mode=mode,
        risk_policy_version=risk.version,
        results=results,
        ignored_features=ignored,
        warnings=warnings,
    )
