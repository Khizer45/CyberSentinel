"""Streaming CSV reader that turns an untrusted flow CSV into canonical, cleaned chunks.

Used by the API (upload validation and analysis jobs) and by the notebooks, so both sides apply the
same header resolution, duplicate handling, cleaning and label normalization.

Security notes: files are read as text with explicit ``compression=None`` (no implicit decompression),
``dtype=str`` (no type coercion surprises), the C parser and ``on_bad_lines="error"``. Nothing in the
file is ever evaluated or executed.
"""

from __future__ import annotations

import codecs
import csv
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.ml.datasets.base import DatasetSchema
from app.ml.errors import DatasetFormatError
from app.ml.preprocessing.cleaning import CleaningStats, clean_feature_frame, numeric_equal
from app.ml.preprocessing.columns import ColumnResolution, resolve_columns

SUPPORTED_ENCODINGS = ("utf-8", "cp1252")
_BINARY_PROBE_BYTES = 64 * 1024
_SCAN_CHUNK_BYTES = 1024 * 1024


def detect_text_encoding(path: Path) -> str:
    """Return ``"utf-8"`` or ``"cp1252"`` for a text CSV, or raise :class:`DatasetFormatError`.

    UTF-8 (optionally with BOM) is the supported encoding. Windows-1252 is accepted as a fallback because
    the official CIC-IDS2017 CSVs encode the en dash in web-attack labels as byte 0x96.
    Files containing NUL bytes are rejected as binary.
    """
    with path.open("rb") as handle:
        probe = handle.read(_BINARY_PROBE_BYTES)
    if not probe:
        raise DatasetFormatError("the file is empty")
    if b"\x00" in probe:
        raise DatasetFormatError("the file appears to be binary, not a CSV text file")

    for encoding in SUPPORTED_ENCODINGS:
        decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
        try:
            with path.open("rb") as handle:
                while chunk := handle.read(_SCAN_CHUNK_BYTES):
                    if b"\x00" in chunk:
                        raise DatasetFormatError("the file contains NUL bytes and is not a valid CSV text file")
                    decoder.decode(chunk)
                decoder.decode(b"", final=True)
            return encoding
        except UnicodeDecodeError:
            continue
    raise DatasetFormatError("unsupported text encoding; save the CSV as UTF-8")


def read_header(path: Path, encoding: str) -> list[str]:
    """Read the header row with the ``csv`` module (duplicate names are preserved)."""
    with path.open("r", encoding="utf-8-sig" if encoding == "utf-8" else encoding, newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise DatasetFormatError("the file has no header row") from None
        except csv.Error as exc:
            raise DatasetFormatError("the header row is not valid CSV") from exc
    if len(header) < 2:
        raise DatasetFormatError("the header must contain comma-separated column names")
    return header


@dataclass(frozen=True)
class CsvLayout:
    """Resolved structure of a CSV file for a given schema."""

    encoding: str
    resolution: ColumnResolution
    feature_names: tuple[str, ...]

    @property
    def has_labels(self) -> bool:
        return self.resolution.has_labels


def inspect_csv(
    path: Path,
    schema: DatasetSchema,
    *,
    required_features: Sequence[str] | None = None,
    reject_unknown: bool = False,
    encoding: str | None = None,
) -> CsvLayout:
    """Detect the encoding, read the header and resolve it against ``schema`` (fail fast)."""
    encoding = encoding or detect_text_encoding(path)
    header = read_header(path, encoding)
    resolution = resolve_columns(header, schema, required_features=required_features, reject_unknown=reject_unknown)
    features = tuple(required_features) if required_features is not None else tuple(resolution.feature_positions)
    return CsvLayout(encoding=encoding, resolution=resolution, feature_names=features)


@dataclass
class CanonicalChunk:
    """One chunk of cleaned, canonical data.

    ``start_index`` is the 0-based index of the first data row of the chunk within the file (header excluded),
    so ``start_index + i`` is the ERD ``predictions.record_index`` of row ``i``.
    """

    start_index: int
    features: pd.DataFrame
    labels: pd.DataFrame | None
    identifiers: pd.DataFrame | None
    stats: CleaningStats

    def __len__(self) -> int:
        return len(self.features)


def iter_canonical_chunks(
    path: Path,
    layout: CsvLayout,
    schema: DatasetSchema,
    *,
    chunk_size: int = 5000,
    max_rows: int | None = None,
    include_labels: bool = True,
    include_identifiers: bool = True,
) -> Iterator[CanonicalChunk]:
    """Yield cleaned chunks with canonical column names.

    Raises :class:`DatasetFormatError` for malformed rows, rows beyond ``max_rows``, or a known duplicate
    column whose values differ from the original.
    """
    resolution = layout.resolution
    # Unique placeholder names for every raw position avoid pandas' duplicate mangling.
    names = [f"c{i}" for i in range(len(resolution.raw_headers))]
    wanted: dict[int, str] = {resolution.feature_positions[f]: f for f in layout.feature_names}
    dup_positions = {
        feature: position
        for feature, position in resolution.known_duplicate_positions.items()
        if feature in resolution.feature_positions
    }
    for feature, position in dup_positions.items():
        wanted[position] = f"__duplicate__{feature}"
        wanted.setdefault(resolution.feature_positions[feature], feature)
    if include_labels:
        wanted.update({pos: name for name, pos in resolution.label_positions.items()})
    if include_identifiers:
        wanted.update({pos: name for name, pos in resolution.identifier_positions.items()})
    usecols = sorted(wanted)

    try:
        reader = pd.read_csv(
            path,
            header=0,
            names=names,
            usecols=[names[i] for i in usecols],
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig" if layout.encoding == "utf-8" else layout.encoding,
            compression=None,
            engine="c",
            on_bad_lines="error",
            skip_blank_lines=True,
            chunksize=chunk_size,
        )
    except (ValueError, pd.errors.ParserError) as exc:
        raise DatasetFormatError("the CSV structure could not be parsed") from exc

    offset = 0
    try:
        for raw in reader:
            if max_rows is not None and offset + len(raw) > max_rows:
                raise DatasetFormatError(
                    f"the file exceeds the maximum of {max_rows:,} data rows", details={"max_rows": max_rows}
                )
            raw = raw.rename(columns={names[i]: wanted[i] for i in usecols})
            for feature in dup_positions:
                if not numeric_equal(raw[feature], raw[f"__duplicate__{feature}"]):
                    raise DatasetFormatError(
                        f"the duplicated '{feature}' column differs from the original column",
                        details={"column": feature},
                    )
            features, stats = clean_feature_frame(raw, schema, list(layout.feature_names))
            label_cols = [c for c in schema.label_columns if c in raw.columns] if include_labels else []
            ident_cols = [c for c in schema.identifier_columns if c in raw.columns] if include_identifiers else []
            index = pd.RangeIndex(offset, offset + len(raw))
            features.index = index
            labels = raw[label_cols].set_axis(index) if label_cols else None
            identifiers = raw[ident_cols].set_axis(index) if ident_cols else None
            yield CanonicalChunk(start_index=offset, features=features, labels=labels, identifiers=identifiers, stats=stats)
            offset += len(raw)
    except pd.errors.ParserError as exc:
        raise DatasetFormatError(
            "malformed CSV row (unexpected number of fields or broken quoting)", details={"near_row": offset + 1}
        ) from exc
    except UnicodeDecodeError as exc:
        raise DatasetFormatError("the file contains bytes that are invalid for its detected encoding") from exc


def context_frame(chunk: CanonicalChunk, schema: DatasetSchema) -> pd.DataFrame | None:
    """Collect allowlisted flow-context columns (identifiers and selected features) for a chunk.

    The returned values are *raw strings*; IP pseudonymization happens in the service layer, which holds the key.
    """
    data: dict[str, pd.Series] = {}
    for column, key in schema.context_columns.items():
        if chunk.identifiers is not None and column in chunk.identifiers:
            data[key] = chunk.identifiers[column]
        elif column in chunk.features:
            data[key] = chunk.features[column]
    return pd.DataFrame(data, index=chunk.features.index) if data else None
