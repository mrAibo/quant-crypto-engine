from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, TypeVar, cast

from cryptobot.data.clock import Clock
from cryptobot.data.manifest import SegmentManifestRecord, seal_segment
from cryptobot.data.rawlog import RawFrameMetadata, RawLog, RawRef


_SEGMENT_SAFE = re.compile(r"[^a-z0-9._-]+")
_END = object()


class RecorderError(ValueError):
    """Raised for invalid recorder configuration or lifecycle use."""


class RecorderState(StrEnum):
    INIT = "INIT"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ShutdownOutcome(StrEnum):
    NONE = "NONE"
    CLEAN_DURABLE = "CLEAN_DURABLE"
    CLEAN_UNSEALED = "CLEAN_UNSEALED"
    TIMED_OUT = "TIMED_OUT"
    FAILED = "FAILED"


class RecorderFailureCode(StrEnum):
    PRODUCER_FAILED = "PRODUCER_FAILED"
    WRITER_FAILED = "WRITER_FAILED"
    WRITER_CANCELLED = "WRITER_CANCELLED"
    DRAIN_TIMEOUT = "DRAIN_TIMEOUT"
    APPEND_FAILED = "APPEND_FAILED"
    SYNC_FAILED = "SYNC_FAILED"
    SEAL_FAILED = "SEAL_FAILED"


class RolloverMode(StrEnum):
    DISABLED = "DISABLED"


class CaptureFrame(Protocol):
    @property
    def metadata(self) -> RawFrameMetadata:
        """Capture metadata assigned before queueing."""
        ...

    @property
    def payload(self) -> bytes:
        """Exact received application payload bytes."""
        ...


class RawLogPort(Protocol):
    @property
    def durable_length(self) -> int:
        """Bytes known durable after the last sync."""
        ...

    def append(self, metadata: RawFrameMetadata, payload: bytes) -> RawRef:
        """Append one framed capture."""
        ...

    def sync(self) -> None:
        """Flush and fsync written bytes."""
        ...

    def close(self) -> None:
        """Close the segment."""
        ...


class SegmentSealer(Protocol):
    def __call__(
        self,
        *,
        open_path: str | Path,
        final_path: str | Path,
        storage_root: str | Path,
        manifest_path: str | Path,
        segment_id: str,
        sealed_wall_ns: int,
        recorder_version: str | None = None,
        event_schema_version: int | None = None,
    ) -> SegmentManifestRecord:
        """Seal and publish a clean segment."""
        ...


RawLogFactory = Callable[[Path, str], RawLogPort]
AsyncPersistHook = Callable[[CaptureFrame], Awaitable[None]]
_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class RecorderRuntimeSettings:
    queue_capacity: int
    sync_every_frames: int
    shutdown_drain_timeout_seconds: float
    seal_on_shutdown: bool
    rollover_mode: RolloverMode = RolloverMode.DISABLED

    def __post_init__(self) -> None:
        _require_positive_int(self.queue_capacity, "queue_capacity")
        _require_positive_int(self.sync_every_frames, "sync_every_frames")
        if (
            isinstance(self.shutdown_drain_timeout_seconds, bool)
            or not isinstance(self.shutdown_drain_timeout_seconds, int | float)
            or self.shutdown_drain_timeout_seconds <= 0
        ):
            raise RecorderError("shutdown_drain_timeout_seconds must be a positive number")
        if not isinstance(self.seal_on_shutdown, bool):
            raise RecorderError("seal_on_shutdown must be boolean")
        if self.rollover_mode is not RolloverMode.DISABLED:
            raise RecorderError("TASK-008 supports only DISABLED automatic rollover")


@dataclass(frozen=True, slots=True)
class RecorderCounters:
    received_frames: int
    enqueued_frames: int
    appended_frames: int
    durable_frames: int
    durable_bytes: int
    queue_high_watermark: int


@dataclass(frozen=True, slots=True)
class RecorderFailure:
    code: RecorderFailureCode
    detail: str


@dataclass(frozen=True, slots=True)
class RecorderStatus:
    state: RecorderState
    shutdown_outcome: ShutdownOutcome
    counters: RecorderCounters
    queue_size: int
    segment_id: str | None
    open_path: str | None
    final_path: str | None
    manifest_path: str
    sealed_record: SegmentManifestRecord | None
    failure: RecorderFailure | None


@dataclass(slots=True)
class _MutableCounters:
    received_frames: int = 0
    enqueued_frames: int = 0
    appended_frames: int = 0
    durable_frames: int = 0
    durable_bytes: int = 0
    queue_high_watermark: int = 0

    def snapshot(self) -> RecorderCounters:
        return RecorderCounters(
            received_frames=self.received_frames,
            enqueued_frames=self.enqueued_frames,
            appended_frames=self.appended_frames,
            durable_frames=self.durable_frames,
            durable_bytes=self.durable_bytes,
            queue_high_watermark=self.queue_high_watermark,
        )


class RecorderSupervisor:
    """Bounded raw-capture pipeline with truthful durability accounting."""

    def __init__(
        self,
        *,
        source: AsyncIterator[CaptureFrame],
        storage_root: str | Path,
        manifest_path: str | Path,
        run_id: str,
        settings: RecorderRuntimeSettings,
        clock: Clock,
        raw_log_factory: RawLogFactory | None = None,
        sealer: SegmentSealer | None = None,
        before_persist: AsyncPersistHook | None = None,
        recorder_version: str | None = None,
        event_schema_version: int | None = None,
    ) -> None:
        self._storage_root = Path(storage_root)
        self._manifest_path = Path(manifest_path)
        _require_run_id(run_id)
        self._run_id = run_id
        self._settings = settings
        self._clock = clock
        self._source = source
        self._queue: asyncio.Queue[CaptureFrame | object] = asyncio.Queue(
            maxsize=settings.queue_capacity
        )
        self._raw_log_factory = raw_log_factory or _open_raw_log
        self._sealer = sealer or seal_segment
        self._before_persist = before_persist
        self._recorder_version = recorder_version
        self._event_schema_version = event_schema_version

        self._stop_requested = asyncio.Event()
        self._state = RecorderState.INIT
        self._shutdown_outcome = ShutdownOutcome.NONE
        self._counters = _MutableCounters()
        self._failure: RecorderFailure | None = None
        self._segment_id: str | None = None
        self._open_path: Path | None = None
        self._final_path: Path | None = None
        self._sealed_record: SegmentManifestRecord | None = None
        self._has_run = False

    def request_stop(self) -> None:
        """Request a graceful producer stop and queue drain."""
        self._stop_requested.set()
        if self._state is RecorderState.RUNNING:
            self._state = RecorderState.STOPPING

    def snapshot(self) -> RecorderStatus:
        return RecorderStatus(
            state=self._state,
            shutdown_outcome=self._shutdown_outcome,
            counters=self._counters.snapshot(),
            queue_size=self._queue.qsize(),
            segment_id=self._segment_id,
            open_path=str(self._open_path) if self._open_path is not None else None,
            final_path=str(self._final_path) if self._final_path is not None else None,
            manifest_path=str(self._manifest_path),
            sealed_record=self._sealed_record,
            failure=self._failure,
        )

    async def run(self) -> RecorderStatus:
        if self._has_run:
            raise RecorderError("RecorderSupervisor.run() may be called only once")
        self._has_run = True
        self._state = RecorderState.RUNNING

        producer = asyncio.create_task(self._produce(), name="recorder-producer")
        writer = asyncio.create_task(self._write(), name="recorder-writer")

        done, _ = await asyncio.wait(
            {producer, writer},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if writer in done:
            if writer.cancelled():
                self._set_failure(
                    RecorderFailureCode.WRITER_CANCELLED,
                    "writer task was cancelled",
                )
            else:
                writer_exc = writer.exception()
                if writer_exc is not None:
                    self._set_failure(
                        RecorderFailureCode.WRITER_FAILED,
                        _exception_detail(writer_exc),
                    )
            if not producer.done():
                producer.cancel()
                await _await_cancelled(producer)
        else:
            try:
                await asyncio.wait_for(
                    asyncio.shield(writer),
                    timeout=float(self._settings.shutdown_drain_timeout_seconds),
                )
            except TimeoutError:
                self._set_failure(
                    RecorderFailureCode.DRAIN_TIMEOUT,
                    "writer did not drain the bounded queue before shutdown timeout",
                )
                self._shutdown_outcome = ShutdownOutcome.TIMED_OUT
                writer.cancel()
                await _await_cancelled(writer)
            except asyncio.CancelledError:
                if writer.cancelled():
                    self._set_failure(
                        RecorderFailureCode.WRITER_CANCELLED,
                        "writer task was cancelled during drain",
                    )
                else:
                    raise
            except Exception as exc:
                self._set_failure(
                    RecorderFailureCode.WRITER_FAILED,
                    _exception_detail(exc),
                )

        if not producer.done():
            producer.cancel()
            await _await_cancelled(producer)
        elif producer.cancelled():
            self._set_failure(
                RecorderFailureCode.PRODUCER_FAILED,
                "producer task was cancelled",
            )
        else:
            producer_exc = producer.exception()
            if producer_exc is not None:
                self._set_failure(
                    RecorderFailureCode.PRODUCER_FAILED,
                    _exception_detail(producer_exc),
                )

        if self._failure is not None:
            self._state = RecorderState.FAILED
            if self._shutdown_outcome is ShutdownOutcome.NONE:
                self._shutdown_outcome = ShutdownOutcome.FAILED
        else:
            self._state = RecorderState.COMPLETE

        return self.snapshot()

    async def _produce(self) -> None:
        iterator = self._source.__aiter__()
        cancelled = False
        try:
            while not self._stop_requested.is_set():
                next_frame = asyncio.create_task(_next_frame(iterator))
                stop_wait = asyncio.create_task(self._stop_requested.wait())
                done, _ = await asyncio.wait(
                    {next_frame, stop_wait},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if stop_wait in done:
                    if next_frame.done() and not next_frame.cancelled():
                        try:
                            frame = next_frame.result()
                        except StopAsyncIteration:
                            frame = None
                        if frame is not None:
                            await self._enqueue(frame)
                    else:
                        next_frame.cancel()
                        await _await_cancelled(next_frame)
                    break

                stop_wait.cancel()
                await _await_cancelled(stop_wait)
                try:
                    frame = next_frame.result()
                except StopAsyncIteration:
                    break
                await self._enqueue(frame)
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception as exc:
            self._set_failure(
                RecorderFailureCode.PRODUCER_FAILED,
                _exception_detail(exc),
            )
        finally:
            if cancelled:
                try:
                    self._queue.put_nowait(_END)
                except asyncio.QueueFull:
                    pass
            else:
                await self._queue.put(_END)

    async def _enqueue(self, frame: CaptureFrame) -> None:
        self._counters.received_frames += 1
        await self._queue.put(frame)
        self._counters.enqueued_frames += 1
        self._counters.queue_high_watermark = max(
            self._counters.queue_high_watermark,
            self._queue.qsize(),
        )

    async def _write(self) -> None:
        raw_log: RawLogPort | None = None
        try:
            while True:
                item = await self._queue.get()
                try:
                    if item is _END:
                        break
                    frame = _require_capture_frame(item)
                    if raw_log is None:
                        raw_log = self._open_segment(frame.metadata)
                    if self._before_persist is not None:
                        await self._before_persist(frame)
                    try:
                        raw_log.append(frame.metadata, frame.payload)
                    except Exception as exc:
                        self._set_failure(
                            RecorderFailureCode.APPEND_FAILED,
                            _exception_detail(exc),
                        )
                        raise
                    self._counters.appended_frames += 1

                    if (
                        self._counters.appended_frames
                        - self._counters.durable_frames
                        >= self._settings.sync_every_frames
                    ):
                        self._sync(raw_log)
                finally:
                    self._queue.task_done()

            if raw_log is None:
                self._shutdown_outcome = ShutdownOutcome.CLEAN_UNSEALED
                return

            if self._counters.appended_frames > self._counters.durable_frames:
                self._sync(raw_log)
            raw_log.close()
            raw_log = None

            if self._settings.seal_on_shutdown:
                self._seal_current_segment()
                self._shutdown_outcome = ShutdownOutcome.CLEAN_DURABLE
            else:
                self._shutdown_outcome = ShutdownOutcome.CLEAN_UNSEALED
        except asyncio.CancelledError:
            raise
        finally:
            if raw_log is not None:
                raw_log.close()

    def _open_segment(self, metadata: RawFrameMetadata) -> RawLogPort:
        segment_id = make_segment_id(
            source_id=metadata.source_id,
            start_wall_ns=metadata.recv_wall_ns,
            connection_id=metadata.connection_id,
            run_id=self._run_id,
        )
        raw_dir = self._storage_root / "raw"
        open_path = raw_dir / f"segment-{segment_id}.raw.open"
        final_path = raw_dir / f"segment-{segment_id}.raw"

        if open_path.exists() or final_path.exists():
            raise RecorderError(f"recorder segment path already exists for {segment_id}")

        self._segment_id = segment_id
        self._open_path = open_path
        self._final_path = final_path
        return self._raw_log_factory(open_path, segment_id)

    def _sync(self, raw_log: RawLogPort) -> None:
        try:
            raw_log.sync()
        except Exception as exc:
            self._set_failure(
                RecorderFailureCode.SYNC_FAILED,
                _exception_detail(exc),
            )
            raise
        self._counters.durable_frames = self._counters.appended_frames
        self._counters.durable_bytes = raw_log.durable_length

    def _seal_current_segment(self) -> None:
        if self._segment_id is None or self._open_path is None or self._final_path is None:
            raise RecorderError("cannot seal before a segment has been opened")
        try:
            self._sealed_record = self._sealer(
                open_path=self._open_path,
                final_path=self._final_path,
                storage_root=self._storage_root,
                manifest_path=self._manifest_path,
                segment_id=self._segment_id,
                sealed_wall_ns=self._clock.sample().wall_ns,
                recorder_version=self._recorder_version,
                event_schema_version=self._event_schema_version,
            )
        except Exception as exc:
            self._set_failure(
                RecorderFailureCode.SEAL_FAILED,
                _exception_detail(exc),
            )
            raise

    def _set_failure(self, code: RecorderFailureCode, detail: str) -> None:
        if self._failure is None:
            self._failure = RecorderFailure(code=code, detail=detail)


def make_segment_id(
    *,
    source_id: str,
    start_wall_ns: int,
    connection_id: str,
    run_id: str,
) -> str:
    if not source_id.strip():
        raise RecorderError("source_id must be non-empty")
    if isinstance(start_wall_ns, bool) or not isinstance(start_wall_ns, int) or start_wall_ns < 0:
        raise RecorderError("start_wall_ns must be a non-negative integer")
    if not connection_id.strip():
        raise RecorderError("connection_id must be non-empty")
    _require_run_id(run_id)

    source_slug = _SEGMENT_SAFE.sub("-", source_id.lower()).strip("-._")[:40]
    if not source_slug:
        source_slug = "source"
    digest_input = "\0".join(
        (source_id, str(start_wall_ns), connection_id, run_id)
    ).encode("utf-8")
    digest = hashlib.sha256(digest_input).hexdigest()[:16]
    return f"{source_slug}-{start_wall_ns}-{digest}"


async def _next_frame(iterator: AsyncIterator[CaptureFrame]) -> CaptureFrame:
    return await anext(iterator)


async def _await_cancelled(task: asyncio.Task[_T]) -> None:
    try:
        await task
    except (asyncio.CancelledError, StopAsyncIteration):
        return


def _open_raw_log(path: Path, segment_id: str) -> RawLogPort:
    return RawLog.open(path, segment_id)


def _require_capture_frame(value: CaptureFrame | object) -> CaptureFrame:
    if not hasattr(value, "metadata") or not hasattr(value, "payload"):
        raise RecorderError("queue contained an invalid capture frame")
    return cast(CaptureFrame, value)


def _require_positive_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RecorderError(f"{field} must be a positive integer")


def _require_run_id(value: str) -> None:
    if not value.strip() or value.strip() != value:
        raise RecorderError("run_id must be a non-empty trimmed string")
    if len(value) > 128:
        raise RecorderError("run_id must be at most 128 characters")


def _exception_detail(exc: BaseException) -> str:
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__
