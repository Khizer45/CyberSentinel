"""Dataset-family schema definitions.

A :class:`DatasetSchema` is the versioned feature contract for one dataset family. CIC-IDS2017 and
UNSW-NB15 have **different** schemas (different flow extractors, feature semantics and units), so the
platform never merges them into a shared feature space (see docs/00_phase1_architecture_review.md,
C-16/C-17 and the dataset cards).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from app.ml.constants import DatasetFamily

FeatureDType = Literal["numeric", "categorical"]


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    dtype: FeatureDType = "numeric"
    description: str = ""


@dataclass(frozen=True)
class DatasetSchema:
    """Canonical (normalized) column contract for one dataset family.

    Attributes:
        family: dataset family identifier.
        schema_version: identifier stored in ``datasets.schema_version`` / ``model_versions.feature_schema_version``.
        features: canonical model-input candidates in canonical order.
        label_columns: canonical names of ground-truth columns (never model inputs).
        identifier_columns: canonical names of identifier columns (never model inputs; may feed flow context).
        context_columns: canonical column → flow-context key for allowlisted identifiers shown to analysts.
        ip_context_keys: context keys holding IP addresses (pseudonymized before storage).
        column_aliases: normalized alias → canonical name (alternative spellings seen in exports).
        known_duplicate_columns: canonical feature → normalized alias of a *known identical* duplicate column.
        shortcut_feature_candidates: features suspected to act as dataset-specific shortcuts (ablation in notebooks).
    """

    family: DatasetFamily
    schema_version: str
    display_name: str
    features: tuple[FeatureSpec, ...]
    label_columns: tuple[str, ...]
    identifier_columns: tuple[str, ...] = ()
    context_columns: Mapping[str, str] = field(default_factory=dict)
    ip_context_keys: frozenset[str] = frozenset()
    column_aliases: Mapping[str, str] = field(default_factory=dict)
    known_duplicate_columns: Mapping[str, str] = field(default_factory=dict)
    shortcut_feature_candidates: tuple[str, ...] = ()
    label_mapping_version: str = ""
    source: str = ""
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        names = [f.name for f in self.features]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate feature names in schema {self.schema_version}")
        overlap = set(names) & (set(self.label_columns) | set(self.identifier_columns))
        if overlap:
            raise ValueError(f"label/identifier columns must not be features: {sorted(overlap)}")

    @property
    def feature_names(self) -> list[str]:
        return [f.name for f in self.features]

    @property
    def numeric_features(self) -> list[str]:
        return [f.name for f in self.features if f.dtype == "numeric"]

    @property
    def categorical_features(self) -> list[str]:
        return [f.name for f in self.features if f.dtype == "categorical"]

    def feature_dtype(self, name: str) -> FeatureDType:
        for spec in self.features:
            if spec.name == name:
                return spec.dtype
        raise KeyError(name)

    @property
    def known_columns(self) -> set[str]:
        return set(self.feature_names) | set(self.label_columns) | set(self.identifier_columns)
