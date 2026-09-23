from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from cryptobot.data.clock import ClockSample
from cryptobot.data.rawlog import RawFrameMetadata
from cryptobot.data.recorder import (
    RecorderError,
    RecorderRuntimeSettings,
    RecorderState,
    RecorderSupervisor,
    RolloverMode,
    ShutdownOutcome,
    make_segment_id,
)


class FixedClock:
    def sample(self) -> ClockSample:
        return ClockSample(
            wall_ns=99_000,
            mono_ns=77_000,
            host_id="host",
            boot_id="boot",
        )


def _settings(**overrides: object) -> RecorderRuntimeSettings:
    values: dict[str, object] = {
        "queue_capacity": 4,
        "sync_every_frames": 2,
        "shutdown_drain_timeout_seconds": 1.0,
        "seal_on_shutdown": True,
        "rollover_mode": RolloverMode.DISABLED,
    }
    values.update(overrides)
    return RecorderRuntimeSettings(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("queue_capacity", 0),
        ("queue_capacity", -1),
        ("sync_every_frames", 0),
        ("sync_every_frames", -2),
        ("shutdown_drain_timeout_seconds", 0),
        ("shutdown_drain_timeout_seconds", -0.1),
    ],
)
def test_runtime_settings_reject_non_positive_values(field: str, value: object) -> None:
    with pytest.raises(RecorderError):
        _settings(**{field: value})


def test_runtime_settings_are_immutable() -> None:
    settings = _settings()

    with pytest.raises(FrozenInstanceError):
        settings.queue_capacity = 9  # type: ignore[misc]


def test_segment_id_is_deterministic_safe_and_input_sensitive() -> None:
    first = make_segment_id(
        source_id="Hyperliquid MAINNET/Public",
        start_wall_ns=123,
        connection_id="conn-a",
        run_id="run-1",
    )
    repeated = make_segment_id(
        source_id="Hyperliquid MAINNET/Public",
        start_wall_ns=123,
        connection_id="conn-a",
        run_id="run-1",
    )
    changed = make_segment_id(
        source_id="Hyperliquid MAINNET/Public",
        start_wall_ns=123,
        connection_id="conn-b",
        run_id="run-1",
    )

    assert first == repeated
    assert first != changed
    assert "/" not in first
    assert " " not in first
    assert first.startswith("hyperliquid-mainnet-public-123-")


def test_segment_id_rejects_invalid_run_id() -> None:
    with pytest.raises(RecorderError, match="run_id"):
        make_segment_id(
            source_id="source",
            start_wall_ns=1,
            connection_id="conn",
            run_id=" bad ",
        )


def test_initial_snapshot_is_explicit_and_immutable(tmp_path: Path) -> None:
    async def empty_source():
        if False:
            yield  # pragma: no cover

    supervisor = RecorderSupervisor(
        source=empty_source(),
        storage_root=tmp_path,
        manifest_path=tmp_path / "manifest.json",
        run_id="run-1",
        settings=_settings(),
        clock=FixedClock(),
    )

    status = supervisor.snapshot()

    assert status.state is RecorderState.INIT
    assert status.shutdown_outcome is ShutdownOutcome.NONE
    assert status.counters.received_frames == 0
    assert status.queue_size == 0
    assert status.segment_id is None
    with pytest.raises(FrozenInstanceError):
        status.state = RecorderState.RUNNING  # type: ignore[misc]


def test_metadata_contract_can_be_used_without_adapter_dependency() -> None:
    metadata = RawFrameMetadata(
        schema_version=1,
        source_id="source",
        recv_wall_ns=1,
        recv_mono_ns=2,
        host_id="host",
        boot_id="boot",
        connection_id="conn",
        ingest_seq=1,
        channel_hint="trades",
        capture_flags=("LIVE_CAPTURE",),
    )

    assert metadata.source_id == "source"
