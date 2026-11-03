"""System information and the active risk policy (read-only)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.api.deps import AnyUser, Risk, SettingsDep
from app.ml.datasets import list_schemas
from app.ml.risk import RiskPolicy
from app.schemas.system import SystemInfo

router = APIRouter(tags=["system"])


class RiskPolicyResponse(BaseModel):
    policy: RiskPolicy
    sha256: str


@router.get("/risk-policy", response_model=RiskPolicyResponse)
def risk_policy(user: AnyUser, risk: Risk) -> RiskPolicyResponse:
    """The versioned policy that converts model outputs into 0–100 policy risk scores and bands."""
    return RiskPolicyResponse(policy=risk.policy, sha256=risk.policy_sha256)


@router.get("/system/info", response_model=SystemInfo)
def system_info(user: AnyUser, settings: SettingsDep, risk: Risk) -> SystemInfo:
    return SystemInfo(
        app_name=settings.app_name,
        version=__version__,
        environment=settings.app_env,
        risk_policy_version=risk.version,
        supported_schemas=[s.schema_version for s in list_schemas()],
        limits={
            "max_upload_mb": settings.max_upload_mb,
            "max_upload_rows": settings.max_upload_rows,
            "quick_analysis_max_records": settings.quick_analysis_max_records,
            "export_max_rows": settings.export_max_rows,
            "page_size_max": 100,
            "access_token_ttl_minutes": settings.access_token_ttl_minutes,
        },
        explain_scope=settings.explain_scope,
    )
