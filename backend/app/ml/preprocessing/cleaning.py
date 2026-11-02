"""Deterministic cleaning applied identically at training time (notebooks) and inference time (API).

Nothing here is fitted: imputation and scaling are learned by the preprocessing pipeline on the training
split only and are applied at inference through the exported artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.ml.datasets.base import DatasetSchema

# Absolute values above this are treated as invalid measurements (missing), not as information.
FEATURE_ABS_MAX = 1e15
MISSING_CATEGORY_TOKENS = frozenset({"", "nan", "none", "null"})


@dataclass
class CleaningStats:
    """Counters describing data-quality issues found while cleaning (aggregated across chunks)."""

    rows: int = 0
    non_numeric: dict[str, int] = field(default_factory=dict)
    non_finite: dict[str, int] = field(default_factory=dict)
    out_of_range: dict[str, int] = field(default_factory=dict)
    missing: dict[str, int] = field(default_factory=dict)

    @staticmethod
    def _add(target: dict[str, int], name: str, count: int) -> None:
        if count:
            target[name] = target.get(name, 0) + int(count)

    def merge(self, other: CleaningStats) -> None:
        self.rows += other.rows
        for attr in ("non_numeric", "non_finite", "out_of_range", "missing"):
            mine: dict[str, int] = getattr(self, attr)
            for key, value in getattr(other, attr).items():
                self._add(mine, key, value)

    @property
    def invalid_total(self) -> int:
        return sum(self.non_numeric.values()) + sum(self.out_of_range.values())

    def invalid_fraction_by_column(self) -> dict[str, float]:
        if not self.rows:
            return {}
        columns = set(self.non_numeric) | set(self.out_of_range)
        return {
            c: (self.non_numeric.get(c, 0) + self.out_of_range.get(c, 0)) / self.rows for c in sorted(columns)
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "rows": self.rows,
            "non_numeric_values": dict(sorted(self.non_numeric.items())),
            "non_finite_values": dict(sorted(self.non_finite.items())),
            "out_of_range_values": dict(sorted(self.out_of_range.items())),
            "missing_values": dict(sorted(self.missing.items())),
        }


def _clean_numeric(column: pd.Series, name: str, stats: CleaningStats) -> pd.Series:
    if pd.api.types.is_numeric_dtype(column) and not pd.api.types.is_bool_dtype(column):
        values = column.astype("float64")
        empty = values.isna()
        non_numeric = pd.Series(False, index=column.index)
    else:
        text = column.astype(object).map(lambda v: v.strip() if isinstance(v, str) else v)
        empty = text.isna() | text.map(lambda v: isinstance(v, str) and v == "")
        values = pd.to_numeric(text.where(~empty), errors="coerce").astype("float64")
        non_numeric = values.isna() & ~empty
    raw = values.to_numpy(copy=True)
    non_finite = np.isinf(raw)
    out_of_range = np.zeros(raw.shape, dtype=bool)
    finite = np.isfinite(raw)
    out_of_range[finite] = np.abs(raw[finite]) > FEATURE_ABS_MAX
    raw[non_finite | out_of_range] = np.nan
    stats._add(stats.non_numeric, name, int(non_numeric.sum()))
    stats._add(stats.non_finite, name, int(non_finite.sum()))
    stats._add(stats.out_of_range, name, int(out_of_range.sum()))
    stats._add(stats.missing, name, int(empty.sum()))
    return pd.Series(raw, index=column.index, name=name, dtype="float64")


def _clean_categorical(column: pd.Series, name: str, stats: CleaningStats) -> pd.Series:
    def normalize(value: object) -> object:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return np.nan
        text = str(value).strip().lower()
        return np.nan if text in MISSING_CATEGORY_TOKENS else text

    cleaned = column.astype(object).map(normalize).astype(object)
    stats._add(stats.missing, name, int(cleaned.isna().sum()))
    return cleaned


def clean_feature_frame(
    frame: pd.DataFrame, schema: DatasetSchema, feature_names: list[str] | None = None
) -> tuple[pd.DataFrame, CleaningStats]:
    """Return a frame with exactly ``feature_names`` (canonical order), typed and cleaned.

    Numeric features → ``float64`` with non-numeric, non-finite and |x| > :data:`FEATURE_ABS_MAX` values set to
    NaN (counted in the returned stats). Categorical features → stripped lower-case strings, NaN for missing.
    """
    names = feature_names if feature_names is not None else schema.feature_names
    stats = CleaningStats(rows=len(frame))
    cleaned: dict[str, pd.Series] = {}
    for name in names:
        if name not in frame.columns:
            raise KeyError(f"feature column {name!r} not present")
        if schema.feature_dtype(name) == "numeric":
            cleaned[name] = _clean_numeric(frame[name], name, stats)
        else:
            cleaned[name] = _clean_categorical(frame[name], name, stats)
    return pd.DataFrame(cleaned, index=frame.index), stats


def numeric_equal(left: pd.Series, right: pd.Series) -> bool:
    """True when two raw columns hold the same numeric values (NaN == NaN), used for known duplicates."""
    a = pd.to_numeric(left.astype(object), errors="coerce").to_numpy(dtype="float64")
    b = pd.to_numeric(right.astype(object), errors="coerce").to_numpy(dtype="float64")
    return bool(np.array_equal(a, b, equal_nan=True))
