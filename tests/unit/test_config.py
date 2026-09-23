from __future__ import annotations

import json
from pathlib import Path

import pytest

from cryptobot.config import RecorderConfigError, load_recorder_config
from cryptobot.data.instruments import InstrumentRegistry, load_instrument_registry


def _registry() -> InstrumentRegistry:
    return load_instrument_registry(Path("config/instruments.yaml"))


def _source(**overrides: object) -> dict[str, object]:
    source: dict[str, object] = {
        "source_id": "hyperliquid-mainnet-public",
        "venue": "hyperliquid",
        "environment": "MAINNET",
        "enabled": True,
        "instrument_ids": [
            "hyperliquid.mainnet.perpetual.btc",
            "hyperliquid.mainnet.perpetual.eth",
        ],
        "channels": ["l2Book", "bbo", "trades", "activeAssetCtx"],
    }
    source.update(overrides)
    return source


def _config(**overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "schema_version": 1,
        "sources": [_source()],
        "reference_feed": {"required": True, "selected_source_id": None},
        "storage": {
            "root": "data",
            "raw_path": "raw",
            "normalized_path": "normalized",
            "artifact_path": "artifacts/stage_0",
        },
        "buffering": {
            "queue_capacity": None,
            "high_watermark_fraction": None,
        },
        "rollover": {
            "max_segment_bytes": None,
            "max_segment_age_seconds": None,
        },
        "reconnect": {
            "base_delay_seconds": None,
            "max_delay_seconds": None,
            "jitter_fraction": None,
        },
        "clock_health": {"record": True},
    }
    config.update(overrides)
    return config


def _write_config(tmp_path: Path, config: dict[str, object]) -> Path:
    path = tmp_path / "recorder.yaml"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_project_recorder_config_loads_without_invented_thresholds() -> None:
    config = load_recorder_config(Path("config/recorder.yaml"), _registry())

    assert config.sources[0].source_id == "hyperliquid-mainnet-public"
    assert config.reference_feed.required is True
    assert config.reference_feed.selected_source_id is None
    assert config.buffering.queue_capacity is None
    assert config.rollover.max_segment_bytes is None
    assert config.reconnect.base_delay_seconds is None
    assert config.clock_health.record is True


def test_unknown_top_level_field_is_rejected(tmp_path: Path) -> None:
    config = _config(mystery="value")
    path = _write_config(tmp_path, config)

    with pytest.raises(RecorderConfigError, match="unknown fields: mystery"):
        load_recorder_config(path, _registry())


def test_missing_required_field_is_rejected(tmp_path: Path) -> None:
    config = _config()
    del config["storage"]
    path = _write_config(tmp_path, config)

    with pytest.raises(RecorderConfigError, match="missing fields: storage"):
        load_recorder_config(path, _registry())


def test_unknown_instrument_reference_is_rejected(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        _config(
            sources=[
                _source(
                    instrument_ids=[
                        "hyperliquid.mainnet.perpetual.btc",
                        "hyperliquid.mainnet.perpetual.sol",
                    ]
                )
            ]
        ),
    )

    with pytest.raises(RecorderConfigError, match="unknown instrument_id"):
        load_recorder_config(path, _registry())


def test_duplicate_channel_is_rejected(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        _config(sources=[_source(channels=["bbo", "bbo"])]),
    )

    with pytest.raises(RecorderConfigError, match="must not contain duplicates"):
        load_recorder_config(path, _registry())


def test_unsupported_channel_is_rejected(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        _config(sources=[_source(channels=["bbo", "candles"])]),
    )

    with pytest.raises(RecorderConfigError, match="unsupported channels"):
        load_recorder_config(path, _registry())


def test_source_must_match_instrument_venue_and_environment(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        _config(sources=[_source(environment="TESTNET")]),
    )

    with pytest.raises(RecorderConfigError, match="does not match"):
        load_recorder_config(path, _registry())


def test_reference_source_must_exist_when_selected(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        _config(
            reference_feed={
                "required": True,
                "selected_source_id": "reference-not-configured",
            }
        ),
    )

    with pytest.raises(RecorderConfigError, match="must reference a configured source"):
        load_recorder_config(path, _registry())


def test_parent_path_traversal_is_rejected(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        _config(
            storage={
                "root": "../data",
                "raw_path": "raw",
                "normalized_path": "normalized",
                "artifact_path": "artifacts/stage_0",
            }
        ),
    )

    with pytest.raises(RecorderConfigError, match="must not be absolute"):
        load_recorder_config(path, _registry())


def test_operational_thresholds_may_remain_explicitly_unset(tmp_path: Path) -> None:
    path = _write_config(tmp_path, _config())

    config = load_recorder_config(path, _registry())

    assert config.buffering.high_watermark_fraction is None
    assert config.rollover.max_segment_age_seconds is None
    assert config.reconnect.max_delay_seconds is None
    assert config.reconnect.jitter_fraction is None


def test_serialization_is_stable() -> None:
    first = load_recorder_config(Path("config/recorder.yaml"), _registry()).as_dict()
    second = load_recorder_config(Path("config/recorder.yaml"), _registry()).as_dict()

    assert first == second
