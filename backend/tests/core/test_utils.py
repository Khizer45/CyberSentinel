"""Utility safety helpers: IP pseudonymization, CSV formula escaping, text sanitizing."""

from __future__ import annotations

from app.utils.csv_safety import escape_csv_cell
from app.utils.ip import pseudonymize_ip
from app.utils.text import clean_text, display_filename, escape_like


def test_ip_pseudonymization_is_keyed_stable_and_validated() -> None:
    a = pseudonymize_ip("192.168.10.5", b"key-1")
    assert a is not None and a == pseudonymize_ip(" 192.168.10.5 ", b"key-1")
    assert a.startswith("ip_") and "192" not in a
    assert a != pseudonymize_ip("192.168.10.5", b"key-2")
    assert pseudonymize_ip("192.168.10.5", None) is None  # no key -> IP dropped
    assert pseudonymize_ip("not-an-ip; DROP TABLE", b"key-1") is None


def test_csv_formula_injection_escaped() -> None:
    for payload in ('=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)", "\tcmd"):
        assert escape_csv_cell(payload).startswith("'")
    assert escape_csv_cell("Benign") == "Benign"
    assert escape_csv_cell(-1.5) == -1.5


def test_text_helpers() -> None:
    assert display_filename("..\\..\\windows/system32/evil.csv") == "evil.csv"
    assert clean_text("a\x00b\x1bc  ", max_length=10) == "a b c"
    assert escape_like("50%_off\\") == "50\\%\\_off\\\\"
