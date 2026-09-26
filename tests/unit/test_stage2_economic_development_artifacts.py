from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_stage2_deterministic_economic_development_artifact() -> None:
    path = Path("artifacts/stage_2/economic_family_development.json")
    raw = path.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "ae62dff1172ca7666b1119c4c8a0f1ca61757f428c30b66b73a208b34c2a3b67"
    )
    assert payload["report_version"] == "stage2-economic-family-development-v1"
    assert payload["decision"] == "DEVELOP_REGULARIZED_LOGISTIC_BASELINE"
    assert payload["deterministic_shortlist"] == []
    assert payload["confirmation_used"] is False


def test_stage2_logistic_economic_development_artifact() -> None:
    path = Path("artifacts/stage_2/economic_logistic_development.json")
    raw = path.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "285775b8febb226414bd838121f99b15b72d5b46edb13383b12398b8c80ccaf8"
    )
    assert payload["report_version"] == "stage2-economic-logistic-development-v1"
    assert payload["decision"] == "STOP_LOGISTIC_DEVELOPMENT"
    assert payload["old_confirmation_used"] is False
    assert payload["dev_b_evaluation"]["selected_trades"] == 1
    assert payload["dev_b_evaluation"]["mean_known_net_quote"] == "-129.9582"
