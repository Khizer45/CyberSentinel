"""Deterministic preprocessing shared by notebooks and the API (no fitting happens here)."""

from app.ml.preprocessing.cleaning import FEATURE_ABS_MAX, CleaningStats, clean_feature_frame
from app.ml.preprocessing.columns import ColumnResolution, normalize_column_name, resolve_columns
from app.ml.preprocessing.labels import NormalizedLabels, label_key, normalize_labels
from app.ml.preprocessing.reader import (
    CanonicalChunk,
    CsvLayout,
    context_frame,
    detect_text_encoding,
    inspect_csv,
    iter_canonical_chunks,
    read_header,
    validate_structure,
)
from app.ml.preprocessing.transforms import ALLOWED_TRANSFORM_FUNCTIONS, signed_log1p

__all__ = [
    "ALLOWED_TRANSFORM_FUNCTIONS",
    "FEATURE_ABS_MAX",
    "CanonicalChunk",
    "CleaningStats",
    "ColumnResolution",
    "CsvLayout",
    "NormalizedLabels",
    "clean_feature_frame",
    "context_frame",
    "detect_text_encoding",
    "inspect_csv",
    "iter_canonical_chunks",
    "label_key",
    "normalize_column_name",
    "normalize_labels",
    "read_header",
    "resolve_columns",
    "signed_log1p",
    "validate_structure",
]
