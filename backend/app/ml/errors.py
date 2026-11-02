"""Exceptions raised by the ML layer.

Each exception carries a stable, machine-readable ``code`` that the API maps to an HTTP status and that
is safe to show to users (no paths, no stack traces). ``details`` must only contain data that is safe to
return to an authorized client (column names, counts, allowed values).
"""

from __future__ import annotations

from typing import Any


class MLError(Exception):
    code = "ml_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


# --- Dataset / feature contract ------------------------------------------------------------------
class DatasetFormatError(MLError):
    """The file is not a well-formed CSV for the selected schema (header problems, encoding...)."""

    code = "dataset_format_invalid"


class FeatureSchemaError(MLError):
    """Input columns/values do not satisfy the feature contract (missing/unexpected features)."""

    code = "feature_schema_mismatch"


class LabelNormalizationError(MLError):
    """A raw label is not covered by the versioned label mapping (never silently mapped)."""

    code = "label_mapping_unknown"


# --- Model artifacts -----------------------------------------------------------------------------
class ArtifactError(MLError):
    code = "artifact_error"


class ArtifactNotFoundError(ArtifactError):
    code = "artifact_missing"


class ArtifactPathError(ArtifactError):
    code = "artifact_path_invalid"


class ArtifactIntegrityError(ArtifactError):
    code = "artifact_integrity_failed"


class ArtifactIncompatibleError(ArtifactError):
    code = "artifact_incompatible"


class ManifestError(ArtifactError):
    code = "manifest_invalid"


class InferenceError(MLError):
    code = "inference_failed"
