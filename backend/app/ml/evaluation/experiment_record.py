"""Contract for experiment results exported by the notebooks and served read-only by ``/experiments``.

Keeping the schema here (shared by notebooks and API) means a notebook cannot write a file the API would
misinterpret, and the API never displays numbers that a notebook did not produce.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ml.artifacts.manifest import RuntimeSection
from app.ml.constants import DatasetFamily

ExperimentType = Literal[
    "semi_supervised_label_budget",
    "supervised_comparison",
    "anomaly_detection",
    "unknown_attack_holdout",
    "risk_policy_evaluation",
]
Scalar = str | int | float | bool | None
MAX_EXPERIMENT_BYTES = 2 * 1024 * 1024


class ExperimentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,99}$")
    experiment_type: ExperimentType
    title: str = Field(max_length=200)
    dataset_family: DatasetFamily
    schema_version: str
    created_at: datetime
    config: dict[str, Any] = Field(default_factory=dict)
    columns: dict[str, str] = Field(default_factory=dict, description="column name -> description/units")
    rows: list[dict[str, Scalar]] = Field(default_factory=list, max_length=20_000)
    summary: dict[str, Any] = Field(default_factory=dict)
    runtime: RuntimeSection
    notes: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("rows")
    @classmethod
    def _finite(cls, rows: list[dict[str, Scalar]]) -> list[dict[str, Scalar]]:
        json.dumps(rows, allow_nan=False)
        return rows


def write_experiment(record: ExperimentRecord, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record.experiment_id}.json"
    payload = json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True, allow_nan=False)
    if len(payload.encode("utf-8")) > MAX_EXPERIMENT_BYTES:
        raise ValueError("experiment record exceeds 2 MiB; reduce the number of rows")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(payload + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def read_experiment(path: Path) -> ExperimentRecord:
    if path.stat().st_size > MAX_EXPERIMENT_BYTES:
        raise ValueError("experiment file too large")
    return ExperimentRecord.model_validate_json(path.read_bytes())
