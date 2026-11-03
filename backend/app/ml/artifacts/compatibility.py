"""Runtime library compatibility checks for pickled artifacts.

Pickles produced by scikit-learn / XGBoost are only reliable with the same minor version that wrote
them. The manifest records the exporting environment; the loader refuses mismatches (fail closed).
"""

from __future__ import annotations

import platform
from importlib import metadata

from app.ml.artifacts.manifest import RuntimeSection


def _version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def current_runtime() -> RuntimeSection:
    return RuntimeSection(
        python=platform.python_version(),
        numpy=_version("numpy") or "unknown",
        pandas=_version("pandas") or "unknown",
        scikit_learn=_version("scikit-learn") or "unknown",
        xgboost=_version("xgboost"),
        joblib=_version("joblib") or "unknown",
    )


def _major_minor(version: str | None) -> tuple[str, ...]:
    if not version:
        return ()
    return tuple(version.split(".")[:2])


def _major(version: str | None) -> str:
    return version.split(".")[0] if version else ""


def compatibility_problems(recorded: RuntimeSection, *, uses_xgboost: bool) -> list[str]:
    """Return human-readable incompatibilities (empty list = compatible)."""
    current = current_runtime()
    problems: list[str] = []
    if _major_minor(recorded.scikit_learn) != _major_minor(current.scikit_learn):
        problems.append(f"scikit-learn {recorded.scikit_learn} was used for export but {current.scikit_learn} is installed")
    if _major(recorded.numpy) != _major(current.numpy):
        problems.append(f"numpy major version {recorded.numpy} differs from installed {current.numpy}")
    if uses_xgboost:
        if current.xgboost is None:
            problems.append("the bundle requires xgboost, which is not installed")
        elif _major_minor(recorded.xgboost) != _major_minor(current.xgboost):
            problems.append(f"xgboost {recorded.xgboost} was used for export but {current.xgboost} is installed")
    return problems
