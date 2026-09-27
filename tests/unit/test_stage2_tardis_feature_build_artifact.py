from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast


def test_task029_feature_build_report_is_frozen() -> None:
    path = Path("artifacts/stage_2/tardis_historical_feature_build_report.json")
    raw = path.read_bytes()
    payload = cast(dict[str, object], json.loads(raw))

    assert hashlib.sha256(raw).hexdigest() == (
        "645e247ea9589935f4b7a09cb98559d0df704ebc6c60287863d72303f6e68195"
    )
    assert payload["report_version"] == "stage2-task029-feature-cache-build-v1"
    assert payload["protocol_sha256"] == (
        "75fc97ab0ee68185704a06c81fd9fce06c0b1df5e32871dbac6247133ab53da1"
    )
    assert payload["lakehouse_manifest_sha256"] == (
        "c5032eda1f33421a6d71560e42e0f3e042b1ccd78647e358ea8b0390b4fc0e5f"
    )
    assert payload["parquet_set_sha256"] == (
        "4d451076c74fa706d57b3565a16cc5aa78875664c68fb934ab72c687257a7a2b"
    )
    assert payload["row_count_50s"] == 33965
    assert payload["row_count_300s"] == 5756
    assert payload["cache_50s_sha256"] == (
        "409ef9c60bfcbb048b593fc16f1d34cc84da1f0087ea372b7c4c799d3d030640"
    )
    assert payload["cache_300s_sha256"] == (
        "49fea618533a359727cfce3d95d2b50ee876c6fa2d75931f4b4e305e3938b3b3"
    )
    assert payload["economic_summary_computed"] is False
    assert payload["model_fitted"] is False


def test_task029_feature_build_day_counts_cover_exact_20_days() -> None:
    payload = cast(
        dict[str, object],
        json.loads(
            Path("artifacts/stage_2/tardis_historical_feature_build_report.json").read_bytes()
        ),
    )
    days_50 = cast(dict[str, int], payload["day_counts_50s"])
    days_300 = cast(dict[str, int], payload["day_counts_300s"])

    assert len(days_50) == 20
    assert len(days_300) == 20
    assert sum(days_50.values()) == 33965
    assert sum(days_300.values()) == 5756
    assert min(days_50) == "2024-11-01"
    assert max(days_50) == "2026-06-01"
    assert set(days_50) == set(days_300)
