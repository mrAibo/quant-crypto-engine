from __future__ import annotations

import asyncio
import hashlib
import json
import signal
import socket
import time
import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from pathlib import Path, PurePosixPath
from typing import cast

from cryptobot.adapters.hyperliquid.public import (
    CapturedPublicFrame,
    FrameKind,
    HyperliquidPublicAdapter,
    ReconnectPolicy,
    SubscriptionKey,
    TransportSettings,
)
from cryptobot.data.clock import Clock, SystemClock, elapsed_ns
from cryptobot.data.manifest import StorageAuditItem, audit_storage
from cryptobot.data.recorder import (
    RecorderRuntimeSettings,
    RecorderState,
    RecorderStatus,
    RecorderSupervisor,
    RolloverMode,
    ShutdownOutcome,
)


class RuntimeConfigError(ValueError):
    """Raised when the public recorder runtime config is invalid."""


class ParameterBasis(StrEnum):
    MEASURED = "MEASURED"
    SAFETY_DEFAULT = "SAFETY_DEFAULT"
    DOCUMENTED_CONSTRAINT = "DOCUMENTED_CONSTRAINT"
    EXPERIMENTAL = "EXPERIMENTAL"


class RuntimeExitCode(IntEnum):
    SUCCESS = 0
    RECORDER_FAILED = 2
    STORAGE_AUDIT_FAILED = 3
    NO_FRAMES = 4
    SUBSCRIPTIONS_INCOMPLETE = 5


_CONFIG_FIELDS = frozenset({"schema_version", "parameters"})
_LABELED_FIELDS = frozenset({"value", "basis"})
_PARAMETER_FIELDS = frozenset(
    {
        "source_id",
        "endpoint",
        "coins",
        "channels",
        "queue_capacity",
        "sync_every_frames",
        "shutdown_drain_timeout_seconds",
        "seal_on_shutdown",
        "reconnect_base_seconds",
        "reconnect_max_seconds",
        "reconnect_jitter_fraction",
        "heartbeat_idle_seconds",
        "max_message_bytes",
        "receive_queue_high_water",
        "open_timeout_seconds",
        "close_timeout_seconds",
        "storage_root",
        "manifest_path",
        "run_duration_seconds",
    }
)
_REQUIRED_COINS = frozenset({"BTC", "ETH"})
_REQUIRED_CHANNELS = frozenset({"l2Book", "bbo", "trades", "activeAssetCtx"})


@dataclass(frozen=True, slots=True, order=True)
class ParameterBasisRecord:
    name: str
    basis: ParameterBasis


@dataclass(frozen=True, slots=True)
class PublicRecorderConfig:
    schema_version: int
    source_id: str
    endpoint: str
    coins: tuple[str, ...]
    channels: tuple[str, ...]
    queue_capacity: int
    sync_every_frames: int
    shutdown_drain_timeout_seconds: float
    seal_on_shutdown: bool
    reconnect_base_seconds: float
    reconnect_max_seconds: float
    reconnect_jitter_fraction: float
    heartbeat_idle_seconds: float
    max_message_bytes: int
    receive_queue_high_water: int
    open_timeout_seconds: float
    close_timeout_seconds: float
    storage_root: PurePosixPath
    manifest_path: PurePosixPath
    run_duration_seconds: float | None
    parameter_bases: tuple[ParameterBasisRecord, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise RuntimeConfigError("schema_version must be integer 1")
        if not self.source_id.strip():
            raise RuntimeConfigError("source_id must be non-empty")
        if not self.endpoint.startswith(("ws://", "wss://")):
            raise RuntimeConfigError("endpoint must use ws:// or wss://")
        if set(self.coins) != _REQUIRED_COINS or len(self.coins) != 2:
            raise RuntimeConfigError("TASK-009 coins must be exactly BTC and ETH")
        if set(self.channels) != _REQUIRED_CHANNELS or len(self.channels) != 4:
            raise RuntimeConfigError(
                "TASK-009 channels must be exactly l2Book, bbo, trades, activeAssetCtx"
            )
        if len(self.parameter_bases) != len(_PARAMETER_FIELDS):
            raise RuntimeConfigError("every runtime parameter must have a basis label")

        self.recorder_settings()
        self.reconnect_policy()
        self.transport_settings()

        _validate_storage_paths(self.storage_root, self.manifest_path)
        if self.run_duration_seconds is not None:
            _require_positive_number(self.run_duration_seconds, "run_duration_seconds")

    def recorder_settings(self) -> RecorderRuntimeSettings:
        return RecorderRuntimeSettings(
            queue_capacity=self.queue_capacity,
            sync_every_frames=self.sync_every_frames,
            shutdown_drain_timeout_seconds=self.shutdown_drain_timeout_seconds,
            seal_on_shutdown=self.seal_on_shutdown,
            rollover_mode=RolloverMode.DISABLED,
        )

    def reconnect_policy(self) -> ReconnectPolicy:
        return ReconnectPolicy(
            base_delay_seconds=self.reconnect_base_seconds,
            max_delay_seconds=self.reconnect_max_seconds,
            jitter_fraction=self.reconnect_jitter_fraction,
        )

    def transport_settings(self) -> TransportSettings:
        return TransportSettings(
            heartbeat_idle_seconds=self.heartbeat_idle_seconds,
            max_message_bytes=self.max_message_bytes,
            receive_queue_high_water=self.receive_queue_high_water,
            open_timeout_seconds=self.open_timeout_seconds,
            close_timeout_seconds=self.close_timeout_seconds,
        )

    def basis_dict(self) -> dict[str, str]:
        return {record.name: record.basis.value for record in self.parameter_bases}


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    host_id: str
    boot_id: str
    run_id: str


@dataclass(slots=True)
class SignalState:
    count: int = 0

    def handle(self, supervisor: RecorderSupervisor) -> None:
        self.count += 1
        supervisor.request_stop()


@dataclass(slots=True)
class _Observation:
    total_frames: int = 0
    channel_counts: dict[str, int] = field(default_factory=dict)
    kind_counts: dict[str, int] = field(default_factory=dict)
    connection_ids: set[str] = field(default_factory=set)
    subscription_acks: set[SubscriptionKey] = field(default_factory=set)

    def observe(self, frame: CapturedPublicFrame) -> None:
        self.total_frames += 1
        channel = frame.channel
        if isinstance(channel, str):
            self.channel_counts[channel] = self.channel_counts.get(channel, 0) + 1
        kind = frame.kind
        if isinstance(kind, FrameKind):
            self.kind_counts[kind.value] = self.kind_counts.get(kind.value, 0) + 1
        connection_id = frame.metadata.connection_id
        self.connection_ids.add(connection_id)
        ack = frame.acknowledged_subscription
        if isinstance(ack, SubscriptionKey):
            self.subscription_acks.add(ack)


@dataclass(frozen=True, slots=True)
class PublicRecorderSummary:
    status: str
    exit_code: int
    run_id: str
    host_id: str
    boot_id: str
    start_wall_ns: int
    end_wall_ns: int
    duration_seconds: float
    signal_count: int
    recorder: RecorderStatus
    audit_clean: bool
    audit_items: tuple[StorageAuditItem, ...]
    observed_frames: int
    messages_per_second: float
    channel_counts: tuple[tuple[str, int], ...]
    channel_messages_per_second: tuple[tuple[str, float], ...]
    kind_counts: tuple[tuple[str, int], ...]
    connection_ids: tuple[str, ...]
    reconnect_count: int
    subscription_ack_count: int
    expected_subscription_ack_count: int
    all_subscription_acks_observed: bool
    parameter_bases: tuple[ParameterBasisRecord, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "run_id": self.run_id,
            "host_id": self.host_id,
            "boot_id": self.boot_id,
            "start_wall_ns": self.start_wall_ns,
            "end_wall_ns": self.end_wall_ns,
            "duration_seconds": self.duration_seconds,
            "signal_count": self.signal_count,
            "recorder": {
                "state": self.recorder.state.value,
                "shutdown_outcome": self.recorder.shutdown_outcome.value,
                "counters": {
                    "received_frames": self.recorder.counters.received_frames,
                    "enqueued_frames": self.recorder.counters.enqueued_frames,
                    "appended_frames": self.recorder.counters.appended_frames,
                    "durable_frames": self.recorder.counters.durable_frames,
                    "durable_bytes": self.recorder.counters.durable_bytes,
                    "queue_high_watermark": self.recorder.counters.queue_high_watermark,
                },
                "queue_size": self.recorder.queue_size,
                "segment_id": self.recorder.segment_id,
                "open_path": self.recorder.open_path,
                "final_path": self.recorder.final_path,
                "manifest_path": self.recorder.manifest_path,
                "failure": (
                    None
                    if self.recorder.failure is None
                    else {
                        "code": self.recorder.failure.code.value,
                        "detail": self.recorder.failure.detail,
                    }
                ),
            },
            "audit": {
                "clean": self.audit_clean,
                "items": [
                    {
                        "relative_path": item.relative_path,
                        "segment_id": item.segment_id,
                        "state": item.state.value,
                        "detail": item.detail,
                    }
                    for item in self.audit_items
                ],
            },
            "observation": {
                "frames": self.observed_frames,
                "messages_per_second": self.messages_per_second,
                "channel_counts": dict(self.channel_counts),
                "channel_messages_per_second": dict(self.channel_messages_per_second),
                "kind_counts": dict(self.kind_counts),
                "connection_ids": list(self.connection_ids),
                "reconnect_count": self.reconnect_count,
                "subscription_ack_count": self.subscription_ack_count,
                "expected_subscription_ack_count": self.expected_subscription_ack_count,
                "all_subscription_acks_observed": self.all_subscription_acks_observed,
                "malformed_frames": dict(self.kind_counts).get(FrameKind.MALFORMED.value, 0),
                "unknown_frames": dict(self.kind_counts).get(FrameKind.UNKNOWN.value, 0),
            },
            "parameter_bases": {record.name: record.basis.value for record in self.parameter_bases},
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


def load_public_recorder_config(path: str | Path) -> PublicRecorderConfig:
    source = Path(path)
    try:
        decoded = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeConfigError(f"runtime config cannot be decoded: {source}") from exc
    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        raise RuntimeConfigError("runtime config root must be a string-keyed object")
    raw = cast(dict[str, object], decoded)
    _require_exact_fields(raw, _CONFIG_FIELDS, "runtime config")

    schema_version = _mapping_int(raw, "schema_version")
    parameters = raw["parameters"]
    if not isinstance(parameters, dict) or not all(isinstance(key, str) for key in parameters):
        raise RuntimeConfigError("parameters must be a string-keyed object")
    params = cast(dict[str, object], parameters)
    _require_exact_fields(params, _PARAMETER_FIELDS, "parameters")

    values: dict[str, object] = {}
    bases: list[ParameterBasisRecord] = []
    for name in sorted(_PARAMETER_FIELDS):
        value, basis = _labeled_value(params[name], name)
        values[name] = value
        bases.append(ParameterBasisRecord(name=name, basis=basis))

    duration_raw = values["run_duration_seconds"]
    duration = None if duration_raw is None else _number(duration_raw, "run_duration_seconds")

    return PublicRecorderConfig(
        schema_version=schema_version,
        source_id=_string(values["source_id"], "source_id"),
        endpoint=_string(values["endpoint"], "endpoint"),
        coins=_strings(values["coins"], "coins"),
        channels=_strings(values["channels"], "channels"),
        queue_capacity=_int(values["queue_capacity"], "queue_capacity"),
        sync_every_frames=_int(values["sync_every_frames"], "sync_every_frames"),
        shutdown_drain_timeout_seconds=_number(
            values["shutdown_drain_timeout_seconds"],
            "shutdown_drain_timeout_seconds",
        ),
        seal_on_shutdown=_bool(values["seal_on_shutdown"], "seal_on_shutdown"),
        reconnect_base_seconds=_number(values["reconnect_base_seconds"], "reconnect_base_seconds"),
        reconnect_max_seconds=_number(values["reconnect_max_seconds"], "reconnect_max_seconds"),
        reconnect_jitter_fraction=_number(
            values["reconnect_jitter_fraction"],
            "reconnect_jitter_fraction",
        ),
        heartbeat_idle_seconds=_number(values["heartbeat_idle_seconds"], "heartbeat_idle_seconds"),
        max_message_bytes=_int(values["max_message_bytes"], "max_message_bytes"),
        receive_queue_high_water=_int(
            values["receive_queue_high_water"], "receive_queue_high_water"
        ),
        open_timeout_seconds=_number(values["open_timeout_seconds"], "open_timeout_seconds"),
        close_timeout_seconds=_number(values["close_timeout_seconds"], "close_timeout_seconds"),
        storage_root=_path(values["storage_root"], "storage_root"),
        manifest_path=_path(values["manifest_path"], "manifest_path"),
        run_duration_seconds=duration,
        parameter_bases=tuple(bases),
    )


def derive_runtime_identity(
    *,
    machine_id_path: str | Path = "/etc/machine-id",
    boot_id_path: str | Path = "/proc/sys/kernel/random/boot_id",
    hostname: str | None = None,
    fallback_boot_token: str | None = None,
    run_entropy: str | None = None,
    run_wall_ns: int | None = None,
) -> RuntimeIdentity:
    machine_id = _read_optional_text(machine_id_path)
    host_source = machine_id or (hostname if hostname is not None else socket.gethostname())
    if not host_source.strip():
        raise RuntimeConfigError("cannot derive non-empty host identity")
    host_id = "host-" + hashlib.sha256(host_source.encode()).hexdigest()[:16]

    boot_source = _read_optional_text(boot_id_path)
    if boot_source is None:
        token = fallback_boot_token or uuid.uuid4().hex
        if not token.strip():
            raise RuntimeConfigError("fallback boot token must be non-empty")
        boot_source = token
    boot_id = "boot-" + hashlib.sha256(boot_source.encode()).hexdigest()[:16]

    wall_ns = time.time_ns() if run_wall_ns is None else run_wall_ns
    if isinstance(wall_ns, bool) or not isinstance(wall_ns, int) or wall_ns < 0:
        raise RuntimeConfigError("run_wall_ns must be a non-negative integer")
    entropy = run_entropy or uuid.uuid4().hex
    if not entropy.strip():
        raise RuntimeConfigError("run entropy must be non-empty")
    run_digest = hashlib.sha256(f"{host_id}\0{boot_id}\0{wall_ns}\0{entropy}".encode()).hexdigest()[
        :20
    ]
    return RuntimeIdentity(
        host_id=host_id,
        boot_id=boot_id,
        run_id=f"run-{wall_ns}-{run_digest}",
    )


async def run_public_recorder(
    config: PublicRecorderConfig,
    *,
    identity: RuntimeIdentity | None = None,
    clock: Clock | None = None,
    install_signal_handlers: bool = True,
) -> PublicRecorderSummary:
    runtime_identity = identity or derive_runtime_identity()
    runtime_clock = clock or SystemClock(
        host_id=runtime_identity.host_id,
        boot_id=runtime_identity.boot_id,
    )

    observation = _Observation()
    adapter = HyperliquidPublicAdapter(
        source_id=config.source_id,
        coins=config.coins,
        channels=config.channels,
        clock=runtime_clock,
        transport=config.transport_settings(),
        endpoint=config.endpoint,
    )
    source = _observe_frames(adapter.frames(config.reconnect_policy()), observation)
    supervisor = RecorderSupervisor(
        source=source,
        storage_root=Path(config.storage_root),
        manifest_path=Path(config.manifest_path),
        run_id=runtime_identity.run_id,
        settings=config.recorder_settings(),
        clock=runtime_clock,
        recorder_version="task-009",
        event_schema_version=1,
    )

    signal_state = SignalState()
    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []
    if install_signal_handlers:
        for handled_signal in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(
                    handled_signal,
                    signal_state.handle,
                    supervisor,
                )
            except (NotImplementedError, RuntimeError):
                continue
            installed_signals.append(handled_signal)

    start = runtime_clock.sample()
    run_task = asyncio.create_task(supervisor.run(), name="public-recorder-supervisor")
    timer: asyncio.Task[None] | None = None
    try:
        if config.run_duration_seconds is not None:
            timer = asyncio.create_task(
                asyncio.sleep(config.run_duration_seconds),
                name="public-recorder-duration",
            )
            done, _ = await asyncio.wait(
                {run_task, timer},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if timer in done and not run_task.done():
                supervisor.request_stop()
        recorder_status = await run_task
    finally:
        if timer is not None and not timer.done():
            timer.cancel()
            await _await_cancelled(timer)
        for handled_signal in installed_signals:
            loop.remove_signal_handler(handled_signal)

    end = runtime_clock.sample()
    audit = audit_storage(Path(config.storage_root), Path(config.manifest_path))
    duration_seconds = elapsed_ns(start, end) / 1_000_000_000
    expected_acks = {
        SubscriptionKey(channel=channel, coin=coin)
        for coin in config.coins
        for channel in config.channels
    }
    all_acks = expected_acks.issubset(observation.subscription_acks)

    exit_code = _runtime_exit_code(
        recorder=recorder_status,
        audit_clean=audit.clean,
        observed_frames=observation.total_frames,
        all_subscription_acks_observed=all_acks,
    )
    safe_duration = duration_seconds if duration_seconds > 0 else 1e-9
    channel_counts = tuple(sorted(observation.channel_counts.items()))
    return PublicRecorderSummary(
        status="SUCCESS" if exit_code is RuntimeExitCode.SUCCESS else "FAILED",
        exit_code=int(exit_code),
        run_id=runtime_identity.run_id,
        host_id=runtime_identity.host_id,
        boot_id=runtime_identity.boot_id,
        start_wall_ns=start.wall_ns,
        end_wall_ns=end.wall_ns,
        duration_seconds=duration_seconds,
        signal_count=signal_state.count,
        recorder=recorder_status,
        audit_clean=audit.clean,
        audit_items=audit.items,
        observed_frames=observation.total_frames,
        messages_per_second=observation.total_frames / safe_duration,
        channel_counts=channel_counts,
        channel_messages_per_second=tuple(
            (channel, count / safe_duration) for channel, count in channel_counts
        ),
        kind_counts=tuple(sorted(observation.kind_counts.items())),
        connection_ids=tuple(sorted(observation.connection_ids)),
        reconnect_count=max(0, len(observation.connection_ids) - 1),
        subscription_ack_count=len(observation.subscription_acks),
        expected_subscription_ack_count=len(expected_acks),
        all_subscription_acks_observed=all_acks,
        parameter_bases=config.parameter_bases,
    )


def audit_public_recorder(config: PublicRecorderConfig) -> dict[str, object]:
    report = audit_storage(Path(config.storage_root), Path(config.manifest_path))
    return {
        "clean": report.clean,
        "items": [
            {
                "relative_path": item.relative_path,
                "segment_id": item.segment_id,
                "state": item.state.value,
                "detail": item.detail,
            }
            for item in report.items
        ],
    }


async def _observe_frames(
    source: AsyncIterator[CapturedPublicFrame],
    observation: _Observation,
) -> AsyncIterator[CapturedPublicFrame]:
    async for frame in source:
        observation.observe(frame)
        yield frame


def _runtime_exit_code(
    *,
    recorder: RecorderStatus,
    audit_clean: bool,
    observed_frames: int,
    all_subscription_acks_observed: bool,
) -> RuntimeExitCode:
    if recorder.state is RecorderState.FAILED or recorder.shutdown_outcome in {
        ShutdownOutcome.TIMED_OUT,
        ShutdownOutcome.FAILED,
    }:
        return RuntimeExitCode.RECORDER_FAILED
    if not audit_clean:
        return RuntimeExitCode.STORAGE_AUDIT_FAILED
    if observed_frames == 0:
        return RuntimeExitCode.NO_FRAMES
    if not all_subscription_acks_observed:
        return RuntimeExitCode.SUBSCRIPTIONS_INCOMPLETE
    return RuntimeExitCode.SUCCESS


def _labeled_value(raw: object, name: str) -> tuple[object, ParameterBasis]:
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise RuntimeConfigError(f"{name} must be a labeled object")
    item = cast(dict[str, object], raw)
    _require_exact_fields(item, _LABELED_FIELDS, name)
    basis_raw = item["basis"]
    if not isinstance(basis_raw, str):
        raise RuntimeConfigError(f"{name}.basis must be a string")
    try:
        basis = ParameterBasis(basis_raw)
    except ValueError as exc:
        allowed = ", ".join(value.value for value in ParameterBasis)
        raise RuntimeConfigError(f"{name}.basis must be one of: {allowed}") from exc
    return item["value"], basis


def _require_exact_fields(
    raw: Mapping[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    unknown = set(raw) - expected
    missing = expected - set(raw)
    if unknown:
        raise RuntimeConfigError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        raise RuntimeConfigError(f"{label} is missing fields: {', '.join(sorted(missing))}")


def _mapping_int(raw: Mapping[str, object], field: str) -> int:
    return _int(raw[field], field)


def _int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeConfigError(f"{field} must be an integer")
    return value


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RuntimeConfigError(f"{field} must be a number")
    return float(value)


def _require_positive_number(value: float, field: str) -> None:
    if value <= 0:
        raise RuntimeConfigError(f"{field} must be positive")


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise RuntimeConfigError(f"{field} must be boolean")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value.strip() != value:
        raise RuntimeConfigError(f"{field} must be a non-empty trimmed string")
    return value


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise RuntimeConfigError(f"{field} must be a non-empty array")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_string(item, f"{field}[{index}]"))
    if len(result) != len(set(result)):
        raise RuntimeConfigError(f"{field} must not contain duplicates")
    return tuple(result)


def _path(value: object, field: str) -> PurePosixPath:
    raw = _string(value, field)
    if "\\" in raw:
        raise RuntimeConfigError(f"{field} must use POSIX path separators")
    path = PurePosixPath(raw)
    if ".." in path.parts or str(path) == ".":
        raise RuntimeConfigError(f"{field} must not traverse parent directories")
    return path


def _validate_storage_paths(root: PurePosixPath, manifest: PurePosixPath) -> None:
    if root.is_absolute() != manifest.is_absolute():
        raise RuntimeConfigError(
            "storage_root and manifest_path must both be absolute or both be relative"
        )
    try:
        manifest.relative_to(root)
    except ValueError as exc:
        raise RuntimeConfigError("manifest_path must be inside storage_root") from exc


def _read_optional_text(path: str | Path) -> str | None:
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


async def _await_cancelled(task: asyncio.Task[None]) -> None:
    try:
        await task
    except asyncio.CancelledError:
        return
