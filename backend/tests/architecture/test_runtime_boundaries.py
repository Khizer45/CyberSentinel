"""SEC-07: the running API has no code path that trains, tunes or downloads models.

Static checks over ``backend/app`` plus an import check of the application factory.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"
FIT_METHODS = {"fit", "fit_transform", "partial_fit", "fit_predict"}
TUNERS = {"GridSearchCV", "RandomizedSearchCV", "HalvingGridSearchCV", "HalvingRandomSearchCV"}
NETWORK_MODULES = {"requests", "httpx", "httpx2", "urllib.request", "urllib3", "aiohttp", "huggingface_hub", "boto3", "ftplib"}
SERIALIZE_ALLOWED = {"dump": {"ml/artifacts/export.py"}, "load": {"ml/artifacts/loader.py"}}


def python_files() -> list[Path]:
    return [p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_fit_calls_or_tuners_in_app() -> None:
    offenders = []
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in FIT_METHODS:
                offenders.append(f"{path.relative_to(APP_DIR)}:{node.lineno} .{node.func.attr}()")
            if isinstance(node, ast.Name) and node.id in TUNERS:
                offenders.append(f"{path.relative_to(APP_DIR)}:{node.lineno} {node.id}")
    assert offenders == []


def test_no_network_clients_in_app() -> None:
    offenders = []
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name in NETWORK_MODULES or name.split(".")[0] in {
                    "requests",
                    "httpx",
                    "httpx2",
                    "aiohttp",
                    "huggingface_hub",
                    "boto3",
                }:
                    offenders.append(f"{path.relative_to(APP_DIR)}:{node.lineno} imports {name}")
    assert offenders == []


def test_joblib_dump_and_load_confined() -> None:
    offenders = []
    for path in python_files():
        rel = str(path.relative_to(APP_DIR)).replace("\\", "/")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"joblib", "pickle"}
                and node.func.attr in SERIALIZE_ALLOWED
                and rel not in SERIALIZE_ALLOWED[node.func.attr]
            ):
                offenders.append(f"{rel}:{node.lineno} {node.func.value.id}.{node.func.attr}")
    assert offenders == []


def test_application_does_not_import_training_or_export_code() -> None:
    code = (
        "import sys, app.main, app.cli;"
        "bad=[m for m in sys.modules if m.startswith('nb_utils') or m=='app.ml.artifacts.export'"
        " or m.startswith('sklearn.model_selection._search')];"
        "print(','.join(bad))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=APP_DIR.parent, check=True)
    assert result.stdout.strip() == ""
