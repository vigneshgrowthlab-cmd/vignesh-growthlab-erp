"""Shared parsing helpers for CSV bulk-import services.

Keeps the per-row parsing of master-data importers (products, customers,
vendors) consistent: blanks fall back to a default, bad values raise so the
row is reported rather than silently coerced.
"""
from decimal import Decimal
from typing import Optional

_TRUE = {"true", "1", "yes", "y", "t"}
_FALSE = {"false", "0", "no", "n", "f"}


def clean(value: Optional[str]) -> Optional[str]:
    """Trim a CSV cell; empty -> None."""
    s = (value or "").strip()
    return s or None


def parse_decimal(value: Optional[str], default: str = "0") -> Decimal:
    """Decimal from a CSV cell; blank -> default. Raises on invalid input."""
    s = (value or "").strip()
    if s == "":
        return Decimal(default)
    return Decimal(s)


def parse_int(value: Optional[str], default: int = 0) -> int:
    """Int from a CSV cell; blank -> default. Tolerates '30.0'."""
    s = (value or "").strip()
    if s == "":
        return default
    return int(Decimal(s))


def parse_bool(value: Optional[str], default: bool = True) -> bool:
    """Bool from a CSV cell; blank -> default. Raises on unrecognised text."""
    s = (value or "").strip().lower()
    if s == "":
        return default
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    raise ValueError(f"invalid true/false value '{value}'")
