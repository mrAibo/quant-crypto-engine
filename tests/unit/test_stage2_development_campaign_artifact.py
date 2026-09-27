from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_task027_campaign_protocol_is_frozen() -> None:
    path = Path("artifacts/stage_2/development_campaign_protocol.json")
    raw = path.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "1ab9a735f512dd301392ba568b49ebd0f1e80d676f073b3d502bf73d111bc1d3"
    )
    assert payload["protocol_version"] == "stage2-task027-development-campaign-v1"
    assert payload["evidence_role"] == "DEVELOPMENT_ONLY"
    assert payload["duration_seconds"] == 259200
    assert payload["segment_seconds"] == 900
    assert payload["horizons_seconds"] == [50, 300]
    assert payload["old_confirmation"] == "UNOPENED_AND_EXCLUDED"
    assert payload["model_fitting_allowed"] is False
    assert payload["fresh_registered_test_evidence"] is False
    assert payload["private_account_access_required"] is False
    assert payload["aws_requester_pays_required"] is False
    assert payload["runtime_config_sha256"] == (
        "8bf2a31ec634b475f1e3b559663bb35e16950c1c721ab73ddc5812cd6b1f03e1"
    )
    assert payload["development_eligibility"]["feature_family"] == (
        "TASK025_EIGHT_FEATURE_MICROSTRUCTURE_V1_UNCHANGED"
    )
    assert payload["capture_transport"]["extra_public_frames"] == (
        "PRESERVE_RAW_BUT_EXCLUDE_FROM_TASK027_ELIGIBILITY"
    )
