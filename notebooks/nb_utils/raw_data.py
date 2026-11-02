"""Discover and load the official raw CSV files into canonical, cleaned frames.

The column resolution, duplicate handling, cleaning and label normalization come from ``app.ml`` (the same
code the API uses on uploads). Loading uses pandas type inference instead of ``dtype=str`` because the full
datasets do not fit in memory as strings.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.ml.datasets import DatasetSchema, get_schema_for_family
from app.ml.errors import DatasetFormatError
from app.ml.preprocessing import CleaningStats, clean_feature_frame, detect_text_encoding, normalize_labels, read_header, resolve_columns
from app.ml.preprocessing.cleaning import numeric_equal

UNSW_PARTITION_FILES = {"train": "UNSW_NB15_training-set.csv", "test": "UNSW_NB15_testing-set.csv"}
LABEL_COLUMNS = ["label_original", "label_fine", "label_category", "label_binary"]


@dataclass
class RawLoadReport:
    files: list[dict[str, object]] = field(default_factory=list)
    cleaning: CleaningStats = field(default_factory=CleaningStats)
    header_mappings: dict[str, dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {"files": self.files, "cleaning": self.cleaning.to_dict(), "header_mappings": self.header_mappings}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def discover_raw_files(raw_dir: Path, family: str) -> list[tuple[str, Path]]:
    """Return ``(official_split, path)`` pairs. ``official_split`` is ``"none"`` for CIC-IDS2017."""
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"raw data directory not found: {raw_dir} (see data/README.md)")
    if family == "unsw_nb15":
        files = []
        for split, name in UNSW_PARTITION_FILES.items():
            path = raw_dir / name
            if not path.is_file():
                raise FileNotFoundError(f"missing {name} in {raw_dir}")
            files.append((split, path))
        return files
    csvs = sorted(p for p in raw_dir.glob("*.csv") if p.is_file())
    if not csvs:
        raise FileNotFoundError(f"no CSV files found in {raw_dir}")
    return [("none", p) for p in csvs]


def load_raw_file(path: Path, schema: DatasetSchema, *, max_rows: int | None = None) -> tuple[pd.DataFrame, CleaningStats, dict[str, object]]:
    """Load one raw file → canonical features + normalized label columns + provenance columns."""
    encoding = detect_text_encoding(path)
    header = read_header(path, encoding)
    resolution = resolve_columns(header, schema)
    names = [f"c{i}" for i in range(len(header))]
    wanted = {pos: name for name, pos in resolution.feature_positions.items()}
    wanted.update({pos: name for name, pos in resolution.label_positions.items()})
    dup = dict(resolution.known_duplicate_positions)
    for feature, pos in dup.items():
        wanted[pos] = f"__duplicate__{feature}"
    raw = pd.read_csv(
        path,
        header=0,
        names=names,
        usecols=[names[i] for i in sorted(wanted)],
        encoding="utf-8-sig" if encoding == "utf-8" else encoding,
        low_memory=False,
        nrows=max_rows,
        compression=None,
    ).rename(columns={names[i]: wanted[i] for i in wanted})
    for feature in dup:
        if not numeric_equal(raw[feature], raw[f"__duplicate__{feature}"]):
            raise DatasetFormatError(f"{path.name}: duplicated column for {feature!r} differs from the original")
        raw = raw.drop(columns=[f"__duplicate__{feature}"])
    features, stats = clean_feature_frame(raw, schema)
    labels = normalize_labels(raw[[c for c in schema.label_columns if c in raw.columns]], schema)
    if labels.category is None:
        raise DatasetFormatError(f"{path.name}: multi-class labels are required for training")
    frame = features.copy()
    frame["label_original"] = labels.original.to_numpy()
    frame["label_fine"] = labels.fine.to_numpy() if labels.fine is not None else labels.category.to_numpy()
    frame["label_category"] = labels.category.to_numpy()
    frame["label_binary"] = labels.binary.to_numpy()
    frame["source_file"] = path.name
    frame["source_row"] = range(len(frame))
    info = {
        "file": path.name,
        "sha256": sha256_file(path),
        "encoding": encoding,
        "rows_loaded": len(frame),
        "row_cap": max_rows,
        "unknown_columns": list(resolution.unknown_columns),
        "known_duplicates_dropped": sorted(dup),
        "label_inconsistencies": labels.inconsistent_rows,
    }
    mapping = {raw_name: resolution.canonical_names[i] for i, raw_name in enumerate(header)}
    return frame, stats, {"info": info, "mapping": mapping}


def load_family(raw_dir: Path, family: str, *, max_rows_per_file: int | None = None) -> tuple[pd.DataFrame, RawLoadReport]:
    """Load all raw files of a family. Adds ``official_split`` (``train``/``test`` for UNSW, ``none`` for CIC)."""
    schema = get_schema_for_family(family)
    report = RawLoadReport()
    frames = []
    for split, path in discover_raw_files(raw_dir, family):
        frame, stats, meta = load_raw_file(path, schema, max_rows=max_rows_per_file)
        frame["official_split"] = split
        frames.append(frame)
        report.cleaning.merge(stats)
        report.files.append(meta["info"])  # type: ignore[arg-type]
        report.header_mappings[path.name] = meta["mapping"]  # type: ignore[assignment]
    data = pd.concat(frames, ignore_index=True)
    return data, report
