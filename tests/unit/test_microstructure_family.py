from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from cryptobot.research.economic_family import EconomicDevelopmentRow
from cryptobot.research.microstructure_family import (
    FEATURE_NAMES,
    MicrostructureRow,
    build_training_report,
    expected_value_hurdle,
    feature_vector,
    fit_frozen_model_50s,
    write_training_report,
)


def _row(index: int, *, profitable: bool) -> MicrostructureRow:
    direction = 1 if index % 2 == 0 else -1
    bbo = Decimal(direction) * (Decimal("0.8") + Decimal(index % 7) / Decimal("100"))
    base = EconomicDevelopmentRow(
        row_id=f"row-{index}",
        decision_recv_wall_ns=index * 100,
        invalid_reasons=(),
        entry_bid=Decimal("100"),
        entry_ask=Decimal("101"),
        exit_bid=Decimal("104") if direction > 0 and profitable else Decimal("100"),
        exit_ask=Decimal("97") if direction < 0 and profitable else Decimal("102"),
        hl_spread_bps=Decimal("0.2") + Decimal(index % 3) / Decimal("100"),
        hl_bbo_imbalance=bbo,
        binance_mid_return_5s_bps=Decimal(direction)
        * (Decimal("3") if profitable else Decimal("-1")),
        outcome_invalid_reasons=(),
    )
    return MicrostructureRow(
        base=base,
        hl_depth_imbalance_top5=Decimal(direction)
        * (Decimal("0.6") + Decimal(index % 5) / Decimal("100")),
        hl_aggressive_trade_flow_5s=Decimal(direction)
        * (Decimal("0.5") if profitable else Decimal("-0.2")),
        binance_aggressive_trade_flow_5s=Decimal(direction)
        * (Decimal("0.4") if profitable else Decimal("-0.1")),
        hl_mid_return_5s_bps=Decimal(direction) * (Decimal("2") if profitable else Decimal("0.2")),
        cross_venue_return_gap_5s_bps=Decimal(direction)
        * (Decimal("-1") if profitable else Decimal("1.2")),
    )


def _rows(n: int) -> tuple[MicrostructureRow, ...]:
    return tuple(_row(index, profitable=index % 4 == 0) for index in range(n))


def test_feature_vector_uses_all_frozen_eight_features() -> None:
    row = _row(0, profitable=True)
    values = feature_vector(row)

    assert values is not None
    assert len(values) == 8
    assert len(FEATURE_NAMES) == 8
    assert values[0] == abs(row.base.hl_bbo_imbalance or Decimal(0))
    assert values[1] == row.hl_depth_imbalance_top5
    assert values[2] == row.hl_aggressive_trade_flow_5s
    assert values[3] == row.binance_aggressive_trade_flow_5s


def test_full_microstructure_model_is_deterministic() -> None:
    rows = _rows(400)

    first = fit_frozen_model_50s(rows)
    second = fit_frozen_model_50s(rows)

    assert first == second
    assert len(first.coefficients) == 9
    assert Decimal(0) < first.economic_probability_hurdle < Decimal(1)


def test_expected_value_hurdle_has_no_threshold_sweep() -> None:
    assert expected_value_hurdle(
        mean_positive=Decimal("20"),
        mean_nonpositive=Decimal("-80"),
    ) == Decimal("0.8")


def test_training_report_marks_300s_ineligible_below_frozen_support() -> None:
    report = build_training_report(_rows(400), _rows(57))

    assert report.exposed_dev_b_contaminated is True
    assert report.horizon_300s_eligible is False
    assert report.horizon_300s_complete == 57
    assert report.as_dict()["old_confirmation_used"] is False


def test_training_report_writer_is_immutable(tmp_path: Path) -> None:
    report = build_training_report(_rows(400), _rows(57))
    target = tmp_path / "training.json"

    assert write_training_report(report, target) == target
    assert target.read_bytes() == report.to_json_bytes()
    assert write_training_report(report, target) == target

    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(Exception, match="differs"):
        write_training_report(report, target)
