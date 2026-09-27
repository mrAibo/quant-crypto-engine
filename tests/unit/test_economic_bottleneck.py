from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from cryptobot.research.economic_bottleneck import (
    BottleneckValidationError,
    PrimaryPath,
    break_even_fee_bps_per_side,
    build_task026_report,
    write_economic_bottleneck_report,
)


def test_break_even_fee_sensitivity_is_linear() -> None:
    result = break_even_fee_bps_per_side(
        mean_gross_quote=Decimal("20"),
        mean_fee_quote=Decimal("100"),
        scenario_bps_per_side=Decimal("4.5"),
    )
    assert result == Decimal("0.9")


def test_break_even_fee_rejects_invalid_fee_inputs() -> None:
    with pytest.raises(BottleneckValidationError, match="positive"):
        break_even_fee_bps_per_side(
            mean_gross_quote=Decimal("1"),
            mean_fee_quote=Decimal("0"),
        )


def test_task026_selects_fixed_public_development_expansion() -> None:
    report = build_task026_report()

    assert report.selected_primary_path is (PrimaryPath.PROSPECTIVE_DEVELOPMENT_EVIDENCE_EXPANSION)
    assert report.fee_sensitivity.candidate_id == "E3_H2_AGREE_STRONG_REFERENCE"
    assert report.fee_sensitivity.break_even_fee_bps_per_side < Decimal("1")
    assert report.fee_sensitivity.mean_net_at_documented_tier6_diamond_quote < 0
    assert report.best_300s_candidate_id == "E300_2_IMB_EXTREME"
    assert report.best_300s_dev_b_valid_trade_count == 9
    assert report.best_300s_dev_b_mean_partial_known_cost_pnl < 0
    assert report.microstructure_50s_positive_target_count == 24
    assert report.microstructure_300s_positive_target_count == 6
    assert report.evidence_expansion.fixed_duration_hours == 72
    assert report.evidence_expansion.nominal_decision_intervals == 5184
    assert Decimal("24.8") < report.evidence_expansion.source_exposure_hours < Decimal("24.9")
    assert (
        Decimal("1186")
        < report.evidence_expansion.projected_valid_targets_at_observed_rate
        < Decimal("1187")
    )
    assert (
        Decimal("69")
        < report.evidence_expansion.projected_positive_targets_at_observed_rate
        < Decimal("70")
    )
    assert report.as_dict()["user_action_required_now"] is False
    assert report.as_dict()["new_model_or_test_evidence_consumed"] is False


def test_task026_report_writer_is_immutable(tmp_path: Path) -> None:
    report = build_task026_report()
    target = tmp_path / "task026.json"

    assert write_economic_bottleneck_report(report, target) == target
    assert target.read_bytes() == report.to_json_bytes()
    assert write_economic_bottleneck_report(report, target) == target

    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(BottleneckValidationError, match="differs"):
        write_economic_bottleneck_report(report, target)
