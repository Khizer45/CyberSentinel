"""Application-level vocabularies (status fields, roles, audit actions).

Values mirror the CHECK constraints in the ERD and in the Alembic migration. The ML-level
vocabularies (risk bands, analysis modes, model types) live in :mod:`app.ml.constants` and are
re-exported here for convenience.
"""

from __future__ import annotations

from enum import StrEnum

from app.ml.constants import AnalysisMode, ModelType, RiskBand  # noqa: F401  (re-export)


class UserRole(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class DatasetSourceType(StrEnum):
    UPLOAD = "upload"
    IMPORT = "import"
    SAMPLE = "sample"


class DatasetStatus(StrEnum):
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"
    DELETED = "deleted"


class ModelStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    RETIRED = "retired"
    REVOKED = "revoked"


# Allowed model status transitions. ``revoked`` is terminal: a revoked artifact is never loaded again.
MODEL_STATUS_TRANSITIONS: dict[ModelStatus, frozenset[ModelStatus]] = {
    ModelStatus.DRAFT: frozenset({ModelStatus.APPROVED, ModelStatus.REVOKED}),
    ModelStatus.APPROVED: frozenset({ModelStatus.RETIRED, ModelStatus.REVOKED}),
    ModelStatus.RETIRED: frozenset({ModelStatus.APPROVED, ModelStatus.REVOKED}),
    ModelStatus.REVOKED: frozenset(),
}


class JobStatus(StrEnum):
    QUEUED = "queued"
    VALIDATING = "validating"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_JOB_STATUSES = frozenset({JobStatus.QUEUED, JobStatus.VALIDATING, JobStatus.RUNNING})
TERMINAL_JOB_STATUSES = frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED})

JOB_STATUS_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.VALIDATING, JobStatus.CANCELLED, JobStatus.FAILED}),
    JobStatus.VALIDATING: frozenset({JobStatus.RUNNING, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


class Disposition(StrEnum):
    """Analyst review dispositions (ERD 4.6 merged with Workflow Manual 12.1; see conflict C-09)."""

    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    BENIGN = "benign"
    DUPLICATE = "duplicate"
    NEEDS_INVESTIGATION = "needs_investigation"


class AlertStatus(StrEnum):
    """Derived alert status (computed from the latest review; not stored)."""

    OPEN = "open"
    INVESTIGATING = "investigating"
    CLOSED = "closed"


CLOSING_DISPOSITIONS = frozenset(
    {Disposition.TRUE_POSITIVE, Disposition.FALSE_POSITIVE, Disposition.BENIGN, Disposition.DUPLICATE}
)


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class AuditAction(StrEnum):
    """Controlled audit vocabulary (ERD 4.7: ``action`` uses a controlled event vocabulary)."""

    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGIN_LOCKED = "auth.login.locked"
    LOGOUT = "auth.logout"
    PASSWORD_CHANGE = "auth.password.change"
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_ROLE_CHANGE = "user.role.change"
    USER_DEACTIVATE = "user.deactivate"
    USER_ACTIVATE = "user.activate"
    USER_PASSWORD_RESET = "user.password.reset"
    DATASET_UPLOAD = "dataset.upload"
    DATASET_REJECT = "dataset.reject"
    DATASET_IMPORT = "dataset.import"
    DATASET_DELETE = "dataset.delete"
    ANALYSIS_CREATE = "analysis.create"
    ANALYSIS_COMPLETE = "analysis.complete"
    ANALYSIS_FAIL = "analysis.fail"
    ANALYSIS_CANCEL = "analysis.cancel"
    QUICK_ANALYSIS = "analysis.quick"
    ALERT_REVIEW = "alert.review"
    EXPORT_PREDICTIONS = "export.predictions"
    EXPORT_ALERTS = "export.alerts"
    EXPORT_REPORT = "export.report"
    MODEL_REGISTER = "model.register"
    MODEL_STATUS_CHANGE = "model.status.change"
    MODEL_VERIFY = "model.verify"
    MODEL_INTEGRITY_FAILURE = "model.integrity.failure"
    ACCESS_DENIED = "access.denied"
    DATASET_PURGE = "dataset.purge"
