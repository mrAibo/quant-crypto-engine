from __future__ import annotations

import json
from pathlib import Path

from cryptobot.research.signal_protocol import (
    H1_ID,
    H2_ID,
    HORIZON_NS,
    MAX_EXECUTION_STEP_NS,
    MAX_FEATURE_AGE_NS,
    RANDOM_CONTROL_SEED,
    REFERENCE_LOOKBACK_NS,
    TRIAL_REGISTRY,
    PowerPlan,
)


def test_stage2_protocol_artifact_matches_frozen_code_contract() -> None:
    payload = json.loads(Path("artifacts/stage_2/signal_protocol.json").read_text(encoding="utf-8"))

    assert payload["protocol_version"] == "stage2-signal-protocol-v1"
    assert payload["frozen_before_candidate_outcome_inspection"] is True
    assert payload["timing"]["target_horizon_ns"] == HORIZON_NS
    assert payload["timing"]["reference_lookback_ns"] == REFERENCE_LOOKBACK_NS
    assert payload["timing"]["max_feature_age_ns"] == MAX_FEATURE_AGE_NS
    assert payload["timing"]["max_execution_step_ns"] == MAX_EXECUTION_STEP_NS

    assert payload["features"]["H1"]["hypothesis_id"] == H1_ID
    assert payload["features"]["H2"]["hypothesis_id"] == H2_ID

    power = PowerPlan()
    assert payload["power_plan"]["selection_min_evaluable"] == (power.selection_min_evaluable)
    assert payload["power_plan"]["confirmation_min_evaluable"] == (power.confirmation_min_evaluable)

    assert payload["trial_registry"]["sha256"] == TRIAL_REGISTRY.sha256
    assert payload["controls"]["random_seed"] == RANDOM_CONTROL_SEED

    assert payload["partitions"]["development"]["row_count"] == 1110
    assert payload["partitions"]["selection"]["row_count"] == 847
    assert payload["partitions"]["selection"]["h1_ready"] == 783
    assert payload["partitions"]["confirmation"]["row_count"] == 1302
    assert payload["partitions"]["confirmation"]["h1_ready"] == 1225

    assert payload["primary_dataset"]["sha256"] == (
        "3eeb0b405a9db439b7711b453ec9820707068bbfba855bf120124b79aa32b237"
    )
    assert payload["business_net_boundary"]["current_status"] == "NOT_EVALUABLE"
    assert payload["business_net_boundary"]["partial_known_cost_pnl_is_not_business_net"] is True
