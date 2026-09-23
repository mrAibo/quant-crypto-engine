from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from cryptobot.data.clock import ClockSample
from cryptobot.data.manifest import SegmentManifestRecord
from cryptobot.data.rawlog import RawFrameMetadata, RawRef
from cryptobot.data.recorder import (
    RecorderFailureCode,
    RecorderRuntimeSettings,
    RecorderState,
    RecorderSupervisor,
    RolloverMode,
    ShutdownOutcome,
)


@dataclass(frozen=True, slots=True)
class FakeFrame:
    metadata: RawFrameMetadata
    payload: bytes


class FixedClock:
    def sample(self) -> ClockSample:
        return ClockSample(
            wall_ns=90_000,
            mono_ns=91_000,
            host_id="host",
            boot_id="boot",
        )


def _frame() -> FakeFrame:
    return FakeFrame(
        metadata=RawFrameMetadata(
            schema_version=1,
            source_id="source",
            recv_wall_ns=1,
            recv_mono_ns=2,
            host_id="host",
            boot_id="boot",
            connection_id="conn",
            ingest_seq=1,
            channel_hint="bbo",
            capture_flags=("LIVE_CAPTURE",),
        ),
        payload=b"payload",
    )


def _settings(
    *,
    sync_every_frames: int = 1,
    drain: float = 0.2,
) -> RecorderRuntimeSettings:
    return RecorderRuntimeSettings(
        queue_capacity=2,
        sync_every_frames=sync_every_frames,
        shutdown_drain_timeout_seconds=drain,
        seal_on_shutdown=True,
        rollover_mode=RolloverMode.DISABLED,
    )


async def _one_frame_source() -> AsyncIterator[FakeFrame]:
    yield _frame()


class AppendFailLog:
    durable_length = 0

    def append(self, metadata: RawFrameMetadata, payload: bytes) -> RawRef:
        raise OSError("append failed")

    def sync(self) -> None:
        raise AssertionError("sync must not run after failed append")

    def close(self) -> None:
        return None


class SyncFailLog:
    durable_length = 0

    def append(self, metadata: RawFrameMetadata, payload: bytes) -> RawRef:
        return RawRef(
            segment_id="fake",
            offset=0,
            frame_length=1,
            payload_length=len(payload),
            payload_sha256="0" * 64,
            frame_checksum="1" * 64,
        )

    def sync(self) -> None:
        raise OSError("sync failed")

    def close(self) -> None:
        return None


def test_append_failure_is_fatal_and_explicit(tmp_path: Path) -> None:
    async def scenario() -> None:
        supervisor = RecorderSupervisor(
            source=_one_frame_source(),
            storage_root=tmp_path,
            manifest_path=tmp_path / "manifest.json",
            run_id="append-fail",
            settings=_settings(),
            clock=FixedClock(),
            raw_log_factory=lambda path, segment_id: AppendFailLog(),
        )

        status = await supervisor.run()

        assert status.state is RecorderState.FAILED
        assert status.failure is not None
        assert status.failure.code is RecorderFailureCode.APPEND_FAILED
        assert status.counters.received_frames == 1
        assert status.counters.appended_frames == 0
        assert status.counters.durable_frames == 0

    asyncio.run(scenario())


def test_sync_failure_never_advances_durable_accounting(tmp_path: Path) -> None:
    async def scenario() -> None:
        supervisor = RecorderSupervisor(
            source=_one_frame_source(),
            storage_root=tmp_path,
            manifest_path=tmp_path / "manifest.json",
            run_id="sync-fail",
            settings=_settings(),
            clock=FixedClock(),
            raw_log_factory=lambda path, segment_id: SyncFailLog(),
        )

        status = await supervisor.run()

        assert status.state is RecorderState.FAILED
        assert status.failure is not None
        assert status.failure.code is RecorderFailureCode.SYNC_FAILED
        assert status.counters.appended_frames == 1
        assert status.counters.durable_frames == 0
        assert status.counters.durable_bytes == 0

    asyncio.run(scenario())


def test_seal_failure_preserves_open_segment_and_reports_failure(tmp_path: Path) -> None:
    async def scenario() -> None:
        def fail_seal(**kwargs: object) -> SegmentManifestRecord:
            raise OSError("seal failed")

        supervisor = RecorderSupervisor(
            source=_one_frame_source(),
            storage_root=tmp_path,
            manifest_path=tmp_path / "manifest.json",
            run_id="seal-fail",
            settings=_settings(),
            clock=FixedClock(),
            sealer=fail_seal,
        )

        status = await supervisor.run()

        assert status.state is RecorderState.FAILED
        assert status.failure is not None
        assert status.failure.code is RecorderFailureCode.SEAL_FAILED
        assert status.open_path is not None
        assert Path(status.open_path).exists()
        assert status.final_path is not None
        assert not Path(status.final_path).exists()
        assert status.counters.durable_frames == 1

    asyncio.run(scenario())


def test_writer_cancellation_is_classified(tmp_path: Path) -> None:
    async def scenario() -> None:
        async def cancel_writer(frame: object) -> None:
            raise asyncio.CancelledError

        supervisor = RecorderSupervisor(
            source=_one_frame_source(),
            storage_root=tmp_path,
            manifest_path=tmp_path / "manifest.json",
            run_id="writer-cancel",
            settings=_settings(),
            clock=FixedClock(),
            before_persist=cancel_writer,
        )

        status = await supervisor.run()

        assert status.state is RecorderState.FAILED
        assert status.failure is not None
        assert status.failure.code is RecorderFailureCode.WRITER_CANCELLED

    asyncio.run(scenario())


def test_drain_timeout_is_explicit_and_does_not_claim_durability(tmp_path: Path) -> None:
    async def scenario() -> None:
        never = asyncio.Event()

        async def blocked_writer(frame: object) -> None:
            await never.wait()

        supervisor = RecorderSupervisor(
            source=_one_frame_source(),
            storage_root=tmp_path,
            manifest_path=tmp_path / "manifest.json",
            run_id="drain-timeout",
            settings=_settings(drain=0.01),
            clock=FixedClock(),
            before_persist=blocked_writer,
        )

        status = await supervisor.run()

        assert status.state is RecorderState.FAILED
        assert status.shutdown_outcome is ShutdownOutcome.TIMED_OUT
        assert status.failure is not None
        assert status.failure.code is RecorderFailureCode.DRAIN_TIMEOUT
        assert status.counters.durable_frames == 0

    asyncio.run(scenario())


def test_producer_failure_can_still_leave_persisted_prefix_truthful(tmp_path: Path) -> None:
    async def scenario() -> None:
        async def source() -> AsyncIterator[FakeFrame]:
            yield _frame()
            raise RuntimeError("source exploded")

        supervisor = RecorderSupervisor(
            source=source(),
            storage_root=tmp_path,
            manifest_path=tmp_path / "manifest.json",
            run_id="producer-fail",
            settings=_settings(),
            clock=FixedClock(),
        )

        status = await supervisor.run()

        assert status.state is RecorderState.FAILED
        assert status.failure is not None
        assert status.failure.code is RecorderFailureCode.PRODUCER_FAILED
        assert status.counters.appended_frames == 1
        assert status.counters.durable_frames == 1
        assert status.shutdown_outcome is ShutdownOutcome.CLEAN_DURABLE

    asyncio.run(scenario())
