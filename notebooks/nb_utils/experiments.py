"""Write experiment results in the shared :class:`ExperimentRecord` format (served read-only by the API)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.ml.artifacts.compatibility import current_runtime
from app.ml.artifacts.export import to_jsonable
from app.ml.datasets import get_schema_for_family
from app.ml.evaluation.experiment_record import ExperimentRecord, write_experiment


def save_json(data: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(data), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return path


def record_experiment(
    *,
    experiment_id: str,
    experiment_type: str,
    title: str,
    family: str,
    rows: pd.DataFrame | list[dict[str, Any]],
    columns: dict[str, str],
    config: dict[str, Any],
    summary: dict[str, Any],
    notes: list[str],
    experiments_dir: Path,
    reports_dir: Path,
) -> Path:
    """Validate and write an experiment to ``model_artifacts/experiments`` (API) and ``reports/`` (CSV copy)."""
    records = rows.to_dict(orient="records") if isinstance(rows, pd.DataFrame) else rows
    schema = get_schema_for_family(family)
    record = ExperimentRecord(
        experiment_id=experiment_id,
        experiment_type=experiment_type,  # type: ignore[arg-type]
        title=title,
        dataset_family=family,  # type: ignore[arg-type]
        schema_version=schema.schema_version,
        created_at=datetime.now(UTC),
        config=to_jsonable(config),
        columns=columns,
        rows=to_jsonable(records),
        summary=to_jsonable(summary),
        runtime=current_runtime(),
        notes=notes,
    )
    path = write_experiment(record, experiments_dir)
    pd.DataFrame(records).to_csv(reports_dir / f"{experiment_id}.csv", index=False)
    return path
