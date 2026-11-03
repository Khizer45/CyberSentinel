"""In-memory representation of a verified model bundle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ml.artifacts.manifest import BundleManifest
from app.ml.constants import AnalysisMode


@dataclass(frozen=True)
class ExpectedBundle:
    """Identity the caller expects (from the database row) — every field is checked against the manifest."""

    model_name: str
    version: str
    manifest_sha256: str
    feature_schema_version: str | None = None
    preprocessing_version: str | None = None


@dataclass(frozen=True)
class LoadedBundle:
    manifest: BundleManifest
    manifest_sha256: str
    bundle_dir: Path  # internal only — never serialized to API responses
    preprocessor: Any
    classifier: Any | None = None
    anomaly_detector: Any | None = None
    loaded_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def supports_classification(self) -> bool:
        return self.classifier is not None and self.manifest.components.classifier is not None

    @property
    def supports_anomaly(self) -> bool:
        return self.anomaly_detector is not None and self.manifest.components.anomaly_detector is not None

    def supports_mode(self, mode: AnalysisMode | str) -> bool:
        mode = AnalysisMode(mode)
        if mode == AnalysisMode.CLASSIFICATION:
            return self.supports_classification
        if mode == AnalysisMode.ANOMALY:
            return self.supports_anomaly
        return self.supports_classification and self.supports_anomaly

    @property
    def supported_modes(self) -> list[str]:
        return [m.value for m in AnalysisMode if self.supports_mode(m)]
