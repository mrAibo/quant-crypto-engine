from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from cryptobot.data.clock import ClockSample
from cryptobot.data.manifest import AuditState, audit_storage
from cryptobot.data.rawlog import RawFrameMetadata, iter_raw_frames
from cryptobot.data.recorder import (
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


class IncrementingClock:
    def __init__(self) -> None:
        self._wall = 50_000
        self._mono = 80_000

    def sample(self) -> ClockSample:
        self._wall += 1
        self._mono += 1
        return ClockSample(
            wall_ns=self._wall,
            mono_ns=self._mono,
            host_id="host",
            boot_id="boot",
        )


def _frame(seq: int, payload: bytes) -> FakeFrame:
    return FakeFrame(
        metadata=RawFrameMetadata(
            schema_version=1,
            source_id="hyperliquid-mainnet-public",
            recv_wall_ns=1_000 + seq,
            recv_mono_ns=2_000 + seq,
            host_id="host",
            boot_id="boot",
            connection_id="conn-1",
            ingest_seq=seq,
            channel_hint="trades",
            capture_flags=("LIVE_CAPTURE", "WS_PUBLIC"),
        ),
        payload=payload,
    )


def _settings(queue_capacity: int = 4) -> RecorderRuntimeSettings:
    return RecorderRuntimeSettings(
        queue_capacity=queue_capacity,
        sync_every_frames=2,
        shutdown_drain_timeout_seconds=2,
        seal_on_shutdown=True,
        rollover_mode=RolloverMode.DISABLED,
    )


def test_end_to_end_frames_roundtrip_and_publish_valid_manifest(tmp_path: Path) -> None:
    async def scenario() -> None:
        expected = [
            _frame(1, b'{"channel":"trades","n":1}'),
            _frame(2, b'{"channel":"bbo","n":2}'),
            _frame(3, b"\xff\x00opaque"),
        ]

        async def source() -> AsyncIterator[FakeFrame]:
            for frame in expected:
                yield frame

        manifest = tmp_path / "manifests" / "raw-manifest.json"
        supervisor = RecorderSupervisor(
            source=source(),
            storage_root=tmp_path,
            manifest_path=manifest,
            run_id="integration-run",
            settings=_settings(),
            clock=IncrementingClock(),
            recorder_version="task-008-test",
            event_schema_version=1,
        )

        status = await supervisor.run()

        assert status.state is RecorderState.COMPLETE
        assert status.shutdown_outcome is ShutdownOutcome.CLEAN_DURABLE
        assert status.failure is None
        assert status.segment_id is not None
        assert status.open_path is not None
        assert status.final_path is not None
        assert not Path(status.open_path).exists()
        assert Path(status.final_path).exists()

        assert status.counters.received_frames == 3
        assert status.counters.enqueued_frames == 3
        assert status.counters.appended_frames == 3
        assert status.counters.durable_frames == 3
        assert status.counters.durable_bytes > 0
        assert status.counters.queue_high_watermark <= _settings().queue_capacity

        replayed = list(iter_raw_frames(status.final_path, status.segment_id))
        assert [frame.payload for frame in replayed] == [frame.payload for frame in expected]
        assert [frame.metadata for frame in replayed] == [frame.metadata for frame in expected]

        audit = audit_storage(tmp_path, manifest)
        assert audit.clean
        assert len(audit.items) == 1
        assert audit.items[0].state is AuditState.VALID

    asyncio.run(scenario())


def test_bounded_queue_applies_backpressure_without_dropping(tmp_path: Path) -> None:
    async def scenario() -> None:
        expected = [_frame(index, f"payload-{index}".encode()) for index in range(1, 7)]
        writer_gate = asyncio.Event()
        persist_calls = 0

        async def source() -> AsyncIterator[FakeFrame]:
            for frame in expected:
                yield frame

        async def before_persist(frame: object) -> None:
            nonlocal persist_calls
            persist_calls += 1
            if persist_calls == 1:
                await writer_gate.wait()

        supervisor = RecorderSupervisor(
            source=source(),
            storage_root=tmp_path,
            manifest_path=tmp_path / "manifest.json",
            run_id="backpressure-run",
            settings=_settings(queue_capacity=2),
            clock=IncrementingClock(),
            before_persist=before_persist,
        )
        run_task = asyncio.create_task(supervisor.run())

        for _ in range(200):
            status = supervisor.snapshot()
            if status.counters.received_frames >= 4 and status.queue_size == 2:
                break
            await asyncio.sleep(0)
        else:
            raise AssertionError("producer never reached bounded backpressure state")

        blocked = supervisor.snapshot()
        assert blocked.queue_size == 2
        assert blocked.counters.queue_high_watermark == 2
        assert blocked.counters.received_frames > blocked.counters.enqueued_frames

        writer_gate.set()
        final = await run_task

        assert final.state is RecorderState.COMPLETE
        assert final.counters.received_frames == len(expected)
        assert final.counters.enqueued_frames == len(expected)
        assert final.counters.appended_frames == len(expected)
        assert final.counters.durable_frames == len(expected)
        assert final.segment_id is not None
        assert final.final_path is not None

        replayed = list(iter_raw_frames(final.final_path, final.segment_id))
        assert [frame.payload for frame in replayed] == [frame.payload for frame in expected]

    asyncio.run(scenario())


def test_request_stop_drains_already_enqueued_frames(tmp_path: Path) -> None:
    async def scenario() -> None:
        release_source = asyncio.Event()

        async def source() -> AsyncIterator[FakeFrame]:
            yield _frame(1, b"one")
            await release_source.wait()
            yield _frame(2, b"two")

        supervisor = RecorderSupervisor(
            source=source(),
            storage_root=tmp_path,
            manifest_path=tmp_path / "manifest.json",
            run_id="stop-run",
            settings=_settings(),
            clock=IncrementingClock(),
        )
        run_task = asyncio.create_task(supervisor.run())

        for _ in range(100):
            if supervisor.snapshot().counters.enqueued_frames >= 1:
                break
            await asyncio.sleep(0)
        supervisor.request_stop()
        final = await run_task

        assert final.state is RecorderState.COMPLETE
        assert final.counters.appended_frames == 1
        assert final.counters.durable_frames == 1
        assert final.shutdown_outcome is ShutdownOutcome.CLEAN_DURABLE

    asyncio.run(scenario())
