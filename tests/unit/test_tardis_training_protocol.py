from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from cryptobot.research import tardis_training_protocol as tp


def test_task029_protocol_artifact_is_frozen() -> None:
    path = Path("artifacts/stage_2/tardis_historical_training_protocol.json")
    raw = path.read_bytes()
    payload = cast(dict[str, object], json.loads(raw))
    source = cast(dict[str, object], payload["source"])

    assert hashlib.sha256(raw).hexdigest() == (
        "75fc97ab0ee68185704a06c81fd9fce06c0b1df5e32871dbac6247133ab53da1"
    )
    assert raw == tp.protocol_bytes()
    assert payload["protocol_version"] == "stage2-task029-tardis-training-v1"
    assert payload["frozen_before_historical_outcome_use"] is True
    assert source["task028_corpus_manifest_sha256"] == tp.TASK028_CORPUS_SHA256
    assert source["task028_archive_set_sha256"] == tp.TASK028_ARCHIVE_SET_SHA256


def test_task029_whole_day_split_is_frozen_12_8() -> None:
    protocol = tp.build_protocol()
    split = cast(dict[str, object], protocol["split"])

    assert split["rule"] == "WHOLE_UTC_DAYS_CHRONOLOGICAL_60_40"
    assert split["dev_a_days"] == list(tp.DEV_A_DAYS)
    assert split["dev_b_days"] == list(tp.DEV_B_DAYS)
    assert len(tp.DEV_A_DAYS) == 12
    assert len(tp.DEV_B_DAYS) == 8
    assert set(tp.DEV_A_DAYS).isdisjoint(tp.DEV_B_DAYS)


def test_task029_preserves_task025_family_and_no_sweeps() -> None:
    protocol = tp.build_protocol()
    features = cast(dict[str, object], protocol["feature_semantics"])
    model = cast(dict[str, object], protocol["model"])
    decision = cast(dict[str, object], protocol["decision"])
    storage = cast(dict[str, object], protocol["storage_layer"])
    query_catalog = cast(dict[str, object], storage["query_catalog"])

    assert features["feature_names"] == list(tp.FEATURE_NAMES)
    assert features["max_anchor_or_current_staleness_us"] == 2_000_000
    assert features["unknown_trade_side"] == ("FEATURE_MISSING_IF_ANY_UNKNOWN_SIDE_TRADE_IN_WINDOW")
    assert model["training_partition"] == "DEV_A_ONLY"
    assert model["hyperparameter_sweep"] is False
    assert decision["current_task027_may_be_repurposed_as_selection"] is False
    assert decision["old_confirmation"] == "UNOPENED_AND_EXCLUDED"
    assert storage["source_of_truth"] == "TASK028_IMMUTABLE_RAW_PLUS_MANIFESTS"
    assert storage["economic_outcomes_materialized_during_conversion"] is False
    assert query_catalog["engine"] == "DuckDB"
    assert query_catalog["version"] == "1.5.5"


def test_task029_horizon_support_and_pass_rules_are_frozen() -> None:
    protocol = tp.build_protocol()
    horizons = cast(list[dict[str, object]], protocol["horizons"])
    evaluation = cast(dict[str, object], protocol["dev_b_evaluation"])
    decision_stream = cast(dict[str, object], protocol["decision_stream"])

    assert horizons == [dict(item) for item in tp.HORIZONS]
    assert [item["horizon_seconds"] for item in horizons] == [50, 300]
    pass_rules = cast(list[str], evaluation["pass_rules"])
    assert evaluation["no_threshold_or_hyperparameter_tuning"] is True
    assert len(pass_rules) == 7
    assert decision_stream["max_inter_snapshot_gap_us"] == 15_000_000
