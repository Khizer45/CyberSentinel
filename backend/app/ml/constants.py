"""Shared vocabularies for the ML layer.

These values are part of the data contract between the notebooks (which write manifests and
labels), the API (which stores predictions) and the frontend (which renders them). Changing a
value is a breaking change and requires a new feature-schema / label-map version.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal


class DatasetFamily(StrEnum):
    """Supported dataset families. Each family has its own feature schema (no shared schema)."""

    CICIDS2017 = "cicids2017"
    UNSW_NB15 = "unsw_nb15"


class ModelType(StrEnum):
    """``model_versions.model_type`` values (ERD 4.3)."""

    CLASSIFIER = "classifier"
    ANOMALY_DETECTOR = "anomaly_detector"
    SEMI_SUPERVISED = "semi_supervised"
    ENSEMBLE = "ensemble"


class ClassifierTask(StrEnum):
    BINARY = "binary"
    MULTICLASS = "multiclass"


class AnalysisMode(StrEnum):
    """``analysis_jobs.requested_mode`` values (ERD 4.4)."""

    CLASSIFICATION = "classification"
    ANOMALY = "anomaly"
    COMBINED = "combined"


class RiskBand(StrEnum):
    """``predictions.risk_band`` values (ERD 4.5), ordered from lowest to highest."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


RISK_BAND_ORDER: tuple[RiskBand, ...] = (RiskBand.LOW, RiskBand.MEDIUM, RiskBand.HIGH, RiskBand.CRITICAL)


def risk_band_rank(band: str) -> int:
    """Return the ordinal rank of a risk band (0 = low). Raises ``ValueError`` for unknown bands."""
    return RISK_BAND_ORDER.index(RiskBand(band))


class ExplanationMethod(StrEnum):
    XGBOOST_TREE_SHAP = "xgboost_tree_shap"
    TREE_PATH_ATTRIBUTION = "tree_path_attribution"
    BASELINE_DEVIATION = "baseline_deviation"


# Canonical label used for benign traffic in every dataset family after label normalization.
BENIGN_LABEL = "Benign"
# Label used by binary classifiers for the positive class.
MALICIOUS_LABEL = "Malicious"
# Predicted label when the classifier's confidence is below the manifest's ``min_confidence``.
# Workflow Manual 3.3 / 10.1: return an explicit needs-review state instead of a fabricated attack label.
NEEDS_REVIEW_LABEL = "needs_review"
# Predicted label for anomaly-only analyses, where no classifier is run.
UNCLASSIFIED_LABEL = "unclassified"

SPECIAL_PREDICTED_LABELS = frozenset({NEEDS_REVIEW_LABEL, UNCLASSIFIED_LABEL})

ANOMALY_SCORE_DIRECTION: Literal["higher_is_more_anomalous"] = "higher_is_more_anomalous"

EXPLANATION_DISCLAIMER = (
    "Feature attributions describe how the model used its inputs for this prediction. "
    "They are not causal explanations and do not by themselves prove malicious activity."
)
