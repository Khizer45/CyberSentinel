"""Registry of supported dataset schemas and header-based schema detection."""

from __future__ import annotations

from collections.abc import Iterable

from app.ml.constants import DatasetFamily
from app.ml.datasets.base import DatasetSchema
from app.ml.datasets.cicids2017 import CICIDS2017_SCHEMA
from app.ml.datasets.unsw_nb15 import UNSW_NB15_SCHEMA

_SCHEMAS: dict[str, DatasetSchema] = {
    CICIDS2017_SCHEMA.schema_version: CICIDS2017_SCHEMA,
    UNSW_NB15_SCHEMA.schema_version: UNSW_NB15_SCHEMA,
}


def list_schemas() -> list[DatasetSchema]:
    return list(_SCHEMAS.values())


def get_schema(schema_version: str) -> DatasetSchema:
    try:
        return _SCHEMAS[schema_version]
    except KeyError:
        raise KeyError(f"unsupported schema_version {schema_version!r}; supported: {sorted(_SCHEMAS)}") from None


def get_schema_for_family(family: DatasetFamily | str) -> DatasetSchema:
    family = DatasetFamily(family)
    for schema in _SCHEMAS.values():
        if schema.family == family:
            return schema
    raise KeyError(f"no schema registered for family {family!r}")


def is_supported_schema(schema_version: str) -> bool:
    return schema_version in _SCHEMAS


def detect_schema(normalized_columns: Iterable[str]) -> tuple[DatasetSchema | None, dict[str, float]]:
    """Pick the schema whose canonical features best cover the given (normalized) columns.

    Returns the best schema (or ``None`` if no schema covers at least 90 % of its features) and the
    coverage score of every schema, so the caller can explain the decision.
    """
    columns = set(normalized_columns)
    scores: dict[str, float] = {}
    for version, schema in _SCHEMAS.items():
        resolved = {schema.column_aliases.get(c, c) for c in columns}
        scores[version] = round(len(resolved & set(schema.feature_names)) / len(schema.feature_names), 4)
    best_version = max(scores, key=lambda v: scores[v])
    if scores[best_version] < 0.9:
        return None, scores
    return _SCHEMAS[best_version], scores
