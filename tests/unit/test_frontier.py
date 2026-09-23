from __future__ import annotations

import json
from decimal import Decimal

import pytest

from cryptobot.research.frontier import (
    BookWalkSide,
    DepthLevel,
    EvidenceClass,
    FrontierCell,
    FrontierReport,
    FrontierValidationError,
    TradeDirection,
    absolute_move_bps,
    bbo_mid,
    bbo_spread_bps,
    empirical_quantile_nearest_rank,
    horizon_grid_125,
    horizon_support,
    non_overlapping_window_count,
    required_capture_fraction,
    round_trip_fee_bps,
    signed_return_bps,
    top_of_book_round_trip_friction_bps,
    validate_two_sided_book,
    walk_book,
)


def test_bbo_mid_and_spread_use_exact_decimal_arithmetic() -> None:
    assert bbo_mid("99", "101") == Decimal("100")
    assert bbo_spread_bps("99", "101") == Decimal("200")


def test_bbo_rejects_float_and_crossed_inputs() -> None:
    with pytest.raises(FrontierValidationError, match="binary float"):
        bbo_mid(99.0, "101")

    with pytest.raises(FrontierValidationError, match="bid < ask"):
        bbo_mid("101", "101")


def test_signed_and_absolute_moves_are_basis_points() -> None:
    assert signed_return_bps("100", "101") == Decimal("100")
    assert signed_return_bps("100", "99") == Decimal("-100")
    assert absolute_move_bps("100", "99") == Decimal("100")


def test_round_trip_fee_counts_each_side_once() -> None:
    assert round_trip_fee_bps("4.5") == Decimal("9.0")


def test_top_of_book_friction_is_directional_and_includes_fee_once() -> None:
    long_zero_fee = top_of_book_round_trip_friction_bps(
        "99",
        "101",
        fee_bps_per_side="0",
        direction=TradeDirection.LONG,
    )
    short_zero_fee = top_of_book_round_trip_friction_bps(
        "99",
        "101",
        fee_bps_per_side="0",
        direction=TradeDirection.SHORT,
    )
    long_with_fee = top_of_book_round_trip_friction_bps(
        "99",
        "101",
        fee_bps_per_side="4.5",
        direction=TradeDirection.LONG,
    )

    assert long_zero_fee == (Decimal(1) - (Decimal("99") / Decimal("101"))) * Decimal(
        "10000"
    )
    assert short_zero_fee == ((Decimal("101") / Decimal("99")) - Decimal(1)) * Decimal(
        "10000"
    )
    assert long_with_fee > long_zero_fee
    assert long_with_fee < long_zero_fee + Decimal("10")


def test_required_capture_fraction_is_cost_over_move() -> None:
    assert required_capture_fraction("9", "30") == Decimal("0.3")

    with pytest.raises(FrontierValidationError, match="movement_quantile_bps must be positive"):
        required_capture_fraction("9", "0")


def test_buy_book_walk_consumes_asks_in_price_order() -> None:
    levels = (
        DepthLevel(Decimal("100"), Decimal("1")),
        DepthLevel(Decimal("101"), Decimal("2")),
        DepthLevel(Decimal("102"), Decimal("3")),
    )

    result = walk_book(
        levels,
        requested_size=Decimal("2"),
        side=BookWalkSide.BUY,
    )

    assert result.fully_filled
    assert result.filled_size == Decimal("2")
    assert result.unfilled_size == 0
    assert result.filled_notional == Decimal("201")
    assert result.vwap == Decimal("100.5")
    assert result.worst_price == Decimal("101")
    assert result.levels_consumed == 2


def test_sell_book_walk_consumes_bids_in_descending_order() -> None:
    levels = (
        DepthLevel(Decimal("101"), Decimal("1")),
        DepthLevel(Decimal("100"), Decimal("2")),
    )

    result = walk_book(
        levels,
        requested_size="2.5",
        side=BookWalkSide.SELL,
    )

    assert result.fully_filled
    assert result.filled_size == Decimal("2.5")
    assert result.filled_notional == Decimal("251.0")
    assert result.vwap == Decimal("100.4")
    assert result.worst_price == Decimal("100")
    assert result.levels_consumed == 2


def test_book_walk_never_fills_beyond_displayed_depth() -> None:
    levels = (
        DepthLevel(Decimal("100"), Decimal("1")),
        DepthLevel(Decimal("101"), Decimal("2")),
    )

    result = walk_book(
        levels,
        requested_size="4",
        side=BookWalkSide.BUY,
    )

    assert not result.fully_filled
    assert result.filled_size == Decimal("3")
    assert result.unfilled_size == Decimal("1")
    assert result.filled_notional == Decimal("302")
    assert result.vwap == Decimal("302") / Decimal("3")


def test_book_walk_rejects_unsorted_levels() -> None:
    asks = (
        DepthLevel(Decimal("101"), Decimal("1")),
        DepthLevel(Decimal("100"), Decimal("1")),
    )

    with pytest.raises(FrontierValidationError, match="ask levels must be sorted ascending"):
        walk_book(asks, requested_size="1", side=BookWalkSide.BUY)


def test_two_sided_book_rejects_crossed_or_locked_market() -> None:
    bids = (DepthLevel(Decimal("101"), Decimal("1")),)
    asks = (DepthLevel(Decimal("101"), Decimal("1")),)

    with pytest.raises(FrontierValidationError, match="crossed or locked"):
        validate_two_sided_book(bids, asks)


def test_horizon_grid_uses_deterministic_1_2_5_sequence() -> None:
    assert horizon_grid_125(3, 600) == (5, 10, 20, 50, 100, 200, 500)


def test_non_overlapping_window_count_is_exact_floor() -> None:
    assert non_overlapping_window_count(100_000_000_000, 20) == 5
    assert non_overlapping_window_count(19_999_999_999, 20) == 0


def test_horizon_support_exposes_insufficient_cells_instead_of_hiding_them() -> None:
    result = horizon_support(
        observed_duration_ns=100_000_000_000,
        minimum_seconds=10,
        maximum_seconds=50,
        minimum_non_overlapping_windows=3,
    )

    observed = [
        (item.horizon_seconds, item.non_overlapping_windows, item.included)
        for item in result
    ]
    assert observed == [
        (10, 10, True),
        (20, 5, True),
        (50, 2, False),
    ]
    assert result[-1].reason == "INSUFFICIENT_NON_OVERLAPPING_WINDOWS"


def test_empirical_quantile_uses_nearest_rank_without_float_interpolation() -> None:
    values = (
        Decimal("1"),
        Decimal("2"),
        Decimal("3"),
        Decimal("4"),
    )

    assert empirical_quantile_nearest_rank(values, "0.5") == Decimal("2")
    assert empirical_quantile_nearest_rank(values, "0.75") == Decimal("3")
    assert empirical_quantile_nearest_rank(values, "1") == Decimal("4")


def test_frontier_cell_can_explicitly_carry_unsupported_components() -> None:
    cell = FrontierCell(
        horizon_seconds=60,
        movement_quantile_bps=Decimal("25"),
        known_friction_floor_bps=Decimal("11"),
        required_capture_fraction=Decimal("0.44"),
        sample_count=100,
        evidence_class=EvidenceClass.OBSERVED,
        unsupported_components=("funding_boundary", "live_execution_latency"),
    )

    assert cell.unsupported_components == (
        "funding_boundary",
        "live_execution_latency",
    )


def test_frontier_report_serialization_is_deterministic_and_digest_bound() -> None:
    horizons = horizon_support(
        observed_duration_ns=1_000_000_000_000,
        minimum_seconds=10,
        maximum_seconds=20,
        minimum_non_overlapping_windows=10,
    )
    report = FrontierReport(
        report_version="frontier-v1",
        source_dataset_bundle_sha256="a" * 64,
        source_normalized_records_sha256="b" * 64,
        fee_scenario_bps_per_side=Decimal("4.5"),
        fee_evidence_class=EvidenceClass.SCENARIO,
        latency_evidence_class=EvidenceClass.UNKNOWN,
        funding_boundary_evidence_class=EvidenceClass.UNKNOWN,
        horizons=horizons,
        cells=(
            FrontierCell(
                horizon_seconds=10,
                movement_quantile_bps=Decimal("20"),
                known_friction_floor_bps=Decimal("9"),
                required_capture_fraction=Decimal("0.45"),
                sample_count=100,
                evidence_class=EvidenceClass.OBSERVED,
                unsupported_components=(
                    "funding_boundary",
                    "live_execution_latency",
                ),
            ),
        ),
    )

    first = report.to_json_bytes()
    second = report.to_json_bytes()
    decoded = json.loads(first)

    assert first == second
    assert decoded["source_dataset_bundle_sha256"] == "a" * 64
    assert decoded["fee_scenario_bps_per_side"] == "4.5"
    assert decoded["fee_evidence_class"] == "SCENARIO"
    assert decoded["latency_evidence_class"] == "UNKNOWN"


def test_frontier_report_rejects_invalid_dataset_digest() -> None:
    with pytest.raises(FrontierValidationError, match="64 lowercase hex"):
        FrontierReport(
            report_version="frontier-v1",
            source_dataset_bundle_sha256="not-a-digest",
            source_normalized_records_sha256="b" * 64,
            fee_scenario_bps_per_side=Decimal("4.5"),
            fee_evidence_class=EvidenceClass.SCENARIO,
            latency_evidence_class=EvidenceClass.UNKNOWN,
            funding_boundary_evidence_class=EvidenceClass.UNKNOWN,
            horizons=(),
            cells=(),
        )
