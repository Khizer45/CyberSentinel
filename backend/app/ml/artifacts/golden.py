"""Golden parity fixtures (RTM FR-08, ML-02).

At export time the notebook writes a small sample of canonical input rows to ``golden_input.csv``, reads it
back through :func:`app.ml.preprocessing.reader.iter_canonical_chunks` (exactly like an uploaded dataset)
and records the bundle's outputs in ``golden_expected.json``. The API's ``verify`` command re-runs the
loaded bundle on the same file and compares: identical labels and scores within :data:`SCORE_TOLERANCE`.
A mismatch reveals preprocessing drift, library drift or a corrupted artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.ml.artifacts.bundle import LoadedBundle
from app.ml.artifacts.integrity import safe_resolve, sha256_file
from app.ml.artifacts.manifest import ArtifactFile
from app.ml.constants import AnalysisMode
from app.ml.datasets.registry import get_schema
from app.ml.inference.engine import InferenceEngine
from app.ml.preprocessing.reader import inspect_csv, iter_canonical_chunks

GOLDEN_INPUT_FILE = "golden_input.csv"
GOLDEN_EXPECTED_FILE = "golden_expected.json"
SCORE_TOLERANCE = 1e-9


def preferred_mode(bundle: LoadedBundle) -> AnalysisMode:
    for mode in (AnalysisMode.COMBINED, AnalysisMode.CLASSIFICATION, AnalysisMode.ANOMALY):
        if bundle.supports_mode(mode):
            return mode
    raise ValueError("bundle supports no analysis mode")


def _read_golden_frame(bundle: LoadedBundle, path: Path) -> pd.DataFrame:
    schema = get_schema(bundle.manifest.feature_schema_version)
    names = bundle.manifest.features.input_names
    layout = inspect_csv(path, schema, required_features=names)
    chunks = [c.features for c in iter_canonical_chunks(path, layout, schema, chunk_size=10_000, include_labels=False)]
    return pd.concat(chunks) if chunks else pd.DataFrame(columns=names)


def _outputs(bundle: LoadedBundle, frame: pd.DataFrame, mode: AnalysisMode) -> dict[str, Any]:
    out = InferenceEngine(bundle).predict(frame, mode)

    def arr(values: np.ndarray | None) -> list[Any] | None:
        return None if values is None else values.tolist()

    return {
        "mode": mode.value,
        "rows": out.size,
        "predicted_label": [str(v) for v in out.predicted_label],
        "classifier_score": arr(out.classifier_score),
        "class_probabilities": arr(out.class_probabilities),
        "anomaly_score": arr(out.anomaly_score),
        "is_anomaly": None if out.is_anomaly is None else [bool(v) for v in out.is_anomaly],
    }


def write_golden(bundle: LoadedBundle, frame: pd.DataFrame, bundle_dir: Path) -> tuple[ArtifactFile, ArtifactFile, int]:
    """Write golden input/expected files for ``frame`` (cleaned canonical features)."""
    names = bundle.manifest.features.input_names
    input_path = bundle_dir / GOLDEN_INPUT_FILE
    frame.loc[:, names].to_csv(input_path, index=False, encoding="utf-8")
    reread = _read_golden_frame(bundle, input_path)
    expected = _outputs(bundle, reread, preferred_mode(bundle))
    expected_path = bundle_dir / GOLDEN_EXPECTED_FILE
    expected_path.write_text(json.dumps(expected, allow_nan=False), encoding="utf-8")
    return (
        ArtifactFile(file=GOLDEN_INPUT_FILE, sha256=sha256_file(input_path), size_bytes=input_path.stat().st_size),
        ArtifactFile(file=GOLDEN_EXPECTED_FILE, sha256=sha256_file(expected_path), size_bytes=expected_path.stat().st_size),
        len(reread),
    )


def verify_golden(bundle: LoadedBundle) -> dict[str, Any]:
    """Re-score the golden input with the loaded bundle and compare with the recorded outputs."""
    golden = bundle.manifest.golden
    if golden is None:
        return {"available": False, "passed": None}
    input_path = safe_resolve(bundle.bundle_dir, golden.input.file)
    expected_path = safe_resolve(bundle.bundle_dir, golden.expected.file)
    for path, meta in ((input_path, golden.input), (expected_path, golden.expected)):
        if not path.is_file() or sha256_file(path) != meta.sha256:
            return {"available": True, "passed": False, "reason": "golden file missing or checksum mismatch"}
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    actual = _outputs(bundle, _read_golden_frame(bundle, input_path), AnalysisMode(expected["mode"]))
    label_mismatches = sum(a != e for a, e in zip(actual["predicted_label"], expected["predicted_label"], strict=True))
    max_diff = 0.0
    for key in ("classifier_score", "anomaly_score", "class_probabilities"):
        if expected[key] is None and actual[key] is None:
            continue
        if (expected[key] is None) != (actual[key] is None):
            return {"available": True, "passed": False, "reason": f"{key} presence differs"}
        diff = np.max(np.abs(np.asarray(actual[key], dtype=float) - np.asarray(expected[key], dtype=float)), initial=0.0)
        max_diff = max(max_diff, float(diff))
    passed = label_mismatches == 0 and max_diff <= SCORE_TOLERANCE and actual["rows"] == expected["rows"]
    return {
        "available": True,
        "passed": passed,
        "rows": actual["rows"],
        "label_mismatches": int(label_mismatches),
        "max_score_abs_diff": max_diff,
        "tolerance": SCORE_TOLERANCE,
    }
