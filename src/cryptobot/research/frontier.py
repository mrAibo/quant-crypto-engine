from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from enum import StrEnum

from cryptobot.data.numeric import (
    ExactDecimalInput,
    NumericValidationError,
    parse_exact_decimal,
    serialize_exact_decimal,
)

_BPS = Decimal("10000")
_NS_PER_SECOND = 1_000_000_000


class FrontierValidationError(ValueError):
    """Raised when an economic-frontier input is invalid or unsupported."""


class TradeDirection(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class BookWalkSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class EvidenceClass(StrEnum):
    OBSERVED = "OBSERVED"
    SCENARIO = "SCENARIO"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class DepthLevel:
    price: Decimal
    size: Decimal

    def __post_init__(self) -> None:
        _require_positive_decimal(self.price, "price")
        _require_positive_decimal(self.size, "size")


@dataclass(frozen=True, slots=True)
class BookWalkResult:
    side: BookWalkSide
    requested_size: Decimal
    filled_size: Decimal
    unfilled_size: Decimal
    filled_notional: Decimal
    vwap: Decimal | None
    worst_price: Decimal | None
    levels_consumed: int

    @property
    def fully_filled(self) -> bool:
        return self.unfilled_size == 0

    def as_dict(self) -> dict[str, object]:
        return {
            "side": self.side.value,
            "requested_size": serialize_exact_decimal(self.requested_size),
            "filled_size": serialize_exact_decimal(self.filled_size),
            "unfilled_size": serialize_exact_decimal(self.unfilled_size),
            "filled_notional": serialize_exact_decimal(self.filled_notional),
            "vwap": None if self.vwap is None else serialize_exact_decimal(self.vwap),
            "worst_price": (
                None if self.worst_price is None else serialize_exact_decimal(self.worst_price)
            ),
            "levels_consumed": self.levels_consumed,
            "fully_filled": self.fully_filled,
        }


@dataclass(frozen=True, slots=True)
class HorizonSupport:
    horizon_seconds: int
    non_overlapping_windows: int
    included: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "horizon_seconds": self.horizon_seconds,
            "non_overlapping_windows": self.non_overlapping_windows,
            "included": self.included,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class FrontierCell:
    horizon_seconds: int
    movement_quantile_bps: Decimal | None
    known_friction_floor_bps: Decimal | None
    required_capture_fraction: Decimal | None
    sample_count: int
    evidence_class: EvidenceClass
    unsupported_components: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_positive_int(self.horizon_seconds, "horizon_seconds")
        _require_nonnegative_int(self.sample_count, "sample_count")
        if not isinstance(self.evidence_class, EvidenceClass):
            raise FrontierValidationError("evidence_class must be EvidenceClass")
        _require_optional_nonnegative_decimal(
            self.movement_quantile_bps,
            "movement_quantile_bps",
        )
        _require_optional_nonnegative_decimal(
            self.known_friction_floor_bps,
            "known_friction_floor_bps",
        )
        _require_optional_nonnegative_decimal(
            self.required_capture_fraction,
            "required_capture_fraction",
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "horizon_seconds": self.horizon_seconds,
            "movement_quantile_bps": _serialize_optional_decimal(
                self.movement_quantile_bps
            ),
            "known_friction_floor_bps": _serialize_optional_decimal(
                self.known_friction_floor_bps
            ),
            "required_capture_fraction": _serialize_optional_decimal(
                self.required_capture_fraction
            ),
            "sample_count": self.sample_count,
            "evidence_class": self.evidence_class.value,
            "unsupported_components": list(self.unsupported_components),
        }


@dataclass(frozen=True, slots=True)
class FrontierReport:
    report_version: str
    source_dataset_bundle_sha256: str
    source_normalized_records_sha256: str
    fee_scenario_bps_per_side: Decimal
    fee_evidence_class: EvidenceClass
    latency_evidence_class: EvidenceClass
    funding_boundary_evidence_class: EvidenceClass
    horizons: tuple[HorizonSupport, ...]
    cells: tuple[FrontierCell, ...]

    def __post_init__(self) -> None:
        if not self.report_version.strip():
            raise FrontierValidationError("report_version must be non-empty")
        _require_sha256(self.source_dataset_bundle_sha256, "source_dataset_bundle_sha256")
        _require_sha256(
            self.source_normalized_records_sha256,
            "source_normalized_records_sha256",
        )
        _require_nonnegative_decimal(
            self.fee_scenario_bps_per_side,
            "fee_scenario_bps_per_side",
        )
        for field_name, value in (
            ("fee_evidence_class", self.fee_evidence_class),
            ("latency_evidence_class", self.latency_evidence_class),
            ("funding_boundary_evidence_class", self.funding_boundary_evidence_class),
        ):
            if not isinstance(value, EvidenceClass):
                raise FrontierValidationError(f"{field_name} must be EvidenceClass")

    def as_dict(self) -> dict[str, object]:
        return {
            "report_version": self.report_version,
            "source_dataset_bundle_sha256": self.source_dataset_bundle_sha256,
            "source_normalized_records_sha256": self.source_normalized_records_sha256,
            "fee_scenario_bps_per_side": serialize_exact_decimal(
                self.fee_scenario_bps_per_side
            ),
            "fee_evidence_class": self.fee_evidence_class.value,
            "latency_evidence_class": self.latency_evidence_class.value,
            "funding_boundary_evidence_class": self.funding_boundary_evidence_class.value,
            "horizons": [item.as_dict() for item in self.horizons],
            "cells": [item.as_dict() for item in self.cells],
        }

    def to_json_bytes(self) -> bytes:
        return (
            json.dumps(
                self.as_dict(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode()


def bbo_mid(
    bid: ExactDecimalInput,
    ask: ExactDecimalInput,
) -> Decimal:
    bid_value, ask_value = _validated_bbo(bid, ask)
    return (bid_value + ask_value) / Decimal(2)


def bbo_spread_bps(
    bid: ExactDecimalInput,
    ask: ExactDecimalInput,
) -> Decimal:
    bid_value, ask_value = _validated_bbo(bid, ask)
    mid = (bid_value + ask_value) / Decimal(2)
    return ((ask_value - bid_value) / mid) * _BPS


def signed_return_bps(
    start_price: ExactDecimalInput,
    end_price: ExactDecimalInput,
) -> Decimal:
    start = _parse_positive(start_price, "start_price")
    end = _parse_positive(end_price, "end_price")
    return ((end / start) - Decimal(1)) * _BPS


def absolute_move_bps(
    start_price: ExactDecimalInput,
    end_price: ExactDecimalInput,
) -> Decimal:
    return abs(signed_return_bps(start_price, end_price))


def round_trip_fee_bps(fee_bps_per_side: ExactDecimalInput) -> Decimal:
    fee = _parse_nonnegative(fee_bps_per_side, "fee_bps_per_side")
    return fee * Decimal(2)


def top_of_book_round_trip_friction_bps(
    bid: ExactDecimalInput,
    ask: ExactDecimalInput,
    *,
    fee_bps_per_side: ExactDecimalInput,
    direction: TradeDirection,
) -> Decimal:
    bid_value, ask_value = _validated_bbo(bid, ask)
    fee_bps = _parse_nonnegative(fee_bps_per_side, "fee_bps_per_side")
    if fee_bps >= _BPS:
        raise FrontierValidationError("fee_bps_per_side must be below 10000 bps")
    if not isinstance(direction, TradeDirection):
        raise FrontierValidationError("direction must be TradeDirection")

    fee_rate = fee_bps / _BPS
    one = Decimal(1)
    if direction is TradeDirection.LONG:
        entry_cash = ask_value * (one + fee_rate)
        same_book_exit_cash = bid_value * (one - fee_rate)
        return (one - (same_book_exit_cash / entry_cash)) * _BPS

    initial_short_proceeds = bid_value * (one - fee_rate)
    same_book_cover_cash = ask_value * (one + fee_rate)
    return ((same_book_cover_cash / initial_short_proceeds) - one) * _BPS


def required_capture_fraction(
    known_friction_floor_bps: ExactDecimalInput,
    movement_quantile_bps: ExactDecimalInput,
) -> Decimal:
    friction = _parse_nonnegative(
        known_friction_floor_bps,
        "known_friction_floor_bps",
    )
    movement = _parse_positive(movement_quantile_bps, "movement_quantile_bps")
    return friction / movement


def walk_book(
    levels: tuple[DepthLevel, ...],
    *,
    requested_size: ExactDecimalInput,
    side: BookWalkSide,
) -> BookWalkResult:
    requested = _parse_positive(requested_size, "requested_size")
    if not isinstance(side, BookWalkSide):
        raise FrontierValidationError("side must be BookWalkSide")
    _validate_level_order(levels, side)

    remaining = requested
    filled = Decimal(0)
    notional = Decimal(0)
    worst: Decimal | None = None
    consumed = 0

    for level in levels:
        if remaining == 0:
            break
        take = min(remaining, level.size)
        if take <= 0:
            continue
        filled += take
        notional += take * level.price
        remaining -= take
        worst = level.price
        consumed += 1

    vwap = None if filled == 0 else notional / filled
    return BookWalkResult(
        side=side,
        requested_size=requested,
        filled_size=filled,
        unfilled_size=remaining,
        filled_notional=notional,
        vwap=vwap,
        worst_price=worst,
        levels_consumed=consumed,
    )


def validate_two_sided_book(
    bids: tuple[DepthLevel, ...],
    asks: tuple[DepthLevel, ...],
) -> None:
    if not bids or not asks:
        raise FrontierValidationError("two-sided book requires bids and asks")
    _validate_level_order(bids, BookWalkSide.SELL)
    _validate_level_order(asks, BookWalkSide.BUY)
    if bids[0].price >= asks[0].price:
        raise FrontierValidationError("crossed or locked book is unsupported for frontier cost")


def horizon_grid_125(
    minimum_seconds: int,
    maximum_seconds: int,
) -> tuple[int, ...]:
    _require_positive_int(minimum_seconds, "minimum_seconds")
    _require_positive_int(maximum_seconds, "maximum_seconds")
    if maximum_seconds < minimum_seconds:
        raise FrontierValidationError("maximum_seconds must be >= minimum_seconds")

    values: list[int] = []
    power = 1
    while power <= maximum_seconds:
        for multiplier in (1, 2, 5):
            value = multiplier * power
            if minimum_seconds <= value <= maximum_seconds:
                values.append(value)
        power *= 10
    return tuple(values)


def non_overlapping_window_count(
    observed_duration_ns: int,
    horizon_seconds: int,
) -> int:
    _require_nonnegative_int(observed_duration_ns, "observed_duration_ns")
    _require_positive_int(horizon_seconds, "horizon_seconds")
    return observed_duration_ns // (horizon_seconds * _NS_PER_SECOND)


def horizon_support(
    *,
    observed_duration_ns: int,
    minimum_seconds: int,
    maximum_seconds: int,
    minimum_non_overlapping_windows: int,
) -> tuple[HorizonSupport, ...]:
    _require_positive_int(
        minimum_non_overlapping_windows,
        "minimum_non_overlapping_windows",
    )
    grid = horizon_grid_125(minimum_seconds, maximum_seconds)
    result: list[HorizonSupport] = []
    for horizon in grid:
        windows = non_overlapping_window_count(observed_duration_ns, horizon)
        included = windows >= minimum_non_overlapping_windows
        reason = (
            "SUPPORTED_BY_WINDOW_COUNT"
            if included
            else "INSUFFICIENT_NON_OVERLAPPING_WINDOWS"
        )
        result.append(
            HorizonSupport(
                horizon_seconds=horizon,
                non_overlapping_windows=windows,
                included=included,
                reason=reason,
            )
        )
    return tuple(result)


def empirical_quantile_nearest_rank(
    values: tuple[Decimal, ...],
    probability: ExactDecimalInput,
) -> Decimal:
    if not values:
        raise FrontierValidationError("quantile requires at least one value")
    checked = tuple(_parse_nonnegative(value, "quantile value") for value in values)
    p = parse_exact_decimal(probability)
    if p <= 0 or p > 1:
        raise FrontierValidationError("probability must be in (0, 1]")

    ordered = sorted(checked)
    rank = int((p * Decimal(len(ordered))).to_integral_value(rounding=ROUND_CEILING))
    return ordered[rank - 1]


def _validated_bbo(
    bid: ExactDecimalInput,
    ask: ExactDecimalInput,
) -> tuple[Decimal, Decimal]:
    bid_value = _parse_positive(bid, "bid")
    ask_value = _parse_positive(ask, "ask")
    if bid_value >= ask_value:
        raise FrontierValidationError("BBO must be strictly uncrossed: bid < ask")
    return bid_value, ask_value


def _validate_level_order(
    levels: tuple[DepthLevel, ...],
    side: BookWalkSide,
) -> None:
    if not isinstance(levels, tuple):
        raise FrontierValidationError("levels must be a tuple")
    if not isinstance(side, BookWalkSide):
        raise FrontierValidationError("side must be BookWalkSide")
    prices = [level.price for level in levels]
    if side is BookWalkSide.BUY:
        if prices != sorted(prices):
            raise FrontierValidationError("ask levels must be sorted ascending")
    elif prices != sorted(prices, reverse=True):
        raise FrontierValidationError("bid levels must be sorted descending")


def _parse_positive(value: ExactDecimalInput, field: str) -> Decimal:
    try:
        parsed = parse_exact_decimal(value)
    except NumericValidationError as exc:
        raise FrontierValidationError(str(exc)) from exc
    if parsed <= 0:
        raise FrontierValidationError(f"{field} must be positive")
    return parsed


def _parse_nonnegative(value: ExactDecimalInput, field: str) -> Decimal:
    try:
        parsed = parse_exact_decimal(value)
    except NumericValidationError as exc:
        raise FrontierValidationError(str(exc)) from exc
    if parsed < 0:
        raise FrontierValidationError(f"{field} must be non-negative")
    return parsed


def _require_positive_decimal(value: Decimal, field: str) -> None:
    if not isinstance(value, Decimal):
        raise FrontierValidationError(f"{field} must be Decimal")
    _parse_positive(value, field)


def _require_nonnegative_decimal(value: Decimal, field: str) -> None:
    if not isinstance(value, Decimal):
        raise FrontierValidationError(f"{field} must be Decimal")
    _parse_nonnegative(value, field)


def _require_optional_nonnegative_decimal(
    value: Decimal | None,
    field: str,
) -> None:
    if value is not None:
        _require_nonnegative_decimal(value, field)


def _require_positive_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FrontierValidationError(f"{field} must be a positive integer")


def _require_nonnegative_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FrontierValidationError(f"{field} must be a non-negative integer")


def _require_sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise FrontierValidationError(f"{field} must be 64 lowercase hex characters")


def _serialize_optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else serialize_exact_decimal(value)
