from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from cryptobot.research.economic_family import EconomicDevelopmentRow
from cryptobot.research.economic_logistic import (
    LogisticDevelopmentDecision,
    economic_probability_hurdle,
    fit_and_evaluate_logistic_development,
    fit_logistic_model,
    write_logistic_development_report,
)


def _row(index: int, *, profitable: bool) -> EconomicDevelopmentRow:
    magnitude = Decimal("0.6") + Decimal(index % 7) / Decimal("10")
    imbalance = magnitude if index % 2 == 0 else -magnitude
    action = 1 if imbalance > 0 else -1
    reference = Decimal(action) * (Decimal("4") if profitable else Decimal("-1"))
    if action > 0:
        exit_bid = Decimal("104") if profitable else Decimal("100")
        exit_ask = Decimal("104.2")
    else:
        exit_bid = Decimal("96")
        exit_ask = Decimal("96.5") if profitable else Decimal("101.5")
    return EconomicDevelopmentRow(
        row_id=f"row-{index}",
        decision_recv_wall_ns=index * 100,
        invalid_reasons=(),
        entry_bid=Decimal("100"),
        entry_ask=Decimal("101"),
        exit_bid=exit_bid,
        exit_ask=exit_ask,
        hl_spread_bps=Decimal("0.2") if profitable else Decimal("0.8"),
        hl_bbo_imbalance=imbalance,
        binance_mid_return_5s_bps=reference,
        outcome_invalid_reasons=(),
    )


def _rows() -> tuple[EconomicDevelopmentRow, ...]:
    # Same deterministic relationship is present in DEV_A and DEV_B.
    return tuple(_row(index, profitable=(index % 5 == 0 or index % 5 == 1)) for index in range(500))


def test_economic_hurdle_is_expected_value_breakeven() -> None:
    hurdle = economic_probability_hurdle(
        mean_positive=Decimal("20"),
        mean_nonpositive=Decimal("-80"),
    )
    assert hurdle == Decimal("0.8")


def test_logistic_solver_is_deterministic() -> None:
    x = tuple(
        (
            Decimal(index % 7),
            Decimal((index % 5) - 2),
            Decimal(index % 3),
            Decimal("0.2") + Decimal(index % 4) / Decimal(10),
        )
        for index in range(200)
    )
    y = tuple(int(index % 5 in (0, 1)) for index in range(200))

    first = fit_logistic_model(x, y)
    second = fit_logistic_model(x, y)

    assert first == second
    assert first.converged is True
    assert len(first.coefficients) == 5


def test_logistic_development_can_freeze_when_dev_b_economics_are_positive() -> None:
    report = fit_and_evaluate_logistic_development(
        source_sha256="a" * 64,
        rows=_rows(),
    )

    assert report.decision is LogisticDevelopmentDecision.FREEZE_LOGISTIC_FAMILY
    assert report.dev_b_evaluation.selected_trades >= 50
    assert report.dev_b_evaluation.mean_known_net_quote is not None
    assert report.dev_b_evaluation.mean_known_net_quote > 0
    assert report.as_dict()["old_confirmation_used"] is False


def test_logistic_report_writer_is_immutable(tmp_path: Path) -> None:
    report = fit_and_evaluate_logistic_development(
        source_sha256="a" * 64,
        rows=_rows(),
    )
    target = tmp_path / "report.json"

    assert write_logistic_development_report(report, target) == target
    assert target.read_bytes() == report.to_json_bytes()
    assert write_logistic_development_report(report, target) == target

    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(Exception, match="differs"):
        write_logistic_development_report(report, target)
