"""Version 1 API router (``/api/v1``)."""

from fastapi import APIRouter, Depends

from app.api.deps import rate_limit
from app.api.v1.endpoints import (
    admin_users,
    alerts,
    analyses,
    analyze,
    audit_logs,
    auth,
    dataset_schemas,
    datasets,
    experiments,
    health,
    metrics,
    models,
    predictions,
    reports,
    system,
)

api_router = APIRouter(dependencies=[Depends(rate_limit("default", "rate_limit_default"))])
for module in (
    health,
    auth,
    admin_users,
    dataset_schemas,
    datasets,
    models,
    analyses,
    predictions,
    alerts,
    analyze,
    metrics,
    reports,
    experiments,
    audit_logs,
    system,
):
    api_router.include_router(module.router)
