from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_task025_registry_is_frozen() -> None:
    path = Path("artifacts/stage_2/microstructure_development_registry.json")
    raw = path.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "d5024ce6cb16c0d3dcce5b65f3f62f6d577b971d3bda7c8342ab67aaa100b130"
    )
    assert payload["registry_version"] == "stage2-microstructure-development-registry-v1"
    assert payload["old_confirmation"] == "EXCLUDED_AND_UNOPENED"
    assert len(payload["features"]) == 8


def test_task025_decision_is_frozen_stop() -> None:
    path = Path("artifacts/stage_2/microstructure_decision.json")
    raw = path.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "6355dd1295ab156757e091191ee686f6f9e63708a3bb556e03611b25285f7172"
    )
    assert payload["decision"] == "STOP_MICROSTRUCTURE_FAMILY"
    assert payload["old_confirmation_used"] is False
    assert payload["fresh_development_validation_started"] is False
    assert payload["fresh_registered_test_started"] is False
    assert payload["horizon_50s"]["positive_target_count"] == 24
    assert payload["horizon_300s"]["positive_target_count"] == 6
