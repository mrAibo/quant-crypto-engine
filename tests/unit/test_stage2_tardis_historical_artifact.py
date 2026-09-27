from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_task028_tardis_protocol_artifact_is_frozen() -> None:
    path = Path("artifacts/stage_2/tardis_historical_development_protocol.json")
    raw = path.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "8d08ffa54eb64a3ecf11b9a73e3eea5d815f60560e7a93ad6796c63d2760b735"
    )
    assert payload["protocol_version"] == "stage2-task028-tardis-historical-v1"
    assert payload["evidence_role"] == "DEVELOPMENT_ONLY_EXTERNAL_RECEIVE_TIME"
    assert payload["first_day"] == "2024-11-01"
    assert payload["last_day"] == "2026-06-01"
    assert payload["day_count"] == 20
    assert payload["coverage_hours"] == 480
    assert payload["expected_archive_count"] == 80
    assert payload["hyperliquid_fastbook_cutoff"] == "2026-06-17"
    assert payload["old_confirmation"] == "UNOPENED_AND_EXCLUDED"
    assert payload["model_fitting_allowed_in_task028"] is False


def test_task028_tardis_corpus_manifest_is_frozen() -> None:
    path = Path("artifacts/stage_2/tardis_historical_corpus_manifest.json")
    raw = path.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "9696dca5f57fe160a8438236f1af82947a1588d2476a882fdf627f4cbd26e5e8"
    )
    assert payload["report_version"] == "stage2-task028-tardis-corpus-v1"
    assert payload["protocol_sha256"] == (
        "8d08ffa54eb64a3ecf11b9a73e3eea5d815f60560e7a93ad6796c63d2760b735"
    )
    assert payload["complete"] is True
    assert payload["archive_count"] == 80
    assert payload["total_compressed_bytes"] == 1180336813
    assert payload["archive_set_sha256"] == (
        "8e545456b34c6d1dabdb4e31fc13a0cb174bb96fef01eb137d9c32fa1dcb37fc"
    )
    assert payload["economic_outcomes_consumed"] is False
    assert payload["model_fitted"] is False
    assert payload["old_confirmation_status"] == "UNOPENED_AND_EXCLUDED"
