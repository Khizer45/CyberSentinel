"""CyberSentinel FastAPI application factory.

Run locally (from ``backend/``)::

    uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log

``app`` is created lazily on first access so that importing this module (e.g. in tests) has no side effects.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.rate_limit import SlidingWindowLimiter
from app.db.session import Database, build_engine, init_database
from app.services.experiment_service import ExperimentStore
from app.services.job_runner import JobRunner
from app.services.model_registry_service import ModelRegistry
from app.services.risk_scoring_service import RiskScoringService
from app.services.storage_service import UploadStorage

logger = logging.getLogger("cybersentinel")

API_PREFIX = "/api/v1"
DESCRIPTION = """
ML-based network threat detection: dataset upload and validation, asynchronous analysis jobs, predictions with
risk scores and explanations, alert review, analytics and audit.

**Score semantics.** `probability` is only present for calibrated models; `classifier_score` is an uncalibrated
model score; `anomaly_score` is higher for more unusual flows (not necessarily malicious); `risk_score` is a
versioned 0–100 *policy* score, not a probability. Model outputs are decision support, not proof of compromise.

Authenticate with `POST /api/v1/auth/login` and send the access token as `Authorization: Bearer <token>`.
"""


def create_app(settings: Settings | None = None, *, database: Database | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_logs=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = database or Database(
            build_engine(
                settings.database_url.get_secret_value(),
                echo=settings.db_echo,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_timeout=settings.db_pool_timeout_seconds,
                statement_timeout_ms=settings.db_statement_timeout_ms,
            )
        )
        init_database(db)
        risk = RiskScoringService(settings.risk_policy_path)
        registry = ModelRegistry(settings)
        storage = UploadStorage(settings.upload_dir)
        runner = JobRunner(db, settings, registry, risk, storage, inline=settings.job_execution == "inline")
        app.state.database = db
        app.state.risk = risk
        app.state.registry = registry
        app.state.storage = storage
        app.state.runner = runner
        app.state.experiments = ExperimentStore(settings.experiments_dir)  # type: ignore[arg-type]
        runner.start()
        if settings.model_preload:
            _preload_models(db, registry)
        logger.info(
            "CyberSentinel API started",
            extra={"version": __version__, "environment": settings.app_env, "risk_policy_version": risk.version},
        )
        try:
            yield
        finally:
            runner.shutdown()
            if database is None:
                db.dispose()
            logger.info("CyberSentinel API stopped")

    docs = settings.enable_api_docs
    app = FastAPI(
        title="CyberSentinel API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.rate_limiter = SlidingWindowLimiter()
    register_exception_handlers(app)
    app.include_router(api_router, prefix=API_PREFIX)

    # Middleware: the last added is the outermost.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After", "Content-Disposition", "X-Export-Truncated", "Location"],
        max_age=600,
    )
    app.add_middleware(
        BodySizeLimitMiddleware,
        default_limit=settings.max_json_body_bytes,
        upload_limit=settings.max_upload_bytes + 64 * 1024,  # multipart overhead
        upload_paths=(f"{API_PREFIX}/datasets",),
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.hsts_enabled)
    app.add_middleware(RequestContextMiddleware)
    return app


def _preload_models(db: Database, registry: ModelRegistry) -> None:
    from app.repositories import model_versions as model_repo

    with db.session() as session:
        for model in model_repo.list_models(session, statuses=["approved"]):
            try:
                registry.get_bundle(model)
            except Exception:  # noqa: BLE001 - logged by the registry; the API keeps running (fail closed per model)
                logger.warning(
                    "approved model could not be preloaded", extra={"model": model.model_name, "version": model.version}
                )


def __getattr__(name: str) -> Any:
    """Lazily build ``app`` for ``uvicorn app.main:app``."""
    if name == "app":
        instance = create_app()
        globals()["app"] = instance
        return instance
    raise AttributeError(name)
