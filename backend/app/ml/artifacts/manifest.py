"""Model bundle manifest (schema version 1.0) and the registry index.

The manifest is the contract between the training notebooks (which write it via
:mod:`app.ml.artifacts.export`) and the API (which validates it before loading any artifact).
It records *what* was trained, *on which data and split*, *which preprocessing*, the *measured* metrics,
thresholds, label mapping, runtime library versions and the SHA-256 of every component file.

Validation is strict (``extra="forbid"``): unknown fields, unsupported manifest versions, inconsistent
feature lists or thresholds make the bundle unusable (fail closed, SAD 5.3).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ml.constants import (
    ANOMALY_SCORE_DIRECTION,
    BENIGN_LABEL,
    ClassifierTask,
    DatasetFamily,
    ExplanationMethod,
    ModelType,
)
from app.ml.datasets.registry import get_schema, is_supported_schema

SUPPORTED_MANIFEST_VERSIONS = frozenset({"1.0"})
MANIFEST_FILENAME = "manifest.json"
MAX_MANIFEST_BYTES = 5 * 1024 * 1024
MAX_METRICS_JSON_BYTES = 256 * 1024

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
SafeFileName = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
ModelName = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")]
VersionString = Annotated[str, Field(pattern=r"^[0-9A-Za-z][0-9A-Za-z.+_-]{0,59}$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArtifactFile(_Strict):
    file: SafeFileName
    sha256: Sha256
    size_bytes: int = Field(ge=1)

    @field_validator("file")
    @classmethod
    def _no_traversal(cls, value: str) -> str:
        if ".." in value or "/" in value or "\\" in value:
            raise ValueError("artifact file names must be plain names inside the bundle directory")
        return value


class InputFeature(_Strict):
    name: str
    dtype: Literal["numeric", "categorical"]
    categories: list[str] | None = None


class FeatureReference(_Strict):
    """Benign-traffic reference statistics from the training split (used for reason codes)."""

    median: float | None = None
    q25: float | None = None
    q75: float | None = None
    mode: str | None = None
    mode_frequency: float | None = Field(default=None, ge=0, le=1)


class FeaturesSection(_Strict):
    feature_schema_version: str
    input_features: list[InputFeature] = Field(min_length=1)
    transformed_feature_names: list[str] = Field(min_length=1)
    transformed_feature_sources: list[str] = Field(min_length=1)
    benign_reference: dict[str, FeatureReference] = Field(default_factory=dict)

    @property
    def input_names(self) -> list[str]:
        return [f.name for f in self.input_features]

    @model_validator(mode="after")
    def _consistent(self) -> FeaturesSection:
        names = self.input_names
        if len(names) != len(set(names)):
            raise ValueError("input feature names must be unique")
        if len(self.transformed_feature_names) != len(self.transformed_feature_sources):
            raise ValueError("transformed_feature_names and transformed_feature_sources must have equal length")
        unknown_sources = set(self.transformed_feature_sources) - set(names)
        if unknown_sources:
            raise ValueError(f"transformed features reference unknown inputs: {sorted(unknown_sources)}")
        for feature in self.input_features:
            if feature.dtype == "categorical" and not feature.categories:
                raise ValueError(f"categorical feature {feature.name!r} must list its training categories")
        unknown_refs = set(self.benign_reference) - set(names)
        if unknown_refs:
            raise ValueError(f"benign_reference contains unknown features: {sorted(unknown_refs)}")
        return self


class PreprocessingSection(_Strict):
    preprocessing_version: Annotated[str, Field(min_length=1, max_length=60)]
    artifact: ArtifactFile
    description: str = Field(max_length=2000)
    steps: list[str] = Field(default_factory=list)


class FeatureImportance(_Strict):
    feature: str
    importance: float


class CalibrationInfo(_Strict):
    method: str
    evaluated_on: str
    brier_score: float | None = None
    expected_calibration_error: float | None = None


class ClassifierComponent(_Strict):
    artifact: ArtifactFile
    estimator_class: str
    task: ClassifierTask
    classes: list[str] = Field(min_length=2)
    benign_class: str = BENIGN_LABEL
    probability_calibrated: bool = False
    calibration: CalibrationInfo | None = None
    decision_threshold: float | None = Field(default=None, gt=0, lt=1)
    min_confidence: float = Field(default=0.0, ge=0, lt=1)
    explanation_method: ExplanationMethod = ExplanationMethod.BASELINE_DEVIATION
    global_feature_importance: list[FeatureImportance] = Field(default_factory=list, max_length=200)
    threshold_method: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> ClassifierComponent:
        if len(self.classes) != len(set(self.classes)):
            raise ValueError("classifier classes must be unique")
        if self.benign_class not in self.classes:
            raise ValueError("benign_class must be one of the classifier classes")
        if self.task == ClassifierTask.BINARY:
            if len(self.classes) != 2:
                raise ValueError("binary classifiers must have exactly two classes")
            if self.decision_threshold is None:
                raise ValueError("binary classifiers must declare decision_threshold (chosen on validation data)")
        elif self.decision_threshold is not None:
            raise ValueError("decision_threshold is only valid for binary classifiers")
        if self.probability_calibrated and self.calibration is None:
            raise ValueError("probability_calibrated=true requires calibration evidence")
        return self


class ReferencePoints(_Strict):
    """Anomaly-score anchors used by the risk policy: benign median → 0, threshold → 0.5, upper → 1."""

    benign_median: float
    threshold: float
    upper: float

    @model_validator(mode="after")
    def _ordered(self) -> ReferencePoints:
        if not (self.benign_median < self.threshold < self.upper):
            raise ValueError("reference points must satisfy benign_median < threshold < upper")
        return self


class AnomalyComponent(_Strict):
    artifact: ArtifactFile
    estimator_class: str
    score_definition: str
    score_direction: Literal["higher_is_more_anomalous"] = ANOMALY_SCORE_DIRECTION
    threshold: float
    threshold_method: str
    reference_points: ReferencePoints
    training_population: Literal["benign_only", "all_unlabeled"]

    @model_validator(mode="after")
    def _threshold_matches(self) -> AnomalyComponent:
        if abs(self.threshold - self.reference_points.threshold) > 1e-12:
            raise ValueError("threshold must equal reference_points.threshold")
        return self


class ComponentsSection(_Strict):
    classifier: ClassifierComponent | None = None
    anomaly_detector: AnomalyComponent | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> ComponentsSection:
        if self.classifier is None and self.anomaly_detector is None:
            raise ValueError("a bundle must contain a classifier and/or an anomaly detector")
        return self


class BundleInfo(_Strict):
    model_name: ModelName
    version: VersionString
    model_type: ModelType
    description: str = Field(max_length=1000)
    created_at: datetime
    created_by: str = Field(max_length=200)


class DatasetSection(_Strict):
    family: DatasetFamily
    schema_version: str
    source: str = Field(max_length=500)
    split_strategy: str = Field(max_length=1000)
    random_seed: int
    train_rows: int = Field(ge=0)
    validation_rows: int = Field(ge=0)
    test_rows: int = Field(ge=0)
    label_mapping_version: str
    class_policy: str | None = Field(default=None, max_length=1000)


class RuntimeSection(_Strict):
    python: str
    numpy: str
    pandas: str
    scikit_learn: str
    xgboost: str | None = None
    joblib: str


class GoldenSection(_Strict):
    """Parity fixture: raw canonical input rows and the outputs the bundle produced at export time."""

    input: ArtifactFile
    expected: ArtifactFile
    rows: int = Field(ge=1, le=10_000)


class BundleManifest(_Strict):
    manifest_version: str
    bundle: BundleInfo
    dataset: DatasetSection
    features: FeaturesSection
    preprocessing: PreprocessingSection
    components: ComponentsSection
    metrics: dict[str, Any] = Field(default_factory=dict)
    runtime: RuntimeSection
    golden: GoldenSection | None = None
    limitations: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("manifest_version")
    @classmethod
    def _supported_version(cls, value: str) -> str:
        if value not in SUPPORTED_MANIFEST_VERSIONS:
            raise ValueError(f"unsupported manifest_version {value!r}; supported: {sorted(SUPPORTED_MANIFEST_VERSIONS)}")
        return value

    @field_validator("metrics")
    @classmethod
    def _bounded_metrics(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_METRICS_JSON_BYTES:
            raise ValueError("metrics section is too large (limit 256 KiB)")
        return value

    @model_validator(mode="after")
    def _cross_checks(self) -> BundleManifest:
        if self.features.feature_schema_version != self.dataset.schema_version:
            raise ValueError("features.feature_schema_version must equal dataset.schema_version")
        if not is_supported_schema(self.dataset.schema_version):
            raise ValueError(f"unknown feature schema {self.dataset.schema_version!r}")
        schema = get_schema(self.dataset.schema_version)
        if schema.family != self.dataset.family:
            raise ValueError("dataset.family does not match the schema family")
        for feature in self.features.input_features:
            if feature.name not in schema.feature_names:
                raise ValueError(f"input feature {feature.name!r} is not part of schema {schema.schema_version}")
            if schema.feature_dtype(feature.name) != feature.dtype:
                raise ValueError(f"input feature {feature.name!r} has dtype {feature.dtype}, schema says otherwise")

        has_clf = self.components.classifier is not None
        has_anom = self.components.anomaly_detector is not None
        expected = {
            (True, True): {ModelType.ENSEMBLE},
            (True, False): {ModelType.CLASSIFIER, ModelType.SEMI_SUPERVISED},
            (False, True): {ModelType.ANOMALY_DETECTOR},
        }[(has_clf, has_anom)]
        if self.bundle.model_type not in expected:
            raise ValueError(f"model_type {self.bundle.model_type} is inconsistent with the bundle components")

        files = [self.preprocessing.artifact.file]
        if self.components.classifier:
            files.append(self.components.classifier.artifact.file)
        if self.components.anomaly_detector:
            files.append(self.components.anomaly_detector.artifact.file)
        if self.golden:
            files.extend([self.golden.input.file, self.golden.expected.file])
        if len(files) != len(set(files)) or MANIFEST_FILENAME in files:
            raise ValueError("artifact file names must be unique and must not be manifest.json")
        return self

    # Convenience --------------------------------------------------------------------------------
    @property
    def preprocessing_version(self) -> str:
        return self.preprocessing.preprocessing_version

    @property
    def feature_schema_version(self) -> str:
        return self.features.feature_schema_version


# ------------------------------------------------------------------------------- registry index
REGISTRY_VERSION = "1.0"
_BUNDLE_PATH = re.compile(r"^bundles/[a-z0-9][a-z0-9._-]{2,119}/[0-9A-Za-z][0-9A-Za-z.+_-]{0,59}$")


class RegistryEntry(_Strict):
    model_name: ModelName
    version: VersionString
    path: str
    manifest_sha256: Sha256

    @field_validator("path")
    @classmethod
    def _relative_bundle_path(cls, value: str) -> str:
        if not _BUNDLE_PATH.match(value):
            raise ValueError("registry paths must look like 'bundles/<model_name>/<version>'")
        return value


class RegistryIndex(_Strict):
    """``MODEL_MANIFEST`` file: index of exported bundles (written by notebooks, read by the CLI)."""

    registry_version: str = REGISTRY_VERSION
    bundles: list[RegistryEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique(self) -> RegistryIndex:
        keys = [(b.model_name, b.version) for b in self.bundles]
        if len(keys) != len(set(keys)):
            raise ValueError("registry contains duplicate model_name/version entries")
        if self.registry_version != REGISTRY_VERSION:
            raise ValueError(f"unsupported registry_version {self.registry_version!r}")
        return self
