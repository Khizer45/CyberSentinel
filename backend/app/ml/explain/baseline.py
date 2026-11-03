"""Model-agnostic baseline-deviation heuristic (used when no attribution method fits, and for anomalies).

For numeric features a robust z-score ``(x − median) / (IQR / 1.349)`` is computed against the *benign
training* reference stored in the manifest; categorical features score 1 when the value differs from the
most frequent benign value. Scores are weighted by normalized global importance when available. This is a
heuristic description of how unusual inputs are — not a model attribution and not a causal explanation.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from app.ml.artifacts.manifest import FeatureReference


def robust_scale(ref: FeatureReference) -> float | None:
    if ref.median is None:
        return None
    if ref.q25 is not None and ref.q75 is not None and ref.q75 > ref.q25:
        return (ref.q75 - ref.q25) / 1.349
    return max(abs(ref.median) * 0.1, 1e-9)


def deviation_scores(
    row: pd.Series,
    input_names: Sequence[str],
    categorical: set[str],
    references: Mapping[str, FeatureReference],
    importance: Mapping[str, float],
) -> list[tuple[str, float, float]]:
    """Return ``(feature, weighted_score, signed_deviation)`` for every feature with a reference."""
    max_importance = max(importance.values(), default=0.0)
    results: list[tuple[str, float, float]] = []
    for name in input_names:
        ref = references.get(name)
        if ref is None:
            continue
        weight = (importance.get(name, 0.0) / max_importance) if max_importance > 0 else 1.0
        weight = 0.25 + 0.75 * weight  # keep unimportant-but-extreme features visible
        value = row[name]
        if name in categorical:
            if ref.mode is None or value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            deviation = 0.0 if str(value) == ref.mode else 1.0
            results.append((name, deviation * weight, deviation))
            continue
        scale = robust_scale(ref)
        if scale is None or value is None or (isinstance(value, float) and np.isnan(value)):
            continue
        z = (float(value) - float(ref.median)) / scale  # type: ignore[arg-type]
        z = float(np.clip(z, -1e6, 1e6))
        results.append((name, abs(z) * weight, z))
    return results
