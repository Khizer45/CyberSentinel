"""Dataset schemas, header normalization and strict label normalization."""

from __future__ import annotations

import pandas as pd
import pytest

from app.ml.datasets import detect_schema, get_schema
from app.ml.errors import DatasetFormatError, FeatureSchemaError, LabelNormalizationError
from app.ml.preprocessing import label_key, normalize_column_name, normalize_labels, resolve_columns
from tests.fixtures.data import RAW_CIC_FEATURE_HEADERS

CIC = get_schema("cicids2017-flow-v1")
UNSW = get_schema("unsw-nb15-flow-v1")


def test_schemas_are_separate_and_complete() -> None:
    assert len(CIC.features) == 77 and CIC.categorical_features == []
    assert len(UNSW.features) == 42 and UNSW.categorical_features == ["proto", "service", "state"]
    assert not set(CIC.feature_names) & set(UNSW.label_columns)


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        (" Flow Bytes/s", "flow_bytes_s"),
        ("Down/Up Ratio", "down_up_ratio"),
        ("Init_Win_bytes_forward", "init_win_bytes_forward"),
        ("﻿id", "id"),
        (" Fwd Header Length.1", "fwd_header_length_1"),
    ],
)
def test_column_normalization(raw: str, canonical: str) -> None:
    assert normalize_column_name(raw) == canonical


def test_known_cic_duplicate_is_accepted_other_duplicates_rejected() -> None:
    resolution = resolve_columns([*RAW_CIC_FEATURE_HEADERS, " Label"], CIC)
    assert resolution.known_duplicate_positions == {"fwd_header_length": 55}
    assert len(resolution.feature_positions) == 77 and resolution.has_labels
    with pytest.raises(DatasetFormatError) as exc:
        resolve_columns([*RAW_CIC_FEATURE_HEADERS, " Flow Duration", " Label"], CIC)
    assert exc.value.details["duplicate_columns"] == ["flow_duration"]


def test_missing_required_features_listed() -> None:
    with pytest.raises(FeatureSchemaError) as exc:
        resolve_columns(["dur", "proto", "label"], UNSW)
    assert "rate" in exc.value.details["missing_features"]


def test_schema_detection() -> None:
    schema, scores = detect_schema(normalize_column_name(h) for h in RAW_CIC_FEATURE_HEADERS)
    assert schema is CIC and scores["cicids2017-flow-v1"] == 1.0
    schema, _ = detect_schema(["a", "b", "c"])
    assert schema is None


@pytest.mark.parametrize(
    ("raw", "fine", "category"),
    [
        ("BENIGN", "Benign", "Benign"),
        ("Web Attack � XSS", "Web Attack - XSS", "WebAttack"),
        ("Web Attack – Sql Injection", "Web Attack - SQL Injection", "WebAttack"),
        ("FTP-Patator", "FTP-Patator", "BruteForce"),
        ("DoS slowloris", "DoS Slowloris", "DoS"),
    ],
)
def test_cic_label_mapping(raw: str, fine: str, category: str) -> None:
    labels = normalize_labels(pd.DataFrame({"label": [raw]}), CIC)
    assert labels.fine.iloc[0] == fine and labels.category.iloc[0] == category
    assert labels.binary.iloc[0] == (0 if category == "Benign" else 1)


def test_unknown_labels_are_never_silently_mapped() -> None:
    with pytest.raises(LabelNormalizationError) as exc:
        normalize_labels(pd.DataFrame({"label": ["BENIGN", "DoS Hulk - Attempted"]}), CIC)
    assert exc.value.details["unknown_labels"] == [label_key("DoS Hulk - Attempted")]


def test_unsw_variants_and_consistency() -> None:
    frame = pd.DataFrame({"attack_cat": [" Fuzzers ", "Backdoors", "", "Normal"], "label": [1, 1, 0, 1]})
    labels = normalize_labels(frame, UNSW)
    assert list(labels.category) == ["Fuzzers", "Backdoor", "Benign", "Benign"]
    assert labels.inconsistent_rows == 1  # "Normal" with label 1
    with pytest.raises(LabelNormalizationError):
        normalize_labels(pd.DataFrame({"attack_cat": [""], "label": [1]}), UNSW)
