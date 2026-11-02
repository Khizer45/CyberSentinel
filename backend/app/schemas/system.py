from typing import Any, Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "unavailable"]
    version: str
    uptime_seconds: float
    checks: dict[str, str]


class SystemInfo(BaseModel):
    app_name: str
    version: str
    environment: str
    risk_policy_version: str
    supported_schemas: list[str]
    limits: dict[str, Any]
    explain_scope: str
