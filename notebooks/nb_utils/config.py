"""Notebook configuration and path bootstrap.

All settings come from environment variables (with defaults suitable for a laptop), so the same notebooks
can be run interactively, in a smoke test against synthetic fixtures, or on a larger machine without edits.

| Variable | Default | Meaning |
|---|---|---|
| ``CS_DATASET_FAMILY`` | ``cicids2017`` | ``cicids2017`` or ``unsw_nb15`` |
| ``CS_RANDOM_SEED`` | ``42`` | global seed for splits, sampling and estimators |
| ``CS_RAW_DIR`` | ``data/raw/<family>`` | directory with the official CSV files |
| ``CS_PROCESSED_DIR`` | ``data/processed/<family>`` | processed splits + fitted preprocessor |
| ``CS_REPORTS_DIR`` | ``reports/<family>`` | metrics, tables and figures |
| ``CS_MODEL_DIR`` | ``model_artifacts`` | MODEL_DIR used by the backend (bundles, registry, experiments) |
| ``CS_MAX_ROWS_PER_FILE`` | unset | cap rows per raw file (quick iteration only — never for final results) |
| ``CS_N_JOBS`` | ``-1`` | parallelism for scikit-learn / XGBoost |
| ``CS_FAST_MODE`` | ``0`` | ``1`` = tiny models (smoke tests only) |
| ``CS_LINEAR_SAMPLE`` | ``200000`` | training subsample for logistic regression / linear SVM |
| ``CS_SEMI_POOL_SIZE`` | ``20000`` | stratified training pool for label-propagation experiments |
| ``CS_SEMI_EVAL_SIZE`` | ``20000`` | stratified evaluation sample for those experiments |
| ``CS_SEMI_SEEDS`` | ``0,1,2`` | seeds repeated per label budget |
| ``CS_LABEL_BUDGETS`` | ``0.01,0.05,0.1,0.2,0.4,1.0`` | label fractions (SRS 1.4) |
| ``CS_DROP_SHORTCUT_FEATURES`` | ``0`` | ``1`` = drop the schema's shortcut-feature candidates (ablation) |
| ``CS_RUN_HOLDOUT`` | ``1`` | run the unknown-attack hold-out experiment in notebook 04 |
| ``CS_CALIBRATE`` | ``0`` | ``1`` = calibrate the selected classifier on half of the validation split |
| ``CS_MODEL_VERSION`` | ``1.0.0`` | version written to the exported bundle |
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "backend" / "app" / "ml").is_dir() and (candidate / "notebooks").is_dir():
            return candidate
    raise RuntimeError("could not locate the CyberSentinel project root (expected backend/app/ml and notebooks/)")


def bootstrap(start: Path | None = None) -> Path:
    """Make ``app.ml`` (backend) and ``nb_utils`` importable; return the project root."""
    root = find_project_root(start)
    for path in (root / "backend", root / "notebooks"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    return root


def _env_int(name: str, default: int | None) -> int | None:
    value = os.environ.get(name)
    return int(value) if value not in (None, "") else default


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    return default if value in (None, "") else value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str, cast: type) -> list:  # type: ignore[type-arg]
    return [cast(item.strip()) for item in os.environ.get(name, default).split(",") if item.strip()]


@dataclass
class NotebookConfig:
    project_root: Path
    family: str
    seed: int
    raw_dir: Path
    processed_dir: Path
    reports_dir: Path
    model_dir: Path
    max_rows_per_file: int | None
    n_jobs: int
    fast_mode: bool
    linear_sample: int
    semi_pool_size: int
    semi_eval_size: int
    semi_seeds: list[int] = field(default_factory=list)
    label_budgets: list[float] = field(default_factory=list)
    drop_shortcut_features: bool = False
    run_holdout: bool = True
    calibrate: bool = False
    model_version: str = "1.0.0"

    @property
    def staging_dir(self) -> Path:
        return self.model_dir / "staging" / self.family

    @property
    def figures_dir(self) -> Path:
        return self.reports_dir / "figures"

    @property
    def experiments_dir(self) -> Path:
        return self.model_dir / "experiments"

    def ensure_dirs(self) -> None:
        for path in (self.processed_dir, self.reports_dir, self.figures_dir, self.staging_dir, self.experiments_dir):
            path.mkdir(parents=True, exist_ok=True)

    def describe(self) -> dict[str, object]:
        return {
            k: (str(v) if isinstance(v, Path) else v)
            for k, v in self.__dict__.items()
            if k != "project_root"
        }


def load_config(start: Path | None = None) -> NotebookConfig:
    root = bootstrap(start)
    family = os.environ.get("CS_DATASET_FAMILY", "cicids2017").strip().lower()
    if family not in {"cicids2017", "unsw_nb15"}:
        raise ValueError("CS_DATASET_FAMILY must be 'cicids2017' or 'unsw_nb15'")

    def path(var: str, default: Path) -> Path:
        value = os.environ.get(var)
        return Path(value).expanduser().resolve() if value else default

    config = NotebookConfig(
        project_root=root,
        family=family,
        seed=_env_int("CS_RANDOM_SEED", 42) or 42,
        raw_dir=path("CS_RAW_DIR", root / "data" / "raw" / family),
        processed_dir=path("CS_PROCESSED_DIR", root / "data" / "processed" / family),
        reports_dir=path("CS_REPORTS_DIR", root / "reports" / family),
        model_dir=path("CS_MODEL_DIR", root / "model_artifacts"),
        max_rows_per_file=_env_int("CS_MAX_ROWS_PER_FILE", None),
        n_jobs=_env_int("CS_N_JOBS", -1) or -1,
        fast_mode=_env_flag("CS_FAST_MODE"),
        linear_sample=_env_int("CS_LINEAR_SAMPLE", 200_000) or 200_000,
        semi_pool_size=_env_int("CS_SEMI_POOL_SIZE", 20_000) or 20_000,
        semi_eval_size=_env_int("CS_SEMI_EVAL_SIZE", 20_000) or 20_000,
        semi_seeds=_env_list("CS_SEMI_SEEDS", "0,1,2", int),
        label_budgets=_env_list("CS_LABEL_BUDGETS", "0.01,0.05,0.1,0.2,0.4,1.0", float),
        drop_shortcut_features=_env_flag("CS_DROP_SHORTCUT_FEATURES"),
        run_holdout=_env_flag("CS_RUN_HOLDOUT", True),
        calibrate=_env_flag("CS_CALIBRATE"),
        model_version=os.environ.get("CS_MODEL_VERSION", "1.0.0"),
    )
    config.ensure_dirs()
    return config
