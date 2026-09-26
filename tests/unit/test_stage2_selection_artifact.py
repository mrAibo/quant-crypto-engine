from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_stage2_selection_artifact_is_frozen_inconclusive_result() -> None:
    path = Path("artifacts/stage_2/selection_result.json")
    raw = path.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "e3403ef3eb6016040344dd8c17f4174b9190ca1a3aa5f5a59f54e1af7f7fb5a0"
    )
    assert payload["report_version"] == "stage2-selection-v1"
    assert payload["decision"] == "INCONCLUSIVE_SELECTION"
    assert payload["champion_hypothesis_id"] is None
    assert payload["confirmation_opened"] is False
    assert payload["business_net_evaluable"] is False
    assert payload["selection_row_count"] == 1123
    assert payload["protocol_sha256"] == (
        "2e2404b93e82ad8ac6ff27b10b5f4d22cd7ac624be69a277c6aed75a3b9c9843"
    )
    assert payload["dataset_sha256"] == (
        "3eeb0b405a9db439b7711b453ec9820707068bbfba855bf120124b79aa32b237"
    )

    h1, h2 = payload["trials"]
    assert h1["trial_id"] == "S2-SEL-H1-V1"
    assert h1["directional_evaluable_count"] == 644
    assert h1["passed"] is False
    assert "INSUFFICIENT_DIRECTIONAL_EVALUABLE_SUPPORT" in h1["failure_reasons"]

    assert h2["trial_id"] == "S2-SEL-H2-V1"
    assert h2["directional_evaluable_count"] == 930
    assert h2["passed"] is False
    assert h2["wilson_lower_bound"].startswith("0.5488145153")
    assert h2["mean_partial_known_cost_pnl"].startswith("-71.135510")
    assert h2["failure_reasons"] == ["NONPOSITIVE_MEAN_PARTIAL_KNOWN_COST_PNL"]