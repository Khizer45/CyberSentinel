"""Leakage-aware deduplication and splitting (ML-01).

Order matters: deduplicate *before* splitting, split *before* fitting any transformation, and remove
validation/test rows whose feature vectors also occur in training (near-duplicate leakage).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split


def feature_hash(frame: pd.DataFrame, feature_cols: list[str]) -> pd.Series:
    return pd.util.hash_pandas_object(frame[feature_cols], index=False)


@dataclass
class SplitReport:
    strategy: str
    seed: int
    rows_before_dedup: int = 0
    exact_duplicates_removed: int = 0
    conflicting_rows_removed: int = 0
    rare_classes_train_only: list[str] = field(default_factory=list)
    cross_split_duplicates_removed: dict[str, int] = field(default_factory=dict)
    sizes: dict[str, int] = field(default_factory=dict)
    class_counts: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def deduplicate(frame: pd.DataFrame, feature_cols: list[str], label_col: str, report: SplitReport) -> pd.DataFrame:
    """Drop exact duplicates; drop *all* copies of feature vectors that carry conflicting labels."""
    report.rows_before_dedup = len(frame)
    hashes = feature_hash(frame, feature_cols)
    frame = frame.assign(_fh=hashes.to_numpy())
    before = len(frame)
    frame = frame.drop_duplicates(subset=["_fh", label_col])
    report.exact_duplicates_removed = before - len(frame)
    conflict = frame.groupby("_fh")[label_col].transform("nunique") > 1
    report.conflicting_rows_removed = int(conflict.sum())
    return frame.loc[~conflict].drop(columns="_fh").reset_index(drop=True)


def _stratifiable(frame: pd.DataFrame, label_col: str, min_count: int) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    counts = frame[label_col].value_counts()
    rare = sorted(counts[counts < min_count].index.astype(str).tolist())
    mask = frame[label_col].isin(rare)
    return frame.loc[~mask], frame.loc[mask], rare


def stratified_three_way(
    frame: pd.DataFrame, label_col: str, *, val_size: float, test_size: float, seed: int, report: SplitReport
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Stratified train/validation/test split. Classes too rare to stratify (< 6 rows) stay in train only."""
    main, rare_rows, rare = _stratifiable(frame, label_col, 6)
    report.rare_classes_train_only = rare
    train_val, test = train_test_split(main, test_size=test_size, stratify=main[label_col], random_state=seed)
    relative_val = val_size / (1 - test_size)
    train, val = train_test_split(train_val, test_size=relative_val, stratify=train_val[label_col], random_state=seed)
    return pd.concat([train, rare_rows]), val, test


def official_test_split(
    frame: pd.DataFrame, label_col: str, *, val_size: float, seed: int, report: SplitReport
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """UNSW-NB15: keep the publisher's test partition; carve validation out of the official training partition."""
    official_train = frame[frame["official_split"] == "train"]
    test = frame[frame["official_split"] == "test"]
    main, rare_rows, rare = _stratifiable(official_train, label_col, 4)
    report.rare_classes_train_only = rare
    train, val = train_test_split(main, test_size=val_size, stratify=main[label_col], random_state=seed)
    return pd.concat([train, rare_rows]), val, test


def remove_cross_split_duplicates(
    train: pd.DataFrame, other: pd.DataFrame, feature_cols: list[str], name: str, report: SplitReport
) -> pd.DataFrame:
    """Drop rows of ``other`` whose feature vector also appears in ``train``."""
    seen = set(feature_hash(train, feature_cols).to_numpy().tolist())
    mask = feature_hash(other, feature_cols).isin(seen).to_numpy()
    report.cross_split_duplicates_removed[name] = int(mask.sum())
    return other.loc[~mask]


def assert_disjoint(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame, feature_cols: list[str]) -> None:
    """Fail loudly if any feature vector is shared between splits."""
    h_train = set(feature_hash(train, feature_cols).to_numpy().tolist())
    h_val = set(feature_hash(val, feature_cols).to_numpy().tolist())
    h_test = set(feature_hash(test, feature_cols).to_numpy().tolist())
    assert not (h_train & h_val), "train/validation share feature vectors"
    assert not (h_train & h_test), "train/test share feature vectors"
    assert not (h_val & h_test), "validation/test share feature vectors"


def stratified_sample(frame: pd.DataFrame, label_col: str, n: int, seed: int) -> pd.DataFrame:
    """Stratified subsample of up to ``n`` rows keeping at least one row per class."""
    if len(frame) <= n:
        return frame
    fractions = n / len(frame)
    parts = []
    for _, group in frame.groupby(label_col, sort=True):
        take = max(1, int(round(len(group) * fractions)))
        parts.append(group.sample(min(take, len(group)), random_state=seed))
    return pd.concat(parts).sample(frac=1.0, random_state=seed)


def record_class_counts(report: SplitReport, splits: dict[str, pd.DataFrame], label_col: str) -> None:
    for name, frame in splits.items():
        report.sizes[name] = len(frame)
        report.class_counts[name] = {str(k): int(v) for k, v in frame[label_col].value_counts().sort_index().items()}


def rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)
