"""Persist processed splits and staged (trusted, locally produced) intermediate objects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

SPLITS = ("train", "validation", "test")


def save_splits(splits: dict[str, pd.DataFrame], directory: Path) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, frame in splits.items():
        path = directory / f"{name}.parquet"
        frame.reset_index(drop=True).to_parquet(path, index=False)
        paths[name] = str(path)
    return paths


def load_splits(directory: Path) -> dict[str, pd.DataFrame]:
    missing = [s for s in SPLITS if not (directory / f"{s}.parquet").is_file()]
    if missing:
        raise FileNotFoundError(f"processed splits missing in {directory}: {missing} — run 02_preprocessing first")
    frames = {}
    for name in SPLITS:
        frame = pd.read_parquet(directory / f"{name}.parquet")
        # Parquet may return pandas' string dtype; restore ``object`` so values match what the API's
        # cleaning step produces at inference time (train/serve parity).
        for column in frame.columns:
            if pd.api.types.is_string_dtype(frame[column]) and not pd.api.types.is_object_dtype(frame[column]):
                frame[column] = frame[column].astype(object).where(frame[column].notna(), np.nan)
        frames[name] = frame
    return frames


def save_object(obj: Any, path: Path) -> Path:
    """Stage a fitted object produced by these notebooks (trusted local file, git-ignored)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(obj, path, compress=3)
    return path


def load_object(path: Path) -> Any:
    """Load an object staged by these notebooks. Never use this for files from untrusted sources."""
    return joblib.load(path)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
