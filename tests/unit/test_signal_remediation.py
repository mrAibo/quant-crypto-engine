from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path

import pytest

from cryptobot.research.signal_remediation import (
    RemediationDecision,
    RemediationValidationError,
    build_remediation_report,
    load_selection_result,
    wilson_lower_bound,
    write_remediation_report,
)

SELECTION_PATH = Path("artifacts/stage_2/selection_result.json")


def _selection() -> dict[str, object]:
    return load_selection_result(SELECTION_PATH)


def test_task022_frozen_selection_stops_registered_family() -> None:
    report = build_remediation_report(_selection())

    assert report.decision is RemediationDecision.STOP_REGISTERED_H1_H2_FAMILY
    assert report.old_confirmation_status == "UNOPENED_AND_EXCLUDED"
    assert report.historical_data_role == (
        "DIAGNOSTIC_AND_NEW_FAMILY_DEVELOPMENT_ONLY_NOT_CONFIRMATORY"
    )
    assert report.h1_gap_to_partial_known_cost_breakeven == Decimal(
        "74.0311082956259426847662141779788838612368024132730015082956"
    )
    assert report.h2_gap_to_partial_known_cost_breakeven == Decimal(
        "71.1355103950103950103950103950103950103950103950103950103950"
    )


def test_counterfactual_h1_plan_buffers_attrition_and_dependence() -> None:
    plan = build_remediation_report(_selection()).h1_counterfactual_plan

    assert plan.registered is False
    assert [stage.name for stage in plan.attrition_stages] == [
        "FEATURE_READY",
        "NONZERO_ACTION_GIVEN_FEATURE_READY",
        "VALID_EXECUTABLE_GIVEN_ACTION",
        "NONZERO_OUTCOME_GIVEN_TRADED",
    ]
    assert plan.selection_directional_rows_after_dependence == 863
    assert plan.confirmation_directional_rows_after_dependence == 1350
    assert plan.selection_fresh_rows == 1719
    assert plan.confirmation_fresh_rows == 2688
    assert plan.total_fresh_rows == 4407
    assert Decimal("0.50") < plan.conservative_directional_yield < Decimal("0.51")


def test_wilson_planning_lower_bound_is_below_observed_rate() -> None:
    lower = wilson_lower_bound(numerator=1059, denominator=1123)

    assert Decimal(1059) / Decimal(1123) > lower > Decimal("0.9")

    with pytest.raises(RemediationValidationError, match="Wilson"):
        wilson_lower_bound(numerator=2, denominator=1)


def test_positive_h1_economics_with_support_failure_registers_fresh_replication() -> None:
    payload = copy.deepcopy(_selection())
    trials = payload["trials"]
    assert isinstance(trials, list)
    h1 = trials[0]
    assert isinstance(h1, dict)
    h1["mean_partial_known_cost_pnl"] = "1"
    failures = h1["failure_reasons"]
    assert isinstance(failures, list)
    h1["failure_reasons"] = [
        item for item in failures if item != "NONPOSITIVE_MEAN_PARTIAL_KNOWN_COST_PNL"
    ]

    report = build_remediation_report(payload)

    assert report.decision is RemediationDecision.REGISTER_FRESH_H1_REPLICATION
    assert report.h1_counterfactual_plan.registered is True


def test_confirmation_opened_hard_fails() -> None:
    payload = copy.deepcopy(_selection())
    payload["confirmation_opened"] = True

    with pytest.raises(RemediationValidationError, match="confirmation"):
        build_remediation_report(payload)


def test_remediation_report_is_deterministic_and_immutable(tmp_path: Path) -> None:
    first = build_remediation_report(_selection())
    second = build_remediation_report(_selection())

    assert first.to_json_bytes() == second.to_json_bytes()
    assert first.sha256 == second.sha256

    target = tmp_path / "remediation.json"
    assert write_remediation_report(first, target) == target
    assert target.read_bytes() == first.to_json_bytes()
    assert write_remediation_report(first, target) == target

    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(RemediationValidationError, match="differs"):
        write_remediation_report(first, target)


def test_selection_sha_mismatch_hard_fails(tmp_path: Path) -> None:
    target = tmp_path / "selection.json"
    target.write_text(SELECTION_PATH.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(RemediationValidationError, match="SHA-256"):
        load_selection_result(target)
