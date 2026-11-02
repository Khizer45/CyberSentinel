"""Text helpers for user-supplied strings (display-only; never used to build paths or queries)."""

from __future__ import annotations

import re
import unicodedata

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean_text(value: str, *, max_length: int) -> str:
    """Normalize Unicode, strip control characters and surrounding whitespace, and truncate."""
    text = unicodedata.normalize("NFKC", value)
    text = _CONTROL.sub(" ", text).strip()
    return text[:max_length]


def display_filename(name: str | None) -> str | None:
    """Keep only the base name of an uploaded file for display (no directories, no control characters)."""
    if not name:
        return None
    base = re.split(r"[\\/]", name)[-1]
    cleaned = clean_text(base, max_length=255)
    return cleaned or None


def normalize_email(email: str) -> str:
    return email.strip().lower()


def escape_like(term: str) -> str:
    """Escape LIKE wildcards so user search terms are matched literally (used with ``escape='\\\\'``)."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
