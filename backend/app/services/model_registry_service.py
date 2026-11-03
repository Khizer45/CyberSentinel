"""Model registry: registration from the registry index, status governance and verified, cached loading.

The API process only *loads* bundles exported by the notebooks; there is no training, tuning or download
code path (SEC-07). Every load re-verifies the manifest hash pinned in ``model_versions.artifact_sha256``.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import MODEL_STATUS_TRANSITIONS, AuditAction, AuditOutcome, ModelStatus
from app.core.errors import ConflictError, ModelUnavailableError, NotFoundError, UnprocessableError
from app.db.types import utcnow
from app.ml.artifacts import ExpectedBundle, LoadedBundle, load_bundle, read_registry, verify_golden
from app.ml.errors import ArtifactError, ArtifactIntegrityError
from app.models import ModelVersion, User
from app.repositories import model_versions as model_repo
from app.services import audit_service
from app.services.preprocessing_adapter import supported_modes

logger = logging.getLogger("cybersentinel.models")


def expected_identity(model: ModelVersion) -> ExpectedBundle:
    return ExpectedBundle(
        model_name=model.model_name,
        version=model.version,
        manifest_sha256=model.artifact_sha256,
        feature_schema_version=model.feature_schema_version,
        preprocessing_version=model.preprocessing_version,
    )


def to_read_dict(model: ModelVersion) -> dict[str, Any]:
    """ORM → API dict, adding derived fields and omitting the artifact location (FR-06)."""
    return {
        "id": model.id,
        "model_name": model.model_name,
        "version": model.version,
        "model_type": model.model_type,
        "task": model.task,
        "dataset_family": model.dataset_family,
        "feature_schema_version": model.feature_schema_version,
        "preprocessing_version": model.preprocessing_version,
        "description": model.description,
        "status": model.status,
        "status_reason": model.status_reason,
        "probability_calibrated": model.probability_calibrated,
        "explanation_method": model.explanation_method,
        "label_map": model.label_map,
        "threshold_config": model.threshold_config,
        "metrics": model.metrics,
        "supported_modes": supported_modes(model.model_type),
        "artifact_sha256": model.artifact_sha256,
        "approved_at": model.approved_at,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }


class ModelRegistry:
    """Thread-safe LRU cache of verified bundles keyed by ``(model_version_id, manifest_sha256)``."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: OrderedDict[tuple[uuid.UUID, str], LoadedBundle] = OrderedDict()
        self._lock = threading.RLock()
        self._key_locks: dict[tuple[uuid.UUID, str], threading.Lock] = {}

    def _load(self, model: ModelVersion) -> LoadedBundle:
        return load_bundle(
            self.settings.model_dir,
            model.artifact_uri,
            expected_identity(model),
            max_artifact_bytes=self.settings.max_artifact_bytes,
        )

    def get_bundle(self, model: ModelVersion) -> LoadedBundle:
        if model.status == ModelStatus.REVOKED:
            raise ModelUnavailableError("This model version has been revoked.", code="model_revoked")
        if model.status != ModelStatus.APPROVED:
            raise ModelUnavailableError("This model version is not approved for analysis.", code="model_not_approved")
        key = (model.id, model.artifact_sha256)
        with self._lock:
            bundle = self._cache.get(key)
            if bundle is not None:
                self._cache.move_to_end(key)
                return bundle
            key_lock = self._key_locks.setdefault(key, threading.Lock())
        with key_lock:
            with self._lock:
                if key in self._cache:
                    return self._cache[key]
            try:
                bundle = self._load(model)
            except ArtifactError as exc:
                self._report_failure(model, exc)
                raise ModelUnavailableError(details={"reason": exc.code}) from exc
            with self._lock:
                self._cache[key] = bundle
                while len(self._cache) > self.settings.model_cache_size:
                    self._cache.popitem(last=False)
            logger.info("model bundle loaded", extra={"model": model.model_name, "version": model.version})
            return bundle

    def _report_failure(self, model: ModelVersion, exc: ArtifactError) -> None:
        logger.error(
            "model bundle failed verification",
            extra={"model": model.model_name, "version": model.version, "error_code": exc.code},
        )
        if isinstance(exc, ArtifactIntegrityError):
            audit_service.record_independent(
                AuditAction.MODEL_INTEGRITY_FAILURE,
                actor_id=None,
                outcome=AuditOutcome.FAILURE,
                resource_type="model_version",
                resource_id=model.id,
                details={"model": model.model_name, "version": model.version, "reason": exc.code},
            )

    def invalidate(self, model_version_id: uuid.UUID) -> None:
        with self._lock:
            for key in [k for k in self._cache if k[0] == model_version_id]:
                del self._cache[key]

    def verify(self, model: ModelVersion) -> list[dict[str, Any]]:
        """Fresh (uncached) integrity, compatibility and golden-parity verification."""
        checks: list[dict[str, Any]] = []
        if model.status == ModelStatus.REVOKED:
            return [{"name": "status", "passed": False, "detail": "revoked models are never loaded"}]
        try:
            bundle = self._load(model)
        except ArtifactError as exc:
            self._report_failure(model, exc)
            self.invalidate(model.id)
            return [{"name": "load_and_integrity", "passed": False, "detail": exc.code}]
        checks.append({"name": "load_and_integrity", "passed": True, "detail": "manifest and file checksums verified"})
        checks.append({"name": "runtime_compatibility", "passed": True, "detail": "library versions compatible"})
        golden = verify_golden(bundle)
        if golden.get("available"):
            checks.append(
                {
                    "name": "golden_parity",
                    "passed": bool(golden.get("passed")),
                    "detail": f"{golden.get('rows')} rows, max score difference {golden.get('max_score_abs_diff')}",
                }
            )
        else:
            checks.append({"name": "golden_parity", "passed": True, "detail": "no golden fixture in this bundle"})
        return checks

    @property
    def cached_count(self) -> int:
        with self._lock:
            return len(self._cache)


# ------------------------------------------------------------------------------------- governance
def get_model(session: Session, model_version_id: uuid.UUID, *, user: User | None = None) -> ModelVersion:
    model = model_repo.get(session, model_version_id)
    if model is None:
        raise NotFoundError("Model version not found.")
    if user is not None and user.role != "admin" and model.status != ModelStatus.APPROVED:
        raise NotFoundError("Model version not found.")
    return model


def change_status(
    session: Session,
    registry: ModelRegistry,
    *,
    actor: User | None,
    model_version_id: uuid.UUID,
    new_status: ModelStatus,
    reason: str | None,
    ip: str | None,
) -> ModelVersion:
    model = get_model(session, model_version_id)
    current = ModelStatus(model.status)
    if new_status == current:
        return model
    if new_status not in MODEL_STATUS_TRANSITIONS[current]:
        raise ConflictError(
            f"Cannot change status from {current.value} to {new_status.value}.",
            code="invalid_status_transition",
            details={"allowed": sorted(s.value for s in MODEL_STATUS_TRANSITIONS[current])},
        )
    if new_status == ModelStatus.APPROVED:
        checks = registry.verify(model)
        failed = [c for c in checks if not c["passed"]]
        if failed:
            raise UnprocessableError(
                "The model failed verification and cannot be approved.",
                code="model_verification_failed",
                details={"checks": checks},
            )
        model.approved_by = actor.id if actor else None
        model.approved_at = utcnow()
    if new_status in (ModelStatus.RETIRED, ModelStatus.REVOKED):
        registry.invalidate(model.id)
    model.status = new_status.value
    model.status_reason = reason
    audit_service.record(
        session,
        AuditAction.MODEL_STATUS_CHANGE,
        actor_id=actor.id if actor else None,
        ip_address=ip,
        resource_type="model_version",
        resource_id=model.id,
        details={"from": current.value, "to": new_status.value, "model": model.model_name, "version": model.version},
    )
    session.commit()
    return model


@dataclass
class SyncResult:
    model_name: str
    version: str
    outcome: str  # registered | unchanged | error
    detail: str


def sync_from_registry(session: Session, settings: Settings, registry: ModelRegistry) -> list[SyncResult]:
    """Register bundles listed in ``MODEL_MANIFEST`` as ``draft`` after full verification (CLI only)."""
    index = read_registry(settings.model_manifest)  # type: ignore[arg-type]
    results: list[SyncResult] = []
    for entry in index.bundles:
        existing = model_repo.get_by_name_version(session, entry.model_name, entry.version)
        if existing is not None:
            if existing.artifact_sha256 == entry.manifest_sha256:
                results.append(
                    SyncResult(entry.model_name, entry.version, "unchanged", f"already registered ({existing.status})")
                )
            else:
                results.append(
                    SyncResult(
                        entry.model_name,
                        entry.version,
                        "error",
                        "a different bundle is registered under this name/version; export a new version",
                    )
                )
            continue
        try:
            bundle = load_bundle(
                settings.model_dir,
                entry.path,
                ExpectedBundle(entry.model_name, entry.version, entry.manifest_sha256),
                max_artifact_bytes=settings.max_artifact_bytes,
            )
            golden = verify_golden(bundle)
            if golden.get("available") and not golden.get("passed"):
                results.append(SyncResult(entry.model_name, entry.version, "error", f"golden parity failed: {golden}"))
                continue
        except ArtifactError as exc:
            results.append(SyncResult(entry.model_name, entry.version, "error", f"{exc.code}: {exc.message}"))
            continue
        manifest = bundle.manifest
        clf, anom = manifest.components.classifier, manifest.components.anomaly_detector
        model = ModelVersion(
            model_name=entry.model_name,
            version=entry.version,
            model_type=manifest.bundle.model_type.value,
            task=clf.task.value if clf else None,
            dataset_family=manifest.dataset.family.value,
            description=manifest.bundle.description,
            artifact_uri=entry.path,
            artifact_sha256=entry.manifest_sha256,
            preprocessing_version=manifest.preprocessing_version,
            feature_schema_version=manifest.feature_schema_version,
            label_map=(
                {
                    "classes": clf.classes,
                    "benign_class": clf.benign_class,
                    "label_mapping_version": manifest.dataset.label_mapping_version,
                }
                if clf
                else None
            ),
            threshold_config={
                "classifier": (
                    {
                        "decision_threshold": clf.decision_threshold,
                        "min_confidence": clf.min_confidence,
                        "threshold_method": clf.threshold_method,
                    }
                    if clf
                    else None
                ),
                "anomaly_detector": (
                    {
                        "threshold": anom.threshold,
                        "threshold_method": anom.threshold_method,
                        "reference_points": anom.reference_points.model_dump(),
                        "score_direction": anom.score_direction,
                        "score_definition": anom.score_definition,
                        "training_population": anom.training_population,
                    }
                    if anom
                    else None
                ),
            },
            metrics={
                "measured": manifest.metrics,
                "global_feature_importance": [fi.model_dump() for fi in clf.global_feature_importance] if clf else [],
                "dataset": manifest.dataset.model_dump(mode="json"),
                "limitations": manifest.limitations,
                "runtime": manifest.runtime.model_dump(),
                "calibration": clf.calibration.model_dump() if clf and clf.calibration else None,
            },
            explanation_method=clf.explanation_method.value if clf else "baseline_deviation",
            probability_calibrated=bool(clf and clf.probability_calibrated),
            status=ModelStatus.DRAFT.value,
        )
        session.add(model)
        session.flush()
        audit_service.record(
            session,
            AuditAction.MODEL_REGISTER,
            actor_id=None,
            resource_type="model_version",
            resource_id=model.id,
            details={"model": model.model_name, "version": model.version, "manifest_sha256": model.artifact_sha256},
        )
        session.commit()
        results.append(SyncResult(entry.model_name, entry.version, "registered", "registered as draft"))
    return results
