"""Adapters between validated inputs and a model's feature contract (Workflow Manual 7.2)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.errors import UnprocessableError
from app.ml.constants import ModelType
from app.ml.datasets import DatasetSchema
from app.models import Dataset, ModelVersion
from app.utils.ip import pseudonymize_ip

SUPPORTED_MODES: dict[str, list[str]] = {
    ModelType.ENSEMBLE.value: ["classification", "anomaly", "combined"],
    ModelType.CLASSIFIER.value: ["classification"],
    ModelType.SEMI_SUPERVISED.value: ["classification"],
    ModelType.ANOMALY_DETECTOR.value: ["anomaly"],
}


def supported_modes(model_type: str) -> list[str]:
    return SUPPORTED_MODES.get(model_type, [])


def ensure_compatible(dataset: Dataset, model: ModelVersion, mode: str) -> None:
    if dataset.schema_version != model.feature_schema_version:
        raise UnprocessableError(
            "The dataset's feature schema does not match the selected model.",
            code="incompatible_dataset",
            details={"dataset_schema": dataset.schema_version, "model_schema": model.feature_schema_version},
        )
    if mode not in supported_modes(model.model_type):
        raise UnprocessableError(
            "The selected model does not support this analysis mode.",
            code="unsupported_mode",
            details={"supported_modes": supported_modes(model.model_type)},
        )


def _port(value: Any) -> int | None:
    try:
        port = int(float(value))
    except (TypeError, ValueError):
        return None
    return port if 0 <= port <= 65535 else None


def build_flow_contexts(context: pd.DataFrame | None, schema: DatasetSchema, ip_key: bytes | None) -> list[dict[str, Any] | None]:
    """Allowlisted flow context per row; IPs are pseudonymized (or dropped when no key is configured)."""
    if context is None or context.empty:
        return []
    records: list[dict[str, Any] | None] = []
    columns = list(context.columns)
    for values in context.itertuples(index=False, name=None):
        item: dict[str, Any] = {}
        for key, value in zip(columns, values, strict=True):
            if value is None or (isinstance(value, float) and pd.isna(value)) or (isinstance(value, str) and not value.strip()):
                continue
            if key in schema.ip_context_keys:
                token = pseudonymize_ip(str(value), ip_key)
                if token:
                    item[key] = token
            elif key in {"src_port", "dst_port"}:
                port = _port(value)
                if port is not None:
                    item[key] = port
            elif key == "protocol":
                item[key] = str(value).strip()[:16]
            elif key == "timestamp":
                item[key] = str(value).strip()[:40]
        records.append(item or None)
    return records
