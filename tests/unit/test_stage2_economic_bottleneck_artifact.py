from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_task026_economic_bottleneck_artifact_is_frozen() -> None:
    path = Path("artifacts/stage_2/economic_bottleneck_adjudication.json")
    raw = path.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "4c90657accb99a0caff44336bbca091b887f99cd9caedada01fd15364b77b39b"
    )
    assert payload["report_version"] == "stage2-task026-economic-bottleneck-v1"
    assert payload["selected_primary_path"] == ("PROSPECTIVE_DEVELOPMENT_EVIDENCE_EXPANSION")
    assert payload["old_confirmation_status"] == "UNOPENED_AND_EXCLUDED"
    assert payload["new_model_or_test_evidence_consumed"] is False
    assert payload["fresh_registered_test_started"] is False
    assert payload["user_action_required_now"] is False
    assert payload["source_sha256"]["signal_protocol"] == (
        "2e2404b93e82ad8ac6ff27b10b5f4d22cd7ac624be69a277c6aed75a3b9c9843"
    )
    plan = payload["evidence_expansion_plan"]
    assert plan["fixed_duration_hours"] == 72
    assert plan["nominal_decision_intervals"] == 5184
    assert plan["projected_valid_targets_at_observed_rate"].startswith("1186.")
    assert plan["projected_positive_targets_at_observed_rate"].startswith("69.")
