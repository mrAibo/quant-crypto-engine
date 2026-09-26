from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_stage2_remediation_artifact_is_frozen_family_stop() -> None:
    path = Path("artifacts/stage_2/selection_remediation.json")
    raw = path.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "fec7cbb77fe67c672a2319fadee7e6a94f79fef013c16c6033b55fbb07f574d5"
    )
    assert payload["report_version"] == "stage2-selection-remediation-v1"
    assert payload["decision"] == "STOP_REGISTERED_H1_H2_FAMILY"
    assert payload["old_confirmation_status"] == "UNOPENED_AND_EXCLUDED"
    assert payload["historical_data_role"] == (
        "DIAGNOSTIC_AND_NEW_FAMILY_DEVELOPMENT_ONLY_NOT_CONFIRMATORY"
    )

    plan = payload["h1_counterfactual_plan"]
    assert plan["registered"] is False
    assert plan["selection_fresh_rows"] == 1719
    assert plan["confirmation_fresh_rows"] == 2688
    assert plan["total_fresh_rows"] == 4407
