from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from cryptobot.data.events import QualityFlag
from cryptobot.data.instruments import InstrumentRole
from cryptobot.research.signal_protocol import (
    H1_ID,
    H2_ID,
    FeatureValue,
    OutcomeLabel,
    SignalFeatureRow,
)
from cryptobot.research.signal_selection import (
    CONFIRMATION_START_WALL_NS,
    EXPECTED_SELECTION_ROW_COUNT,
    SELECTION_START_WALL_NS,
    SelectionDecision,
    SignalSelectionValidationError,
    correctness_autocorrelations,
    dependence_design_effect,
    effective_sample_size,
    evaluate_registered_selection,
    exact_binomial_upper_tail,
    wilson_lower_bound,
    write_selection_report,
)
from cryptobot.sim import QuoteObservation, SimulationOpportunity


def _feature(value: str, event_id: str, mono: int, wall: int) -> FeatureValue:
    return FeatureValue(
        value=Decimal(value),
        source_event_ids=(event_id,),
        asof_recv_mono_ns=mono,
        asof_recv_wall_ns=wall,
    )


def _row(
    index: int,
    *,
    h1_value: str = "1",
    h2_value: str = "-0.2",
    outcome_direction: int = 1,
) -> SignalFeatureRow:
    mono = index * 60_000_000_000
    wall = SELECTION_START_WALL_NS + index * 1_000_000_000
    entry = QuoteObservation(
        event_id=f"entry-{index}",
        source_id="hyperliquid-mainnet-public",
        instrument_id="hyperliquid.mainnet.perpetual.btc",
        role=InstrumentRole.PRIMARY,
        host_id="host-a",
        boot_id="boot-a",
        recv_mono_ns=mono,
        recv_wall_ns=wall,
        bid_price=Decimal("100"),
        ask_price=Decimal("101"),
        quality_flags=QualityFlag.NONE,
    )
    exit_quote = replace(
        entry,
        event_id=f"exit-{index}",
        recv_mono_ns=mono + 50_000_000_000,
        recv_wall_ns=wall + 50_000_000_000,
        bid_price=Decimal("103"),
        ask_price=Decimal("104"),
    )
    opportunity = SimulationOpportunity(
        opportunity_id=f"opp-{index}",
        entry_quote=entry,
        exit_quote=exit_quote,
    )
    signed = Decimal(outcome_direction)
    return SignalFeatureRow(
        row_id=f"row-{index}",
        source_segment_id=f"segment-{index // 17}",
        opportunity=opportunity,
        decision_invalid_reasons=(),
        hl_spread_bps=_feature("99.5", entry.event_id, mono, wall),
        hl_bbo_imbalance=_feature(h2_value, entry.event_id, mono, wall),
        binance_mid_return_5s_bps=_feature(
            h1_value,
            f"reference-{index}",
            mono,
            wall,
        ),
        outcome=OutcomeLabel(
            signed_mid_return_bps=signed,
            direction=outcome_direction,
            exit_event_id=exit_quote.event_id,
            exit_recv_mono_ns=exit_quote.recv_mono_ns,
            exit_recv_wall_ns=exit_quote.recv_wall_ns,
            invalid_reasons=(),
        ),
    )


def _selection_rows(
    *,
    h1_value: str = "1",
    h2_value: str = "-0.2",
    outcome_direction: int = 1,
) -> tuple[SignalFeatureRow, ...]:
    return tuple(
        _row(
            index,
            h1_value=h1_value,
            h2_value=h2_value,
            outcome_direction=outcome_direction,
        )
        for index in range(EXPECTED_SELECTION_ROW_COUNT)
    )


def test_exact_binomial_upper_tail_is_deterministic() -> None:
    assert exact_binomial_upper_tail(correct=3, total=4) == Decimal("0.3125")
    assert exact_binomial_upper_tail(correct=4, total=4) == Decimal("0.0625")
    assert exact_binomial_upper_tail(correct=0, total=0) == Decimal("1")

    with pytest.raises(SignalSelectionValidationError, match="binomial"):
        exact_binomial_upper_tail(correct=5, total=4)


def test_dependence_diagnostics_are_bounded_and_deterministic() -> None:
    constant = correctness_autocorrelations((1, 1, 1, 1, 1))
    assert constant[:4] == (Decimal("0"),) * 4
    assert constant[4:] == (None,) * 6

    alternating = correctness_autocorrelations((0, 1, 0, 1, 0, 1))
    design = dependence_design_effect(alternating)
    effective = effective_sample_size(
        evaluable_count=6,
        design_effect=design,
    )
    assert design >= 1
    assert 1 <= effective <= 6


def test_wilson_lower_bound_uses_effective_sample_size() -> None:
    full = wilson_lower_bound(correct=80, total=100, effective_n=100)
    reduced = wilson_lower_bound(correct=80, total=100, effective_n=25)
    assert full is not None
    assert reduced is not None
    assert Decimal("0") <= reduced < full <= Decimal("1")


def test_selection_h1_passes_and_h2_fails_on_opposite_registered_signs() -> None:
    report = evaluate_registered_selection(_selection_rows())

    assert report.decision is SelectionDecision.SELECTION_CHAMPION_H1
    assert report.champion_hypothesis_id == H1_ID
    assert [trial.hypothesis_id for trial in report.trials] == [H1_ID, H2_ID]

    h1, h2 = report.trials
    assert h1.directional_evaluable_count == EXPECTED_SELECTION_ROW_COUNT
    assert h1.correct_direction_count == EXPECTED_SELECTION_ROW_COUNT
    assert h1.passed is True
    assert h1.mean_partial_known_cost_pnl is not None
    assert h1.mean_partial_known_cost_pnl > 0

    assert h2.correct_direction_count == 0
    assert h2.passed is False
    assert report.controls[0].opportunity_ids_sha256 == report.selection_opportunity_ids_sha256
    assert report.controls[1].opportunity_ids_sha256 == report.selection_opportunity_ids_sha256


def test_exact_tie_break_is_lexicographic_hypothesis_id() -> None:
    report = evaluate_registered_selection(_selection_rows(h1_value="1", h2_value="0.2"))

    assert all(trial.passed for trial in report.trials)
    assert report.trials[0].wilson_lower_bound == report.trials[1].wilson_lower_bound
    assert report.decision is SelectionDecision.SELECTION_CHAMPION_H1
    assert report.champion_hypothesis_id == H1_ID


def test_insufficient_directional_support_is_inconclusive() -> None:
    report = evaluate_registered_selection(_selection_rows(outcome_direction=0))

    assert report.decision is SelectionDecision.INCONCLUSIVE_SELECTION
    assert report.champion_hypothesis_id is None
    assert all(
        "INSUFFICIENT_DIRECTIONAL_EVALUABLE_SUPPORT" in trial.failure_reasons
        for trial in report.trials
    )


def test_confirmation_row_is_rejected_before_evaluation() -> None:
    rows = list(_selection_rows())
    last = rows[-1]
    shifted_entry = replace(
        last.opportunity.entry_quote,
        recv_wall_ns=CONFIRMATION_START_WALL_NS,
    )
    exit_quote = last.opportunity.exit_quote
    assert exit_quote is not None
    shifted_exit = replace(
        exit_quote,
        recv_wall_ns=CONFIRMATION_START_WALL_NS + 50_000_000_000,
    )
    rows[-1] = replace(
        last,
        opportunity=replace(
            last.opportunity,
            entry_quote=shifted_entry,
            exit_quote=shifted_exit,
        ),
    )

    with pytest.raises(SignalSelectionValidationError, match="confirmation row"):
        evaluate_registered_selection(tuple(rows))


def test_protocol_and_dataset_sha_mismatch_hard_fail() -> None:
    rows = _selection_rows()

    with pytest.raises(SignalSelectionValidationError, match="protocol SHA-256"):
        evaluate_registered_selection(rows, protocol_sha256="0" * 64)
    with pytest.raises(SignalSelectionValidationError, match="dataset SHA-256"):
        evaluate_registered_selection(rows, dataset_sha256="0" * 64)


def test_selection_report_bytes_and_digest_are_deterministic() -> None:
    rows = _selection_rows()
    first = evaluate_registered_selection(rows)
    second = evaluate_registered_selection(rows)

    assert first.to_json_bytes() == second.to_json_bytes()
    assert first.sha256 == second.sha256
    assert len(first.sha256) == 64
    assert first.as_dict()["confirmation_opened"] is False


def test_selection_report_writer_is_immutable(tmp_path: Path) -> None:
    report = evaluate_registered_selection(_selection_rows())
    target = tmp_path / "selection.json"

    assert write_selection_report(report, target) == target
    assert target.read_bytes() == report.to_json_bytes()
    assert write_selection_report(report, target) == target

    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SignalSelectionValidationError, match="differs"):
        write_selection_report(report, target)
