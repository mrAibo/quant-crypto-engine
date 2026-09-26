from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from cryptobot.research.economic_family import (
    CANDIDATE_IDS,
    DevelopmentDecision,
    EconomicDevelopmentRow,
    EconomicFamilyValidationError,
    FeatureThresholds,
    candidate_action,
    chronological_development_split,
    evaluate_candidate,
    evaluate_economic_development,
    executable_known_net,
    write_development_report,
)


def _row(
    index: int,
    *,
    imbalance: str = "0.8",
    reference: str = "2",
    spread: str = "0.2",
    long_exit_bid: str = "102",
    short_exit_ask: str = "98",
) -> EconomicDevelopmentRow:
    return EconomicDevelopmentRow(
        row_id=f"row-{index}",
        decision_recv_wall_ns=index * 100,
        invalid_reasons=(),
        entry_bid=Decimal("100"),
        entry_ask=Decimal("101"),
        exit_bid=Decimal(long_exit_bid),
        exit_ask=Decimal(short_exit_ask),
        hl_spread_bps=Decimal(spread),
        hl_bbo_imbalance=Decimal(imbalance),
        binance_mid_return_5s_bps=Decimal(reference),
        outcome_invalid_reasons=(),
    )


def _thresholds() -> FeatureThresholds:
    return FeatureThresholds(
        abs_imbalance_q75=Decimal("0.7"),
        abs_reference_return_q75=Decimal("1.5"),
        spread_q50=Decimal("0.5"),
    )


def test_candidate_registry_is_small_and_frozen() -> None:
    assert CANDIDATE_IDS == (
        "E0_H2_BASELINE",
        "E1_H2_STRONG_IMBALANCE",
        "E2_H2_REFERENCE_AGREEMENT",
        "E3_H2_AGREE_STRONG_REFERENCE",
        "E4_H2_AGREE_STRONG_IMBALANCE_TIGHT_SPREAD",
    )


def test_candidate_actions_use_only_decision_features() -> None:
    row = _row(1)
    thresholds = _thresholds()

    assert candidate_action(row, candidate_id="E0_H2_BASELINE", thresholds=thresholds) == 1
    assert candidate_action(row, candidate_id="E1_H2_STRONG_IMBALANCE", thresholds=thresholds) == 1
    assert (
        candidate_action(row, candidate_id="E2_H2_REFERENCE_AGREEMENT", thresholds=thresholds) == 1
    )
    assert (
        candidate_action(row, candidate_id="E3_H2_AGREE_STRONG_REFERENCE", thresholds=thresholds)
        == 1
    )
    assert (
        candidate_action(
            row,
            candidate_id="E4_H2_AGREE_STRONG_IMBALANCE_TIGHT_SPREAD",
            thresholds=thresholds,
        )
        == 1
    )

    disagree = _row(2, reference="-2")
    assert (
        candidate_action(
            disagree,
            candidate_id="E2_H2_REFERENCE_AGREEMENT",
            thresholds=thresholds,
        )
        == 0
    )


def test_executable_known_net_uses_bid_ask_and_fee_once() -> None:
    row = _row(1, long_exit_bid="104")

    gross, fee, net, net_bps = executable_known_net(row, action=1) or (
        None,
        None,
        None,
        None,
    )

    assert gross == Decimal("3")
    assert fee == (Decimal("101") + Decimal("104")) * Decimal("4.5") / Decimal("10000")
    assert net == gross - fee
    assert net_bps == net / Decimal("101") * Decimal("10000")


def test_chronological_split_keeps_equal_wall_in_dev_b() -> None:
    rows = tuple(_row(index) for index in range(400))
    rows = (
        *rows[:199],
        replace(
            rows[199],
            decision_recv_wall_ns=rows[198].decision_recv_wall_ns,
        ),
        *rows[200:],
    )
    a, b = chronological_development_split(rows)
    assert a[-1].decision_recv_wall_ns < b[0].decision_recv_wall_ns


def test_economic_development_prefers_deterministic_family_when_dev_b_positive() -> None:
    rows = tuple(_row(index, long_exit_bid="103") for index in range(400))

    report = evaluate_economic_development("a" * 64, rows)

    assert report.decision is DevelopmentDecision.FREEZE_DETERMINISTIC_FAMILY
    assert 0 < len(report.deterministic_shortlist) <= 2
    assert report.as_dict()["confirmation_used"] is False


def test_shortlist_requires_positive_mean_median_and_support() -> None:
    rows = tuple(_row(index, long_exit_bid="99") for index in range(400))
    report = evaluate_economic_development("a" * 64, rows)

    assert report.deterministic_shortlist == ()
    assert report.decision is DevelopmentDecision.DEVELOP_REGULARIZED_LOGISTIC_BASELINE


def test_report_writer_is_immutable(tmp_path: Path) -> None:
    rows = tuple(_row(index, long_exit_bid="103") for index in range(400))
    report = evaluate_economic_development("a" * 64, rows)
    target = tmp_path / "report.json"

    assert write_development_report(report, target) == target
    assert target.read_bytes() == report.to_json_bytes()
    assert write_development_report(report, target) == target

    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(EconomicFamilyValidationError, match="differs"):
        write_development_report(report, target)


def test_evaluate_candidate_rejects_unknown_id() -> None:
    with pytest.raises(EconomicFamilyValidationError, match="unknown candidate"):
        evaluate_candidate((_row(1),), candidate_id="UNKNOWN", thresholds=_thresholds())
