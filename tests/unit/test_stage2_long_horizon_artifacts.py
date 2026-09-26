from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptobot.research.long_horizon import (
    CACHE_SHA256,
    DETERMINISTIC_RESULTS_SHA256,
    HORIZON_CONTEXT_SHA256,
    HORIZON_DECISION_SHA256,
    LOGISTIC_RESULTS_SHA256,
    REGISTRY_SHA256,
)

ROOT = Path("artifacts/stage_2")

EXPECTED = {
    "binance_development_horizon_1_2_5m.json": HORIZON_CONTEXT_SHA256,
    "economic_horizon_development_decision.json": HORIZON_DECISION_SHA256,
    "economic_300s_registry.json": REGISTRY_SHA256,
    "economic_300s_development_cache.json": CACHE_SHA256,
    "economic_300s_deterministic_results.json": DETERMINISTIC_RESULTS_SHA256,
    "economic_300s_logistic_results.json": LOGISTIC_RESULTS_SHA256,
    "economic_300s_decision.json": (
        "b36027ab6436258b4970e974280ee3669813c585d7deb96a29f00079aca12eb6"
    ),
}


def test_task024_artifact_hash_chain_is_frozen() -> None:
    for name, expected in EXPECTED.items():
        raw = (ROOT / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected


def test_task024_decision_is_stop_and_holdout_closed() -> None:
    payload = json.loads((ROOT / "economic_300s_decision.json").read_bytes())

    assert payload["report_version"] == "stage2-long-horizon-development-v1"
    assert payload["decision"] == "STOP_300S_FAMILY"
    assert payload["horizon_seconds"] == 300
    assert payload["deterministic_passing_candidates"] == []
    assert payload["logistic_passing_gates"] == []
    assert payload["old_confirmation_status"] == "UNOPENED_AND_EXCLUDED"
    assert payload["fresh_test_evidence_collected"] is False


def test_task024_registry_is_pre_outcome() -> None:
    registry = json.loads((ROOT / "economic_300s_registry.json").read_bytes())
    decision = json.loads((ROOT / "economic_horizon_development_decision.json").read_bytes())

    assert registry["created_before_hyperliquid_300s_outcome_evaluation"] is True
    assert (
        registry["horizon_decision_sha256"]
        == EXPECTED["economic_horizon_development_decision.json"]
    )
    assert registry["old_confirmation"] == "EXCLUDED_AND_UNOPENED"
    assert decision["chosen_development_horizon_seconds"] == 300
