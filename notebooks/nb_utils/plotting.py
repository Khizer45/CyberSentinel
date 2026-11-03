"""Matplotlib figures for the notebooks (saved under reports/<family>/figures)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import PrecisionRecallDisplay, RocCurveDisplay


def _save(fig: plt.Figure, path: Path | None) -> plt.Figure:
    fig.tight_layout()
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=120)
    return fig


def confusion_heatmap(matrix: Sequence[Sequence[int]], labels: Sequence[str], title: str, path: Path | None = None, normalize: bool = True) -> plt.Figure:
    data = np.asarray(matrix, dtype=float)
    if normalize:
        sums = data.sum(axis=1, keepdims=True)
        data = np.divide(data, sums, out=np.zeros_like(data), where=sums > 0)
    fig, ax = plt.subplots(figsize=(1.1 * len(labels) + 2, 1.0 * len(labels) + 1.5))
    image = ax.imshow(data, cmap="Blues", vmin=0, vmax=1 if normalize else None)
    ax.set_xticks(range(len(labels)), labels=labels, rotation=45, ha="right")
    ax.set_yticks(range(len(labels)), labels=labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, f"{data[i, j]:.2f}" if normalize else int(data[i, j]), ha="center", va="center", fontsize=7)
    fig.colorbar(image, ax=ax, fraction=0.046)
    return _save(fig, path)


def roc_pr_curves(y_true: np.ndarray, scores: np.ndarray, title: str, path: Path | None = None) -> plt.Figure:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    if len(np.unique(y_true)) > 1:
        RocCurveDisplay.from_predictions(y_true, scores, ax=axes[0])
        PrecisionRecallDisplay.from_predictions(y_true, scores, ax=axes[1])
    axes[0].set_title(f"{title} — ROC")
    axes[1].set_title(f"{title} — Precision/Recall")
    return _save(fig, path)


def threshold_curve(analysis: list[dict], title: str, path: Path | None = None) -> plt.Figure:
    table = pd.DataFrame(analysis)
    fig, ax = plt.subplots(figsize=(7, 4))
    for column in ("precision", "recall", "f1", "false_positive_rate"):
        ax.plot(table["threshold"], table[column], marker="o", markersize=3, label=column)
    ax.set_xlabel("decision threshold")
    ax.set_title(title)
    ax.legend()
    ax.grid(alpha=0.3)
    return _save(fig, path)


def feature_importance_bar(importance: pd.Series, title: str, path: Path | None = None, top: int = 20) -> plt.Figure:
    data = importance.sort_values(ascending=True).tail(top)
    fig, ax = plt.subplots(figsize=(7, 0.3 * len(data) + 1.5))
    ax.barh(data.index, data.values)
    ax.set_title(title)
    return _save(fig, path)


def score_histogram(scores: np.ndarray, groups: np.ndarray, threshold: float, title: str, path: Path | None = None) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, 4))
    for group in np.unique(groups):
        ax.hist(scores[groups == group], bins=60, alpha=0.5, density=True, label=str(group))
    ax.axvline(threshold, color="red", linestyle="--", label=f"threshold {threshold:.3f}")
    ax.set_xlabel("anomaly score (higher = more anomalous)")
    ax.set_title(title)
    ax.legend()
    return _save(fig, path)


def label_budget_curve(results: pd.DataFrame, metric: str, title: str, path: Path | None = None) -> plt.Figure:
    grouped = results.groupby(["method", "label_budget"])[metric].agg(["mean", "std"]).reset_index()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for method, group in grouped.groupby("method"):
        ax.errorbar(100 * group["label_budget"], group["mean"], yerr=group["std"].fillna(0), marker="o", capsize=3, label=method)
    ax.set_xscale("log")
    ax.set_xlabel("labelled fraction of training pool (%)")
    ax.set_ylabel(metric)
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend()
    return _save(fig, path)


def scatter_2d(points: np.ndarray, colors: np.ndarray, title: str, path: Path | None = None) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(7, 5))
    for value in np.unique(colors):
        mask = colors == value
        ax.scatter(points[mask, 0], points[mask, 1], s=4, alpha=0.5, label=str(value))
    ax.set_title(title)
    ax.legend(markerscale=3, fontsize=7)
    return _save(fig, path)
