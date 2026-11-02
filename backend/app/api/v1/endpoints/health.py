"""Health endpoints (FR-20). Public, minimal and free of internal details."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db.session import get_database
from app.schemas.system import HealthResponse
from app.services import health_service

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
def health(request: Request) -> JSONResponse:
    result = health_service.check(get_database(), request.app.state.settings, getattr(request.app.state, "runner", None))
    return JSONResponse(status_code=503 if result.status == "unavailable" else 200, content=result.model_dump())


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}
