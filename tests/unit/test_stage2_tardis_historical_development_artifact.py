from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast


def test_task029_historical_development_report_is_frozen() -> None:
    path = Path("artifacts/stage_2/tardis_historical_development_report.json")
    raw = path.read_bytes()
    payload = cast(dict[str, object], json.loads(raw))

    assert hashlib.sha256(raw).hexdigest() == (
        "fec2e2c9a081b4edb5e84e4bcc04fdd569d5e3746daa93befbf9f23e7d6b2fe7"
    )
    assert payload["report_version"] == "stage2-task029-historical-development-v1"
    assert payload["protocol_sha256"] == (
        "75fc97ab0ee68185704a06c81fd9fce06c0b1df5e32871dbac6247133ab53da1"
    )
    assert payload["feature_build_report_sha256"] == (
        "645e247ea9589935f4b7a09cb98559d0df704ebc6c60287863d72303f6e68195"
    )
    assert payload["cache_50s_sha256"] == (
        "409ef9c60bfcbb048b593fc16f1d34cc84da1f0087ea372b7c4c799d3d030640"
    )
    assert payload["cache_300s_sha256"] == (
        "49fea618533a359727cfce3d95d2b50ee876c6fa2d75931f4b4e305e3938b3b3"
    )
    assert payload["decision"] == "STOP_HISTORICAL_MICROSTRUCTURE_DEVELOPMENT"
    assert payload["selected_horizon_seconds"] is None
    assert payload["current_task027_repurposed_as_selection"] is False
    assert payload["old_confirmation_status"] == "UNOPENED_AND_EXCLUDED"
    assert payload["fresh_selection_started"] is False
    assert payload["fresh_confirmation_started"] is False


def test_task029_50s_dev_b_fails_frozen_economic_gate() -> None:
    payload = cast(
        dict[str, object],
        json.loads(
            Path("artifacts/stage_2/tardis_historical_development_report.json").read_bytes()
        ),
    )
    horizon = cast(dict[str, object], payload["horizon_50s"])
    support = cast(dict[str, object], horizon["support"])
    evaluation = cast(dict[str, object], horizon["dev_b_evaluation"])

    assert horizon["dev_a_row_count"] == 20370
    assert horizon["dev_b_row_count"] == 13595
    assert support["feature_complete_count"] == 18987
    assert support["valid_target_count"] == 18974
    assert support["positive_target_count"] == 729
    assert support["nonpositive_target_count"] == 18245
    assert support["supported"] is True

    assert evaluation["eligible_rows"] == 13380
    assert evaluation["selected_trades"] == 15
    assert evaluation["positive_selected_trades"] == 5
    assert evaluation["mean_known_net_quote"] == "-27.1270700000000000000"
    assert evaluation["cumulative_known_net_quote"] == "-406.9060500000000000000"
    assert evaluation["median_known_net_bps"] == ("-12.23269728331177231565329884")
    assert evaluation["early_selected_trades"] == 7
    assert evaluation["late_selected_trades"] == 8
    assert evaluation["passed"] is False


def test_task029_300s_dev_b_fails_frozen_economic_gate() -> None:
    payload = cast(
        dict[str, object],
        json.loads(
            Path("artifacts/stage_2/tardis_historical_development_report.json").read_bytes()
        ),
    )
    horizon = cast(dict[str, object], payload["horizon_300s"])
    support = cast(dict[str, object], horizon["support"])
    evaluation = cast(dict[str, object], horizon["dev_b_evaluation"])

    assert horizon["dev_a_row_count"] == 3454
    assert horizon["dev_b_row_count"] == 2302
    assert support["feature_complete_count"] == 3224
    assert support["valid_target_count"] == 3214
    assert support["positive_target_count"] == 570
    assert support["nonpositive_target_count"] == 2644
    assert support["supported"] is True

    assert evaluation["eligible_rows"] == 2259
    assert evaluation["selected_trades"] == 1
    assert evaluation["positive_selected_trades"] == 0
    assert evaluation["mean_known_net_quote"] == "-212.5421000000000000000"
    assert evaluation["median_known_net_bps"] == ("-31.56019006607765981141881357")
    assert evaluation["passed"] is False
