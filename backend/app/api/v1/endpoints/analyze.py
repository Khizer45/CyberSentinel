"""Synchronous, bounded quick analysis (PRD analyze/record and analyze/batch). Results are not persisted."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import AnalystUser, ClientIP, DbSession, Registry, Risk, SettingsDep, rate_limit
from app.schemas.common import ERROR_RESPONSES
from app.schemas.quick_analysis import QuickAnalysisResponse, QuickBatchRequest, QuickRecordRequest
from app.services import prediction_service

router = APIRouter(
    prefix="/analyze",
    tags=["quick analysis"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(rate_limit("quick", "rate_limit_quick_analysis", "user"))],
)


@router.post("/record", response_model=QuickAnalysisResponse)
def analyze_record(
    payload: QuickRecordRequest,
    user: AnalystUser,
    db: DbSession,
    settings: SettingsDep,
    registry: Registry,
    risk: Risk,
    ip: ClientIP,
) -> QuickAnalysisResponse:
    """Score one flow record (feature names may use raw or canonical spellings)."""
    return prediction_service.quick_analyze(
        db,
        settings,
        user=user,
        model_version_id=payload.model_version_id,
        mode=payload.mode,
        records=[payload.features],
        registry=registry,
        risk=risk,
        ip=ip,
    )


@router.post("/batch", response_model=QuickAnalysisResponse)
def analyze_batch(
    payload: QuickBatchRequest,
    user: AnalystUser,
    db: DbSession,
    settings: SettingsDep,
    registry: Registry,
    risk: Risk,
    ip: ClientIP,
) -> QuickAnalysisResponse:
    """Score up to ``QUICK_ANALYSIS_MAX_RECORDS`` records synchronously."""
    return prediction_service.quick_analyze(
        db,
        settings,
        user=user,
        model_version_id=payload.model_version_id,
        mode=payload.mode,
        records=[r.features for r in payload.records],
        registry=registry,
        risk=risk,
        ip=ip,
    )
