from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TypeAlias


ExactDecimalInput: TypeAlias = str | int | Decimal


class NumericValidationError(ValueError):
    """Raised when an exact persisted numeric value is invalid."""


def parse_exact_decimal(value: ExactDecimalInput) -> Decimal:
    """Parse a persisted market numeric without accepting binary floating point."""

    if isinstance(value, bool) or isinstance(value, float):
        raise NumericValidationError("binary float/bool input is not allowed for exact numerics")

    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise NumericValidationError(f"invalid exact decimal: {value!r}") from exc

    if not parsed.is_finite():
        raise NumericValidationError("NaN and Infinity are not allowed for exact numerics")
    return parsed


def serialize_exact_decimal(value: ExactDecimalInput) -> str:
    """Return a deterministic non-exponent decimal representation."""

    parsed = parse_exact_decimal(value)
    rendered = format(parsed, "f")
    return "0" if parsed.is_zero() and rendered.startswith("-") else rendered


def decimal_to_scaled_int(value: ExactDecimalInput, decimals: int) -> int:
    """Convert an exact decimal to integer units, rejecting non-integral scaling."""

    if isinstance(decimals, bool) or not isinstance(decimals, int) or decimals < 0:
        raise NumericValidationError("decimals must be a non-negative integer")

    parsed = parse_exact_decimal(value)
    scale = Decimal(10) ** decimals
    scaled = parsed * scale
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise NumericValidationError(
            f"value {serialize_exact_decimal(parsed)} exceeds {decimals} decimal places"
        )
    return int(integral)


def scaled_int_to_decimal(value: int, decimals: int) -> Decimal:
    """Convert integer units back to an exact decimal."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise NumericValidationError("scaled value must be an integer")
    if isinstance(decimals, bool) or not isinstance(decimals, int) or decimals < 0:
        raise NumericValidationError("decimals must be a non-negative integer")
    return Decimal(value) / (Decimal(10) ** decimals)
