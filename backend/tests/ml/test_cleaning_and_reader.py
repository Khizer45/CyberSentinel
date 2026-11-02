"""Deterministic cleaning and the streaming CSV reader (FR-04 validation primitives)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.ml.datasets import get_schema
from app.ml.errors import DatasetFormatError
from app.ml.preprocessing import clean_feature_frame, detect_text_encoding, inspect_csv, iter_canonical_chunks, validate_structure
from tests.fixtures.data import cic_traffic_labelling_csv, unsw_csv

UNSW = get_schema("unsw-nb15-flow-v1")
CIC = get_schema("cicids2017-flow-v1")


def test_cleaning_counts_and_neutralizes_invalid_values() -> None:
    frame = pd.DataFrame({name: ["1"] * 5 for name in UNSW.feature_names})
    frame.loc[0, "dur"] = "Infinity"
    frame.loc[1, "dur"] = "abc"
    frame.loc[2, "dur"] = "1e20"
    frame.loc[3, "dur"] = ""
    frame.loc[4, "proto"] = "  TCP "
    cleaned, stats = clean_feature_frame(frame, UNSW)
    assert cleaned["dur"].isna().sum() == 4
    assert stats.non_finite["dur"] == 1 and stats.non_numeric["dur"] == 1 and stats.out_of_range["dur"] == 1
    assert stats.missing["dur"] == 1
    assert cleaned.loc[4, "proto"] == "tcp"
    assert list(cleaned.columns) == UNSW.feature_names and cleaned["dur"].dtype == np.float64


def test_reader_handles_raw_cic_format(tmp_path: Path) -> None:
    path = tmp_path / "cic.csv"
    path.write_bytes(cic_traffic_labelling_csv(rows=30))
    layout = inspect_csv(path, CIC)
    assert layout.encoding == "cp1252"
    chunks = list(iter_canonical_chunks(path, layout, CIC, chunk_size=7))
    assert [c.start_index for c in chunks] == [0, 7, 14, 21, 28]
    assert sum(len(c) for c in chunks) == 30
    assert chunks[0].stats.non_finite.get("flow_bytes_s") == 3
    assert chunks[0].identifiers is not None and "source_ip" in chunks[0].identifiers


def test_reader_rejects_binary_empty_malformed_and_too_many_rows(tmp_path: Path) -> None:
    binary = tmp_path / "b.csv"
    binary.write_bytes(b"\x89PNG\r\n\x00\x00")
    with pytest.raises(DatasetFormatError):
        detect_text_encoding(binary)
    empty = tmp_path / "e.csv"
    empty.write_bytes(b"")
    with pytest.raises(DatasetFormatError):
        detect_text_encoding(empty)
    good = tmp_path / "u.csv"
    good.write_bytes(unsw_csv(rows=20))
    layout = inspect_csv(good, UNSW)
    with pytest.raises(DatasetFormatError):
        list(iter_canonical_chunks(good, layout, UNSW, max_rows=10))
    assert validate_structure(good, "utf-8") == 20
    lines = good.read_text().splitlines()
    for bad_line in (lines[3] + ",extra,fields", ",".join(lines[3].split(",")[:-2])):
        broken = tmp_path / "m.csv"
        broken.write_text("\n".join([*lines[:3], bad_line, *lines[4:]]))
        with pytest.raises(DatasetFormatError) as exc:
            validate_structure(broken, "utf-8")
        assert exc.value.details["row"] == 3
    with pytest.raises(DatasetFormatError):
        validate_structure(good, "utf-8", max_rows=5)
