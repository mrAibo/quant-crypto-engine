from __future__ import annotations

from decimal import Decimal

import pytest

from cryptobot.data.numeric import (
    NumericValidationError,
    decimal_to_scaled_int,
    parse_exact_decimal,
    scaled_int_to_decimal,
    serialize_exact_decimal,
)


def test_parse_exact_decimal_preserves_exact_string_value() -> None:
    value = parse_exact_decimal("123.4500")

    assert value == Decimal("123.4500")
    assert value.as_tuple().exponent == -4


def test_parse_exact_decimal_accepts_integer_without_float_conversion() -> None:
    assert parse_exact_decimal(42) == Decimal(42)


@pytest.mark.parametrize("value", [1.5, True, False])
def test_binary_float_and_bool_are_rejected(value: object) -> None:
    with pytest.raises(NumericValidationError, match="binary float/bool"):
        parse_exact_decimal(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_decimal_values_are_rejected(value: str) -> None:
    with pytest.raises(NumericValidationError, match="NaN and Infinity"):
        parse_exact_decimal(value)


def test_serialize_exact_decimal_is_non_exponent_and_preserves_scale() -> None:
    assert serialize_exact_decimal(Decimal("1.2300")) == "1.2300"
    assert serialize_exact_decimal(Decimal("1E+3")) == "1000"


def test_negative_zero_serializes_as_zero() -> None:
    assert serialize_exact_decimal(Decimal("-0.00")) == "0"


def test_scaled_integer_roundtrip_is_exact() -> None:
    scaled = decimal_to_scaled_int("123.45", 2)

    assert scaled == 12345
    assert scaled_int_to_decimal(scaled, 2) == Decimal("123.45")


def test_scaled_integer_conversion_rejects_excess_precision() -> None:
    with pytest.raises(NumericValidationError, match="exceeds 2 decimal places"):
        decimal_to_scaled_int("1.234", 2)


def test_invalid_decimal_count_is_rejected() -> None:
    with pytest.raises(NumericValidationError, match="non-negative integer"):
        decimal_to_scaled_int("1.0", -1)
