"""Column-name normalization and header resolution against a dataset schema.

Headers are read with the ``csv`` module (not pandas) so that duplicated names are detected before pandas
would silently rename them (``"x"`` → ``"x.1"``).
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.ml.datasets.base import DatasetSchema
from app.ml.errors import DatasetFormatError, FeatureSchemaError

_NON_ALNUM = re.compile(r"[^0-9a-z]+")
MAX_COLUMNS = 512
MAX_HEADER_NAME_LENGTH = 128


def normalize_column_name(name: str) -> str:
    """Normalize a raw header to snake_case: ``" Flow Bytes/s"`` → ``"flow_bytes_s"``."""
    text = unicodedata.normalize("NFKC", str(name)).replace("﻿", "").strip().lower()
    return _NON_ALNUM.sub("_", text).strip("_")


@dataclass(frozen=True)
class ColumnResolution:
    """Mapping from raw header positions to canonical column roles."""

    raw_headers: tuple[str, ...]
    canonical_names: tuple[str, ...]
    feature_positions: dict[str, int]
    label_positions: dict[str, int]
    identifier_positions: dict[str, int]
    known_duplicate_positions: dict[str, int]
    unknown_columns: tuple[str, ...]
    missing_features: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_labels(self) -> bool:
        return bool(self.label_positions)

    def to_report(self) -> dict[str, object]:
        return {
            "column_count": len(self.raw_headers),
            "feature_columns_found": len(self.feature_positions),
            "label_columns": sorted(self.label_positions),
            "identifier_columns": sorted(self.identifier_positions),
            "known_duplicate_columns": sorted(self.known_duplicate_positions),
            "unknown_columns": list(self.unknown_columns)[:50],
            "missing_features": list(self.missing_features),
        }


def resolve_columns(
    raw_headers: Sequence[str],
    schema: DatasetSchema,
    *,
    required_features: Sequence[str] | None = None,
    reject_unknown: bool = False,
) -> ColumnResolution:
    """Resolve raw CSV headers to canonical roles for ``schema``.

    Raises:
        DatasetFormatError: empty/oversized/duplicated headers (other than the schema's known duplicates).
        FeatureSchemaError: required features are missing, or unknown columns when ``reject_unknown``.
    """
    if not raw_headers:
        raise DatasetFormatError("the file has no header row")
    if len(raw_headers) > MAX_COLUMNS:
        raise DatasetFormatError(f"too many columns ({len(raw_headers)} > {MAX_COLUMNS})")

    canonical: list[str] = []
    for position, raw in enumerate(raw_headers):
        if len(str(raw)) > MAX_HEADER_NAME_LENGTH:
            raise DatasetFormatError(f"column name at position {position + 1} is too long")
        name = normalize_column_name(raw)
        if not name:
            raise DatasetFormatError(f"empty column name at position {position + 1}")
        canonical.append(schema.column_aliases.get(name, name))

    occurrences: dict[str, list[int]] = defaultdict(list)
    for position, name in enumerate(canonical):
        occurrences[name].append(position)

    known_duplicates: dict[str, int] = {}
    alias_to_feature = {alias: feature for feature, alias in schema.known_duplicate_columns.items()}
    unexpected_duplicates: list[str] = []
    for name, positions in occurrences.items():
        if len(positions) == 1:
            continue
        if name in schema.known_duplicate_columns and len(positions) == 2:
            known_duplicates[name] = positions[1]
        else:
            unexpected_duplicates.append(name)
    if unexpected_duplicates:
        raise DatasetFormatError(
            "duplicate column names after normalization",
            details={"duplicate_columns": sorted(unexpected_duplicates)},
        )

    feature_set = set(schema.feature_names)
    feature_positions: dict[str, int] = {}
    label_positions: dict[str, int] = {}
    identifier_positions: dict[str, int] = {}
    unknown: list[str] = []
    for name, positions in occurrences.items():
        first = positions[0]
        if name in alias_to_feature:
            # Pre-renamed duplicate copy (e.g. "Fwd Header Length.1" exported by pandas).
            known_duplicates.setdefault(alias_to_feature[name], first)
        elif name in feature_set:
            feature_positions[name] = first
        elif name in schema.label_columns:
            label_positions[name] = first
        elif name in schema.identifier_columns:
            identifier_positions[name] = first
        else:
            unknown.append(raw_headers[first].strip())

    required = list(required_features) if required_features is not None else schema.feature_names
    missing = [name for name in required if name not in feature_positions]
    if missing:
        raise FeatureSchemaError(
            f"{len(missing)} required feature column(s) are missing for schema {schema.schema_version}",
            details={"missing_features": missing, "schema_version": schema.schema_version},
        )
    if unknown and reject_unknown:
        raise FeatureSchemaError(
            "unexpected columns are not allowed by the configured policy",
            details={"unknown_columns": unknown[:50]},
        )
    warnings = []
    if unknown:
        warnings.append(f"{len(unknown)} unrecognised column(s) will be ignored")
    for feature in known_duplicates:
        warnings.append(f"known duplicate column for '{feature}' will be verified and dropped")

    ordered_features = {name: feature_positions[name] for name in schema.feature_names if name in feature_positions}
    return ColumnResolution(
        raw_headers=tuple(str(h) for h in raw_headers),
        canonical_names=tuple(canonical),
        feature_positions=ordered_features,
        label_positions=label_positions,
        identifier_positions=identifier_positions,
        known_duplicate_positions=known_duplicates,
        unknown_columns=tuple(unknown),
        missing_features=tuple(missing),
        warnings=tuple(warnings),
    )
