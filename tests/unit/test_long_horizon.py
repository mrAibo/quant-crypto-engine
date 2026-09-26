from __future__ import annotations

import copy
from pathlib import Path

import pytest

from cryptobot.research.long_horizon import (
    DETERMINISTIC_RESULTS_SHA256,
    HORIZON_CONTEXT_SHA256,
    HORIZON_DECISION_SHA256,
    LOGISTIC_RESULTS_SHA256,
    REGISTRY_SHA256,
    LongHorizonDecision,
    LongHorizonValidationError,
    adjudicate_long_horizon,
    load_json_with_sha,
    write_long_horizon_report,
)

ARTIFACT_ROOT = Path("artifacts/stage_2")


def _load() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    return (
        load_json_with_sha(
            ARTIFACT_ROOT / "binance_development_horizon_1_2_5m.json",
            expected_sha256=HORIZON_CONTEXT_SHA256,
        ),
        load_json_with_sha(
            ARTIFACT_ROOT / "economic_horizon_development_decision.json",
            expected_sha256=HORIZON_DECISION_SHA256,
        ),
        load_json_with_sha(
            ARTIFACT_ROOT / "economic_300s_registry.json",
            expected_sha256=REGISTRY_SHA256,
        ),
        load_json_with_sha(
            ARTIFACT_ROOT / "economic_300s_deterministic_results.json",
            expected_sha256=DETERMINISTIC_RESULTS_SHA256,
        ),
        load_json_with_sha(
            ARTIFACT_ROOT / "economic_300s_logistic_results.json",
            expected_sha256=LOGISTIC_RESULTS_SHA256,
        ),
    )


def test_frozen_300s_evidence_stops_family() -> None:
    context, decision, registry, deterministic, logistic = _load()

    report = adjudicate_long_horizon(
        horizon_context=context,
        horizon_decision=decision,
        registry=registry,
        deterministic_results=deterministic,
        logistic_results=logistic,
    )

    assert report.decision is LongHorizonDecision.STOP_300S_FAMILY
    assert report.deterministic_passing_candidates == ()
    assert report.logistic_passing_gates == ()
    assert report.old_confirmation_status == "UNOPENED_AND_EXCLUDED"


def test_positive_deterministic_candidate_freezes_without_logistic_promotion() -> None:
    context, decision, registry, deterministic, logistic = _load()
    changed = copy.deepcopy(deterministic)
    results = changed["results"]
    assert isinstance(results, list)
    candidate = results[1]
    assert isinstance(candidate, dict)
    partitions = candidate["partitions"]
    assert isinstance(partitions, dict)
    dev_b = partitions["DEV_B"]
    assert isinstance(dev_b, dict)
    dev_b["valid_trade_count"] = 30
    dev_b["mean_partial_known_cost_pnl"] = "1"
    dev_b["sum_partial_known_cost_pnl"] = "30"

    report = adjudicate_long_horizon(
        horizon_context=context,
        horizon_decision=decision,
        registry=registry,
        deterministic_results=changed,
        logistic_results=logistic,
    )

    assert report.decision is LongHorizonDecision.FREEZE_300S_FAMILY
    assert report.deterministic_passing_candidates == ("E300_1_IMB_STRONG",)
    assert report.logistic_passing_gates == ()


def test_positive_logistic_gate_freezes_when_deterministic_candidates_fail() -> None:
    context, decision, registry, deterministic, logistic = _load()
    changed = copy.deepcopy(logistic)
    gates = changed["gates"]
    assert isinstance(gates, dict)
    gate = gates["LOGIT300_TOP10"]
    assert isinstance(gate, dict)
    dev_b = gate["DEV_B"]
    assert isinstance(dev_b, dict)
    dev_b["valid_trade_count"] = 30
    dev_b["mean_partial_known_cost_pnl"] = "2"
    dev_b["sum_partial_known_cost_pnl"] = "60"

    report = adjudicate_long_horizon(
        horizon_context=context,
        horizon_decision=decision,
        registry=registry,
        deterministic_results=deterministic,
        logistic_results=changed,
    )

    assert report.decision is LongHorizonDecision.FREEZE_300S_FAMILY
    assert report.logistic_passing_gates == ("LOGIT300_TOP10",)


def test_hash_chain_mismatch_hard_fails() -> None:
    context, decision, registry, deterministic, logistic = _load()
    changed = copy.deepcopy(registry)
    changed["horizon_decision_sha256"] = "0" * 64

    with pytest.raises(LongHorizonValidationError, match="horizon-decision"):
        adjudicate_long_horizon(
            horizon_context=context,
            horizon_decision=decision,
            registry=changed,
            deterministic_results=deterministic,
            logistic_results=logistic,
        )


def test_long_horizon_report_writer_is_immutable(tmp_path: Path) -> None:
    context, decision, registry, deterministic, logistic = _load()
    report = adjudicate_long_horizon(
        horizon_context=context,
        horizon_decision=decision,
        registry=registry,
        deterministic_results=deterministic,
        logistic_results=logistic,
    )
    target = tmp_path / "report.json"

    assert write_long_horizon_report(report, target) == target
    assert target.read_bytes() == report.to_json_bytes()
    assert write_long_horizon_report(report, target) == target

    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(LongHorizonValidationError, match="differs"):
        write_long_horizon_report(report, target)
