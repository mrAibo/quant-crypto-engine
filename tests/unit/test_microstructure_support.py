from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from cryptobot.research.economic_family import EconomicDevelopmentRow
from cryptobot.research.microstructure_family import MicrostructureRow
from cryptobot.research.microstructure_support import (
    adjudicate_task025,
    summarize_support,
    write_decision_report,
)


def _row(index: int, *, positive: bool) -> MicrostructureRow:
    direction = 1 if index % 2 == 0 else -1
    base = EconomicDevelopmentRow(
        row_id=f"row-{index}",
        decision_recv_wall_ns=index * 100,
        invalid_reasons=(),
        entry_bid=Decimal("100"),
        entry_ask=Decimal("101"),
        exit_bid=Decimal("104") if direction > 0 and positive else Decimal("100"),
        exit_ask=Decimal("97") if direction < 0 and positive else Decimal("102"),
        hl_spread_bps=Decimal("0.2"),
        hl_bbo_imbalance=Decimal(direction) * Decimal("0.8"),
        binance_mid_return_5s_bps=Decimal(direction) * Decimal("2"),
        outcome_invalid_reasons=(),
    )
    return MicrostructureRow(
        base=base,
        hl_depth_imbalance_top5=Decimal(direction) * Decimal("0.5"),
        hl_aggressive_trade_flow_5s=Decimal(direction) * Decimal("0.4"),
        binance_aggressive_trade_flow_5s=Decimal(direction) * Decimal("0.3"),
        hl_mid_return_5s_bps=Decimal(direction) * Decimal("1"),
        cross_venue_return_gap_5s_bps=Decimal(direction) * Decimal("-1"),
    )


def _rows(total: int, positives: int) -> tuple[MicrostructureRow, ...]:
    return tuple(_row(index, positive=index < positives) for index in range(total))


def test_support_summary_counts_target_classes() -> None:
    result = summarize_support(
        _rows(100, 24),
        horizon_seconds=50,
        min_feature_complete=80,
    )

    assert result.feature_complete_count == 100
    assert result.valid_target_count == 100
    assert result.positive_target_count == 24
    assert result.nonpositive_target_count == 76
    assert result.feature_support_passed is True
    assert result.class_support_passed is False


def test_task025_stops_when_class_and_horizon_support_fail() -> None:
    report = adjudicate_task025(
        _rows(400, 24),
        _rows(57, 6),
    )

    assert report.decision == "STOP_MICROSTRUCTURE_FAMILY"
    assert report.exposed_dev_b_contaminated is True
    assert "50S_TARGET_CLASS_SUPPORT_BELOW_30_30" in report.reasons
    assert "300S_FEATURE_SUPPORT_BELOW_FROZEN_MINIMUM" in report.reasons
    assert report.as_dict()["old_confirmation_used"] is False


def test_decision_writer_is_immutable(tmp_path: Path) -> None:
    report = adjudicate_task025(
        _rows(400, 24),
        _rows(57, 6),
    )
    target = tmp_path / "decision.json"

    assert write_decision_report(report, target) == target
    assert target.read_bytes() == report.to_json_bytes()
    assert write_decision_report(report, target) == target

    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(Exception, match="differs"):
        write_decision_report(report, target)
