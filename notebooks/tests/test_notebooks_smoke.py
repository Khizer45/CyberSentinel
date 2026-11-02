"""Execute all six notebooks end-to-end on synthetic raw-format fixtures (smoke test).

Opt-in because it takes a few minutes::

    cd notebooks
    CS_RUN_NOTEBOOK_SMOKE=1 python -m pytest tests -q

Everything is written to temporary directories (raw data, processed splits, reports, model artifacts); the
repository's ``data/``, ``reports/`` and ``model_artifacts/`` are never touched. The synthetic values carry no
meaning — this test proves that the notebook *code paths* run and that exported bundles load through the API's
loader with golden parity, nothing about model quality.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

NOTEBOOKS_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = NOTEBOOKS_DIR.parent / "backend"
ORDER = [
    "01_data_exploration.ipynb",
    "02_preprocessing.ipynb",
    "03_supervised_learning.ipynb",
    "04_unsupervised_learning.ipynb",
    "05_semi_supervised_learning.ipynb",
    "06_model_evaluation.ipynb",
]

pytestmark = pytest.mark.skipif(os.environ.get("CS_RUN_NOTEBOOK_SMOKE") != "1", reason="set CS_RUN_NOTEBOOK_SMOKE=1")


def _run_notebook(path: Path, env: dict[str, str]) -> None:
    import nbformat
    from nbclient import NotebookClient

    previous = dict(os.environ)
    os.environ.update(env)
    try:
        notebook = nbformat.read(path, as_version=4)
        NotebookClient(notebook, timeout=900, kernel_name="python3", resources={"metadata": {"path": str(NOTEBOOKS_DIR)}}).execute()
    finally:
        os.environ.clear()
        os.environ.update(previous)


@pytest.mark.parametrize("family", ["cicids2017", "unsw_nb15"])
def test_notebooks_execute_and_export_loadable_bundles(family: str, tmp_path: Path) -> None:
    sys.path[:0] = [str(BACKEND_DIR), str(NOTEBOOKS_DIR), str(Path(__file__).parent)]
    from synthetic_raw import write_cicids2017, write_unsw_nb15

    raw_dir = tmp_path / "raw"
    (write_cicids2017 if family == "cicids2017" else write_unsw_nb15)(raw_dir)
    model_dir = tmp_path / "model_artifacts"
    env = {
        "CS_DATASET_FAMILY": family,
        "CS_RAW_DIR": str(raw_dir),
        "CS_PROCESSED_DIR": str(tmp_path / "processed"),
        "CS_REPORTS_DIR": str(tmp_path / "reports"),
        "CS_MODEL_DIR": str(model_dir),
        "CS_FAST_MODE": "1",
        "CS_N_JOBS": "2",
        "CS_LINEAR_SAMPLE": "2000",
        "CS_SEMI_POOL_SIZE": "1200",
        "CS_SEMI_EVAL_SIZE": "800",
        "CS_SEMI_SEEDS": "0,1",
        "CS_LABEL_BUDGETS": "0.05,0.2,1.0",
        "CS_CALIBRATE": "1" if family == "unsw_nb15" else "0",
        "CS_EXPORT_SEMI": "1",
        "CS_EXPORT_BINARY": "1",
        "CS_MODEL_VERSION": "0.0.1-smoke",
        "MPLBACKEND": "Agg",
    }
    for name in ORDER:
        _run_notebook(NOTEBOOKS_DIR / name, env)

    from app.ml.artifacts import ExpectedBundle, load_bundle, read_registry, verify_golden
    from app.ml.evaluation.experiment_record import read_experiment

    registry = read_registry(model_dir / "registry.json")
    assert len(registry.bundles) == 3  # multiclass ensemble, binary ensemble, semi-supervised
    for entry in registry.bundles:
        manifest = json.loads((model_dir / entry.path / "manifest.json").read_text())
        bundle = load_bundle(
            model_dir,
            entry.path,
            ExpectedBundle(entry.model_name, entry.version, entry.manifest_sha256, manifest["dataset"]["schema_version"],
                           manifest["preprocessing"]["preprocessing_version"]),
            max_artifact_bytes=2**31,
        )
        assert verify_golden(bundle)["passed"], entry.model_name
    experiments = sorted((model_dir / "experiments").glob("*.json"))
    assert len(experiments) >= 6
    for path in experiments:
        read_experiment(path)
