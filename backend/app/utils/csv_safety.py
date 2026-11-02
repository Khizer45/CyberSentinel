"""Protection against CSV/spreadsheet formula injection in exports (Workflow Manual 14.2)."""

from __future__ import annotations

from typing import Any

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def escape_csv_cell(value: Any) -> Any:
    """Prefix text that a spreadsheet would interpret as a formula with a single quote.

    Numbers are left untouched (a negative *number* is not text); only strings are escaped.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value
