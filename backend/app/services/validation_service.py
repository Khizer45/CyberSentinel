"""Server-side validation of uploaded CSV datasets and JSON flow records (FR-04, SEC-04, Security Req. 5.3)."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import Settings
from app.ml.artifacts.bundle import LoadedBundle
from app.ml.datasets import DatasetSchema, detect_schema, get_schema
from app.ml.errors import DatasetFormatError, FeatureSchemaError, LabelNormalizationError
from app.ml.preprocessing import (
    FEATURE_ABS_MAX,
    CleaningStats,
    clean_feature_frame,
    detect_text_encoding,
    inspect_csv,
    iter_canonical_chunks,
    normalize_column_name,
    normalize_labels,
    read_header,
    validate_structure,
)

MAX_CATEGORY_LENGTH = 64


def _top(mapping: dict[str, int], n: int = 20) -> dict[str, int]:
    return dict(sorted(mapping.items(), key=lambda kv: -kv[1])[:n])


@dataclass
class DatasetValidation:
    schema: DatasetSchema
    encoding: str
    row_count: int
    has_ground_truth: bool
    report: dict[str, Any] = field(default_factory=dict)


def resolve_schema(path: Path, encoding: str, schema_version: str | None) -> tuple[DatasetSchema, dict[str, Any]]:
    header = read_header(path, encoding)
    if schema_version:
        try:
            return get_schema(schema_version), {"mode": "explicit"}
        except KeyError:
            raise FeatureSchemaError("unsupported schema_version", details={"schema_version": schema_version}) from None
    schema, coverage = detect_schema(normalize_column_name(h) for h in header)
    if schema is None:
        raise FeatureSchemaError(
            "the columns do not match any supported dataset schema (CIC-IDS2017 or UNSW-NB15)",
            details={"feature_coverage": coverage},
        )
    return schema, {"mode": "auto", "feature_coverage": coverage}


def validate_dataset_file(path: Path, settings: Settings, schema_version: str | None) -> DatasetValidation:
    """Full validation pass. Raises ``DatasetFormatError``/``FeatureSchemaError`` when the file is rejected."""
    encoding = detect_text_encoding(path)
    schema, detection = resolve_schema(path, encoding, schema_version)
    layout = inspect_csv(path, schema, reject_unknown=settings.reject_unknown_columns, encoding=encoding)
    validate_structure(path, encoding, max_rows=settings.max_upload_rows)

    stats = CleaningStats()
    rows = 0
    label_counts: Counter[str] = Counter()
    label_issue: dict[str, Any] | None = None
    for chunk in iter_canonical_chunks(
        path, layout, schema, chunk_size=20_000, max_rows=settings.max_upload_rows, include_identifiers=False
    ):
        stats.merge(chunk.stats)
        rows += len(chunk)
        if chunk.labels is not None and label_issue is None:
            try:
                labels = normalize_labels(chunk.labels, schema)
                source = labels.category if labels.category is not None else labels.binary.map({0: "Benign", 1: "Malicious"})
                label_counts.update(source.astype(str).tolist())
            except LabelNormalizationError as exc:
                label_issue = {"message": exc.message, **exc.details}
    if rows == 0:
        raise DatasetFormatError("the file contains a header but no data rows")

    invalid = {c: round(f, 4) for c, f in stats.invalid_fraction_by_column().items() if f > settings.max_invalid_value_fraction}
    if invalid:
        raise FeatureSchemaError(
            "too many non-numeric or out-of-range values in some columns",
            details={"columns": invalid, "max_invalid_fraction": settings.max_invalid_value_fraction},
        )

    warnings = list(layout.resolution.warnings)
    if label_issue:
        warnings.append("ground-truth labels are present but not usable for evaluation (unknown label values)")
    non_finite_total = sum(stats.non_finite.values())
    if non_finite_total:
        warnings.append(f"{non_finite_total} non-finite numeric values will be treated as missing and imputed")
    cleaning = stats.to_dict()
    has_ground_truth = layout.has_labels and label_issue is None
    report = {
        "accepted": True,
        "encoding": encoding,
        "schema_version": schema.schema_version,
        "schema_detection": detection,
        "columns": layout.resolution.to_report(),
        "rows": rows,
        "data_quality": {
            "non_numeric_values": _top(cleaning["non_numeric_values"]),  # type: ignore[arg-type]
            "non_finite_values": _top(cleaning["non_finite_values"]),  # type: ignore[arg-type]
            "out_of_range_values": _top(cleaning["out_of_range_values"]),  # type: ignore[arg-type]
            "missing_values": _top(cleaning["missing_values"]),  # type: ignore[arg-type]
        },
        "ground_truth": {
            "present": layout.has_labels,
            "usable": has_ground_truth,
            "label_distribution": _top(dict(label_counts), 30),
            "issue": label_issue,
        },
        "warnings": warnings,
    }
    return DatasetValidation(schema=schema, encoding=encoding, row_count=rows, has_ground_truth=has_ground_truth, report=report)


def records_to_frame(
    records: list[dict[str, Any]], bundle: LoadedBundle, schema: DatasetSchema
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Validate JSON flow records against the model's feature contract and return a cleaned frame.

    Keys may use raw or canonical spellings. Unknown keys and invalid values are rejected (422); schema
    features the model does not use are ignored and reported. Missing values (``null``) are imputed by the
    model's preprocessor exactly as for CSV uploads.
    """
    manifest = bundle.manifest
    input_names = manifest.features.input_names
    categorical = {f.name: set(f.categories or []) for f in manifest.features.input_features if f.dtype == "categorical"}
    schema_names = set(schema.feature_names)
    errors: list[dict[str, Any]] = []
    ignored: set[str] = set()
    unseen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        normalized: dict[str, Any] = {}
        for raw_key, value in record.items():
            name = normalize_column_name(str(raw_key))
            name = schema.column_aliases.get(name, name)
            if name not in schema_names:
                errors.append({"record": index, "feature": str(raw_key)[:64], "error": "unknown feature for this model's schema"})
                continue
            if name in normalized:
                errors.append({"record": index, "feature": name, "error": "duplicate feature"})
                continue
            normalized[name] = value
        for name in input_names:
            if name not in normalized:
                errors.append({"record": index, "feature": name, "error": "missing (send null for an unknown value)"})
                continue
            value = normalized[name]
            if value is None:
                continue
            if name in categorical:
                if not isinstance(value, str) or not value.strip() or len(value) > MAX_CATEGORY_LENGTH:
                    errors.append(
                        {
                            "record": index,
                            "feature": name,
                            "error": f"must be a non-empty string of at most {MAX_CATEGORY_LENGTH} characters",
                        }
                    )
                elif categorical[name] and value.strip().lower() not in categorical[name]:
                    unseen.add(name)
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append({"record": index, "feature": name, "error": "must be a number"})
            elif not math.isfinite(float(value)) or abs(float(value)) > FEATURE_ABS_MAX:
                errors.append({"record": index, "feature": name, "error": "must be a finite number within range"})
        ignored.update(set(normalized) - set(input_names))
        rows.append({name: normalized.get(name) for name in input_names})
    if errors:
        raise FeatureSchemaError("one or more records do not match the model's feature contract", details={"errors": errors[:50]})
    frame = pd.DataFrame(rows, columns=input_names)
    for name in input_names:
        if name not in categorical:
            frame[name] = pd.to_numeric(frame[name], errors="coerce")
    cleaned, _stats = clean_feature_frame(frame, schema, input_names)
    warnings = [
        f"value of '{name}' was not seen during training; it is encoded as an unknown category" for name in sorted(unseen)
    ]
    return cleaned, sorted(ignored), warnings
