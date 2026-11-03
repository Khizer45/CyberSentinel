"""Data-quality audit helpers for notebook 01 (descriptive only; nothing is fitted for deployment)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_classif


def label_distribution(frame: pd.DataFrame, column: str = "label_category") -> pd.DataFrame:
    counts = frame[column].value_counts()
    table = pd.DataFrame({"count": counts, "percent": (100 * counts / counts.sum()).round(4)})
    table.index.name = column
    return table


def imbalance_ratio(frame: pd.DataFrame, column: str = "label_category") -> float:
    counts = frame[column].value_counts()
    return float(counts.max() / counts.min()) if len(counts) > 1 else 1.0


def duplicate_report(frame: pd.DataFrame, feature_cols: list[str], label_col: str = "label_category") -> dict[str, int]:
    exact = int(frame.duplicated(subset=[*feature_cols, label_col]).sum())
    groups = frame.groupby(pd.util.hash_pandas_object(frame[feature_cols], index=False))[label_col].nunique()
    conflicting_groups = int((groups > 1).sum())
    return {"rows": len(frame), "exact_duplicate_rows": exact, "feature_vectors_with_conflicting_labels": conflicting_groups}


def constant_columns(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    return [c for c in columns if frame[c].nunique(dropna=True) <= 1]


def missing_table(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    missing = frame[columns].isna().sum()
    missing = missing[missing > 0].sort_values(ascending=False)
    return pd.DataFrame({"missing": missing, "percent": (100 * missing / len(frame)).round(4)})


def class_conditional_medians(frame: pd.DataFrame, numeric_cols: list[str], label_col: str = "label_category") -> pd.DataFrame:
    return frame.groupby(label_col)[numeric_cols].median().T


def shortcut_screen(
    frame: pd.DataFrame,
    numeric_cols: list[str],
    candidates: list[str],
    *,
    label_col: str = "label_category",
    sample: int = 50_000,
    seed: int = 42,
) -> pd.DataFrame:
    """Mutual information of each numeric feature with the label on a sample.

    High MI for an identifier-like feature (e.g. destination port, TTL) suggests a dataset-specific shortcut.
    The result is descriptive; ablation in notebooks 02/03 decides whether to drop such features.
    """
    data = frame.sample(min(sample, len(frame)), random_state=seed)
    X = data[numeric_cols].fillna(data[numeric_cols].median()).to_numpy()
    y = data[label_col].astype("category").cat.codes.to_numpy()
    mi = mutual_info_classif(X, y, random_state=seed)
    table = pd.DataFrame({"feature": numeric_cols, "mutual_information": mi}).sort_values("mutual_information", ascending=False)
    table["rank"] = np.arange(1, len(table) + 1)
    table["shortcut_candidate"] = table["feature"].isin(candidates)
    return table.reset_index(drop=True)
