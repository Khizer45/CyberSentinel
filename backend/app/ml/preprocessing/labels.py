"""Versioned, strict label normalization.

Raw labels are mapped to (fine-grained label, evaluation category, binary flag). Labels that are not in
the versioned mapping raise :class:`LabelNormalizationError` listing them — they are never silently
mapped to a default class ("Never silently combine incompatible features or labels").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.ml.constants import BENIGN_LABEL, DatasetFamily
from app.ml.datasets.base import DatasetSchema
from app.ml.datasets.cicids2017 import CIC_LABEL_MAP
from app.ml.datasets.unsw_nb15 import UNSW_LABEL_MAP
from app.ml.errors import LabelNormalizationError

_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def label_key(raw: object) -> str:
    """Case-, whitespace- and punctuation-insensitive key: ``"Web Attack � XSS"`` → ``"web attack xss"``."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return ""
    text = unicodedata.normalize("NFKC", str(raw)).lower()
    return _NON_ALNUM.sub(" ", text).strip()


@dataclass(frozen=True)
class NormalizedLabels:
    """Normalized ground truth aligned with the input rows.

    ``category`` is ``None`` when only a binary label is available (e.g. UNSW file without ``attack_cat``).
    """

    original: pd.Series
    fine: pd.Series | None
    category: pd.Series | None
    binary: pd.Series
    inconsistent_rows: int = 0


def _map_keys(keys: pd.Series, mapping: dict[str, tuple[str, str]], *, column: str) -> tuple[pd.Series, pd.Series]:
    unique = pd.unique(keys)
    unknown = sorted(str(k) for k in unique if k not in mapping)
    if unknown:
        raise LabelNormalizationError(
            f"{len(unknown)} label value(s) in '{column}' are not covered by the label mapping",
            details={"unknown_labels": unknown[:50], "column": column},
        )
    fine = keys.map({k: mapping[k][0] for k in unique}).astype(object)
    category = keys.map({k: mapping[k][1] for k in unique}).astype(object)
    return fine, category


def normalize_labels(labels: pd.DataFrame, schema: DatasetSchema) -> NormalizedLabels:
    """Normalize the label columns of ``labels`` (canonical column names) for ``schema``."""
    if schema.family == DatasetFamily.CICIDS2017:
        if "label" not in labels:
            raise LabelNormalizationError("missing 'label' column", details={"column": "label"})
        original = labels["label"].astype(object).map(lambda v: str(v).strip())
        keys = labels["label"].map(label_key)
        fine, category = _map_keys(keys, CIC_LABEL_MAP, column="label")
        binary = (category != BENIGN_LABEL).astype("int64")
        return NormalizedLabels(original=original, fine=fine, category=category, binary=binary)

    if schema.family == DatasetFamily.UNSW_NB15:
        has_cat = "attack_cat" in labels
        has_bin = "label" in labels
        if not has_cat and not has_bin:
            raise LabelNormalizationError("missing 'attack_cat' and 'label' columns", details={"column": "attack_cat"})
        binary_raw: pd.Series | None = None
        if has_bin:
            binary_raw = pd.to_numeric(labels["label"].astype(object), errors="coerce")
            bad = binary_raw.isna() | ~binary_raw.isin([0, 1])
            if bad.any():
                values = sorted({str(v) for v in labels["label"][bad].head(20)})
                raise LabelNormalizationError(
                    "binary 'label' must be 0 or 1", details={"unknown_labels": values, "column": "label"}
                )
            binary_raw = binary_raw.astype("int64")
        if not has_cat:
            assert binary_raw is not None
            return NormalizedLabels(original=binary_raw.astype(str), fine=None, category=None, binary=binary_raw)

        original = labels["attack_cat"].astype(object).map(lambda v: "" if v is None else str(v).strip())
        keys = labels["attack_cat"].map(label_key)
        empty = keys == ""
        if empty.any():
            if binary_raw is None:
                raise LabelNormalizationError(
                    "empty attack_cat values and no binary label to disambiguate", details={"column": "attack_cat"}
                )
            # Raw UNSW files leave attack_cat empty for normal traffic; only accept that when label == 0.
            if (binary_raw[empty] != 0).any():
                raise LabelNormalizationError("empty attack_cat on rows labelled as attacks", details={"column": "attack_cat"})
            keys = keys.where(~empty, "normal")
        fine, category = _map_keys(keys, UNSW_LABEL_MAP, column="attack_cat")
        binary = (category != BENIGN_LABEL).astype("int64")
        inconsistent = int((binary != binary_raw).sum()) if binary_raw is not None else 0
        return NormalizedLabels(original=original, fine=fine, category=category, binary=binary, inconsistent_rows=inconsistent)

    raise LabelNormalizationError(f"no label normalization for family {schema.family}")
