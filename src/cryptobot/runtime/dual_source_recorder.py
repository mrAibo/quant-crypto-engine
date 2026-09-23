from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import cast

from cryptobot.adapters.binance.public import SOURCE_ID as _BINANCE_SOURCE_ID
from cryptobot.adapters.binance.public import (
    BinanceFrameKind,
    BinanceReconnectPolicy,
    BinanceReferenceAdapter,
    BinanceTransportSettings,
    classify_binance_payload,
)
from cryptobot.adapters.hyperliquid.public import (
    HyperliquidPublicAdapter,
    ReconnectPolicy,
    SubscriptionKey,
    TransportSettings,
    classify_public_payload,
)
from cryptobot.data.clock import Clock, SystemClock, elapsed_ns
from cryptobot.data.manifest import StorageAuditItem, audit_storage
from cryptobot.data.recorder import (
    CaptureFrame,
    RecorderRuntimeSettings,
    RecorderState,
    RecorderStatus,
    RecorderSupervisor,
    RolloverMode,
    ShutdownOutcome,
)
from cryptobot.runtime.public_recorder import RuntimeIdentity, derive_runtime_identity

BINANCE_SOURCE_ID = _BINANCE_SOURCE_ID
HYPERLIQUID_SOURCE_ID = "hyperliquid-mainnet-public"
_REQUIRED_HL_COINS = ("BTC", "ETH")
_REQUIRED_HL_CHANNELS = ("l2Book", "bbo", "trades", "activeAssetCtx")
_EXPECTED_BINANCE_ACK_IDS = frozenset({1301, 1302})


class DualSourceConfigError(ValueError):
    """Raised when the Stage-0 dual-source runtime config is invalid."""


class DualSourceExitCode(IntEnum):
    SUCCESS = 0
    RECORDER_FAILED = 2
    STORAGE_AUDIT_FAILED = 3
    SOURCE_COVERAGE_FAILED = 4
    CLOCK_DOMAIN_FAILED = 5
    SUBSCRIPTION_ACK_FAILED = 6


@dataclass(frozen=True, slots=True)
class HyperliquidRuntimeConfig:
    source_id: str
    endpoint: str
    coins: tuple[str, ...]
    channels: tuple[str, ...]
    reconnect: ReconnectPolicy
    transport: TransportSettings

    def __post_init__(self) -> None:
        if self.source_id != HYPERLIQUID_SOURCE_ID:
            raise DualSourceConfigError(f"Hyperliquid source_id must be {HYPERLIQUID_SOURCE_ID}")
        if self.coins != _REQUIRED_HL_COINS:
            raise DualSourceConfigError("Hyperliquid coins must be exactly BTC,ETH")
        if self.channels != _REQUIRED_HL_CHANNELS:
            raise DualSourceConfigError(
                "Hyperliquid channels must be exactly l2Book,bbo,trades,activeAssetCtx"
            )
        if not self.endpoint.startswith(("ws://", "wss://")):
            raise DualSourceConfigError("Hyperliquid endpoint must use ws:// or wss://")


@dataclass(frozen=True, slots=True)
class BinanceRuntimeConfig:
    source_id: str
    public_endpoint: str
    market_endpoint: str
    reconnect: BinanceReconnectPolicy
    transport: BinanceTransportSettings

    def __post_init__(self) -> None:
        if self.source_id != BINANCE_SOURCE_ID:
            raise DualSourceConfigError(f"Binance source_id must be {BINANCE_SOURCE_ID}")
        for label, endpoint in (
            ("public_endpoint", self.public_endpoint),
            ("market_endpoint", self.market_endpoint),
        ):
            if not endpoint.startswith(("ws://", "wss://")):
                raise DualSourceConfigError(f"Binance {label} must use ws:// or wss://")


@dataclass(frozen=True, slots=True)
class DualSourceRecorderConfig:
    schema_version: int
    hyperliquid: HyperliquidRuntimeConfig
    binance: BinanceRuntimeConfig
    recorder: RecorderRuntimeSettings
    storage_root: Path
    manifest_path: Path
    run_duration_seconds: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise DualSourceConfigError("schema_version must be integer 1")
        if self.run_duration_seconds <= 0:
            raise DualSourceConfigError("run_duration_seconds must be positive")
        if not self.storage_root.as_posix().strip():
            raise DualSourceConfigError("storage_root must be non-empty")
        if not self.manifest_path.as_posix().strip():
            raise DualSourceConfigError("manifest_path must be non-empty")
        try:
            self.manifest_path.relative_to(self.storage_root)
        except ValueError as exc:
            raise DualSourceConfigError("manifest_path must be inside storage_root") from exc


@dataclass(frozen=True, slots=True)
class _SourceDone:
    source_index: int
    error: Exception | None


@dataclass(slots=True)
class _Observation:
    source_frame_counts: dict[str, int] = field(default_factory=dict)
    kind_counts: dict[str, int] = field(default_factory=dict)
    connection_ids: dict[str, set[str]] = field(default_factory=dict)
    clock_domains: set[tuple[str, str]] = field(default_factory=set)
    hl_acks: set[SubscriptionKey] = field(default_factory=set)
    binance_ack_ids: set[int] = field(default_factory=set)

    def observe(
        self,
        frame: CaptureFrame,
        *,
        hl_source_id: str,
        binance_source_id: str,
    ) -> None:
        meta = frame.metadata
        self.source_frame_counts[meta.source_id] = (
            self.source_frame_counts.get(meta.source_id, 0) + 1
        )
        self.connection_ids.setdefault(meta.source_id, set()).add(meta.connection_id)
        self.clock_domains.add((meta.host_id, meta.boot_id))

        if meta.source_id == hl_source_id:
            hl_classification = classify_public_payload(frame.payload)
            key = f"{meta.source_id}:{hl_classification.kind.value}"
            self.kind_counts[key] = self.kind_counts.get(key, 0) + 1
            hl_ack = hl_classification.acknowledged_subscription
            if hl_ack is not None:
                self.hl_acks.add(hl_ack)
            return

        if meta.source_id == binance_source_id:
            binance_classification = classify_binance_payload(frame.payload)
            key = f"{meta.source_id}:{binance_classification.kind.value}"
            self.kind_counts[key] = self.kind_counts.get(key, 0) + 1
            binance_ack = binance_classification.subscription_ack_id
            if (
                binance_classification.kind is BinanceFrameKind.SUBSCRIPTION_ACK
                and isinstance(binance_ack, int)
                and not isinstance(binance_ack, bool)
            ):
                self.binance_ack_ids.add(binance_ack)
            return

        key = f"{meta.source_id}:UNKNOWN_SOURCE"
        self.kind_counts[key] = self.kind_counts.get(key, 0) + 1


@dataclass(frozen=True, slots=True)
class DualSourceRecorderSummary:
    status: str
    exit_code: int
    run_id: str
    host_id: str
    boot_id: str
    duration_seconds: float
    recorder: RecorderStatus
    audit_clean: bool
    audit_items: tuple[StorageAuditItem, ...]
    source_frame_counts: tuple[tuple[str, int], ...]
    kind_counts: tuple[tuple[str, int], ...]
    source_connection_ids: tuple[tuple[str, tuple[str, ...]], ...]
    clock_domains: tuple[tuple[str, str], ...]
    hyperliquid_subscription_acks: tuple[SubscriptionKey, ...]
    expected_hyperliquid_subscription_acks: int
    binance_subscription_ack_ids: tuple[int, ...]
    required_source_ids: tuple[str, str]
    manifest_source_ids: tuple[str, ...]
    both_sources_observed: bool
    single_expected_clock_domain: bool
    all_hyperliquid_acks_observed: bool
    all_binance_acks_observed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "run_id": self.run_id,
            "host_id": self.host_id,
            "boot_id": self.boot_id,
            "duration_seconds": self.duration_seconds,
            "recorder": {
                "state": self.recorder.state.value,
                "shutdown_outcome": self.recorder.shutdown_outcome.value,
                "received_frames": self.recorder.counters.received_frames,
                "durable_frames": self.recorder.counters.durable_frames,
                "durable_bytes": self.recorder.counters.durable_bytes,
                "queue_high_watermark": self.recorder.counters.queue_high_watermark,
                "segment_id": self.recorder.segment_id,
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
            "source_frame_counts": dict(self.source_frame_counts),
            "kind_counts": dict(self.kind_counts),
            "source_connection_ids": {
                source: list(ids) for source, ids in self.source_connection_ids
            },
            "clock_domains": [list(domain) for domain in self.clock_domains],
            "hyperliquid_subscription_acks": [
                {"channel": ack.channel, "coin": ack.coin}
                for ack in self.hyperliquid_subscription_acks
            ],
            "expected_hyperliquid_subscription_acks": self.expected_hyperliquid_subscription_acks,
            "binance_subscription_ack_ids": list(self.binance_subscription_ack_ids),
            "required_source_ids": list(self.required_source_ids),
            "manifest_source_ids": list(self.manifest_source_ids),
            "both_sources_observed": self.both_sources_observed,
            "single_expected_clock_domain": self.single_expected_clock_domain,
            "all_hyperliquid_acks_observed": self.all_hyperliquid_acks_observed,
            "all_binance_acks_observed": self.all_binance_acks_observed,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


def load_dual_source_recorder_config(path: str | Path) -> DualSourceRecorderConfig:
    source = Path(path)
    try:
        raw_value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DualSourceConfigError(f"dual-source config cannot be decoded: {source}") from exc
    root = _object(raw_value, "config")
    _require_exact_fields(
        root,
        {
            "schema_version",
            "hyperliquid",
            "binance",
            "recorder",
            "storage_root",
            "manifest_path",
            "run_duration_seconds",
        },
        "config",
    )

    hl = _object(root["hyperliquid"], "hyperliquid")
    _require_exact_fields(
        hl,
        {"source_id", "endpoint", "coins", "channels", "reconnect", "transport"},
        "hyperliquid",
    )
    hl_reconnect_raw = _object(hl["reconnect"], "hyperliquid.reconnect")
    _require_exact_fields(
        hl_reconnect_raw,
        {"base_delay_seconds", "max_delay_seconds", "jitter_fraction"},
        "hyperliquid.reconnect",
    )
    hl_transport_raw = _object(hl["transport"], "hyperliquid.transport")
    _require_exact_fields(
        hl_transport_raw,
        {
            "heartbeat_idle_seconds",
            "max_message_bytes",
            "receive_queue_high_water",
            "open_timeout_seconds",
            "close_timeout_seconds",
        },
        "hyperliquid.transport",
    )

    bn = _object(root["binance"], "binance")
    _require_exact_fields(
        bn,
        {
            "source_id",
            "public_endpoint",
            "market_endpoint",
            "reconnect",
            "transport",
        },
        "binance",
    )
    bn_reconnect_raw = _object(bn["reconnect"], "binance.reconnect")
    _require_exact_fields(
        bn_reconnect_raw,
        {"base_delay_seconds", "max_delay_seconds", "jitter_fraction"},
        "binance.reconnect",
    )
    bn_transport_raw = _object(bn["transport"], "binance.transport")
    _require_exact_fields(
        bn_transport_raw,
        {
            "max_message_bytes",
            "receive_queue_high_water",
            "open_timeout_seconds",
            "close_timeout_seconds",
        },
        "binance.transport",
    )

    recorder_raw = _object(root["recorder"], "recorder")
    _require_exact_fields(
        recorder_raw,
        {
            "queue_capacity",
            "sync_every_frames",
            "shutdown_drain_timeout_seconds",
            "seal_on_shutdown",
        },
        "recorder",
    )

    return DualSourceRecorderConfig(
        schema_version=_int(root["schema_version"], "schema_version"),
        hyperliquid=HyperliquidRuntimeConfig(
            source_id=_str(hl["source_id"], "hyperliquid.source_id"),
            endpoint=_str(hl["endpoint"], "hyperliquid.endpoint"),
            coins=_str_tuple(hl["coins"], "hyperliquid.coins"),
            channels=_str_tuple(hl["channels"], "hyperliquid.channels"),
            reconnect=ReconnectPolicy(
                base_delay_seconds=_number(
                    hl_reconnect_raw["base_delay_seconds"],
                    "hyperliquid.reconnect.base_delay_seconds",
                ),
                max_delay_seconds=_number(
                    hl_reconnect_raw["max_delay_seconds"],
                    "hyperliquid.reconnect.max_delay_seconds",
                ),
                jitter_fraction=_number(
                    hl_reconnect_raw["jitter_fraction"],
                    "hyperliquid.reconnect.jitter_fraction",
                ),
            ),
            transport=TransportSettings(
                heartbeat_idle_seconds=_number(
                    hl_transport_raw["heartbeat_idle_seconds"],
                    "hyperliquid.transport.heartbeat_idle_seconds",
                ),
                max_message_bytes=_int(
                    hl_transport_raw["max_message_bytes"],
                    "hyperliquid.transport.max_message_bytes",
                ),
                receive_queue_high_water=_int(
                    hl_transport_raw["receive_queue_high_water"],
                    "hyperliquid.transport.receive_queue_high_water",
                ),
                open_timeout_seconds=_number(
                    hl_transport_raw["open_timeout_seconds"],
                    "hyperliquid.transport.open_timeout_seconds",
                ),
                close_timeout_seconds=_number(
                    hl_transport_raw["close_timeout_seconds"],
                    "hyperliquid.transport.close_timeout_seconds",
                ),
            ),
        ),
        binance=BinanceRuntimeConfig(
            source_id=_str(bn["source_id"], "binance.source_id"),
            public_endpoint=_str(bn["public_endpoint"], "binance.public_endpoint"),
            market_endpoint=_str(bn["market_endpoint"], "binance.market_endpoint"),
            reconnect=BinanceReconnectPolicy(
                base_delay_seconds=_number(
                    bn_reconnect_raw["base_delay_seconds"],
                    "binance.reconnect.base_delay_seconds",
                ),
                max_delay_seconds=_number(
                    bn_reconnect_raw["max_delay_seconds"],
                    "binance.reconnect.max_delay_seconds",
                ),
                jitter_fraction=_number(
                    bn_reconnect_raw["jitter_fraction"],
                    "binance.reconnect.jitter_fraction",
                ),
            ),
            transport=BinanceTransportSettings(
                max_message_bytes=_int(
                    bn_transport_raw["max_message_bytes"],
                    "binance.transport.max_message_bytes",
                ),
                receive_queue_high_water=_int(
                    bn_transport_raw["receive_queue_high_water"],
                    "binance.transport.receive_queue_high_water",
                ),
                open_timeout_seconds=_number(
                    bn_transport_raw["open_timeout_seconds"],
                    "binance.transport.open_timeout_seconds",
                ),
                close_timeout_seconds=_number(
                    bn_transport_raw["close_timeout_seconds"],
                    "binance.transport.close_timeout_seconds",
                ),
            ),
        ),
        recorder=RecorderRuntimeSettings(
            queue_capacity=_int(recorder_raw["queue_capacity"], "recorder.queue_capacity"),
            sync_every_frames=_int(
                recorder_raw["sync_every_frames"],
                "recorder.sync_every_frames",
            ),
            shutdown_drain_timeout_seconds=_number(
                recorder_raw["shutdown_drain_timeout_seconds"],
                "recorder.shutdown_drain_timeout_seconds",
            ),
            seal_on_shutdown=_bool(
                recorder_raw["seal_on_shutdown"],
                "recorder.seal_on_shutdown",
            ),
            rollover_mode=RolloverMode.DISABLED,
        ),
        storage_root=Path(_str(root["storage_root"], "storage_root")),
        manifest_path=Path(_str(root["manifest_path"], "manifest_path")),
        run_duration_seconds=_number(
            root["run_duration_seconds"],
            "run_duration_seconds",
        ),
    )


async def merge_capture_sources(
    sources: tuple[AsyncIterator[CaptureFrame], ...],
    *,
    queue_capacity: int,
) -> AsyncIterator[CaptureFrame]:
    if not sources:
        raise DualSourceConfigError("at least one capture source is required")
    if (
        isinstance(queue_capacity, bool)
        or not isinstance(queue_capacity, int)
        or queue_capacity <= 0
    ):
        raise DualSourceConfigError("multiplexer queue_capacity must be a positive integer")

    queue: asyncio.Queue[CaptureFrame | _SourceDone] = asyncio.Queue(maxsize=queue_capacity)

    async def pump(index: int, source: AsyncIterator[CaptureFrame]) -> None:
        error: Exception | None = None
        cancelled = False
        try:
            async for frame in source:
                await queue.put(frame)
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception as exc:
            error = exc
        finally:
            if not cancelled:
                await queue.put(_SourceDone(source_index=index, error=error))

    tasks = [
        asyncio.create_task(pump(index, source), name=f"dual-source-pump-{index}")
        for index, source in enumerate(sources)
    ]
    active = len(tasks)
    try:
        while active:
            item = await queue.get()
            if isinstance(item, _SourceDone):
                active -= 1
                if item.error is not None:
                    raise item.error
                continue
            yield item
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_dual_source_recorder(
    config: DualSourceRecorderConfig,
    *,
    identity: RuntimeIdentity | None = None,
    clock: Clock | None = None,
) -> DualSourceRecorderSummary:
    runtime_identity = identity or derive_runtime_identity()
    runtime_clock = clock or SystemClock(
        host_id=runtime_identity.host_id,
        boot_id=runtime_identity.boot_id,
    )

    hl_adapter = HyperliquidPublicAdapter(
        source_id=config.hyperliquid.source_id,
        coins=config.hyperliquid.coins,
        channels=config.hyperliquid.channels,
        clock=runtime_clock,
        transport=config.hyperliquid.transport,
        endpoint=config.hyperliquid.endpoint,
    )
    binance_adapter = BinanceReferenceAdapter(
        clock=runtime_clock,
        transport=config.binance.transport,
        source_id=config.binance.source_id,
        public_endpoint=config.binance.public_endpoint,
        market_endpoint=config.binance.market_endpoint,
    )

    sources = cast(
        tuple[AsyncIterator[CaptureFrame], ...],
        (
            hl_adapter.frames(config.hyperliquid.reconnect),
            binance_adapter.frames(config.binance.reconnect),
        ),
    )
    observation = _Observation()
    merged = _observe_frames(
        merge_capture_sources(sources, queue_capacity=config.recorder.queue_capacity),
        observation,
        hl_source_id=config.hyperliquid.source_id,
        binance_source_id=config.binance.source_id,
    )
    supervisor = RecorderSupervisor(
        source=merged,
        storage_root=config.storage_root,
        manifest_path=config.manifest_path,
        run_id=runtime_identity.run_id,
        settings=config.recorder,
        clock=runtime_clock,
        recorder_version="task-016",
        event_schema_version=1,
    )

    start = runtime_clock.sample()
    task = asyncio.create_task(supervisor.run(), name="dual-source-recorder")
    timer = asyncio.create_task(
        asyncio.sleep(config.run_duration_seconds),
        name="dual-source-duration",
    )
    try:
        done, _ = await asyncio.wait({task, timer}, return_when=asyncio.FIRST_COMPLETED)
        if timer in done and not task.done():
            supervisor.request_stop()
        recorder_status = await task
    finally:
        if not timer.done():
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)

    end = runtime_clock.sample()
    audit = audit_storage(config.storage_root, config.manifest_path)
    required_sources = (
        config.hyperliquid.source_id,
        config.binance.source_id,
    )
    observed_sources = {
        source for source, count in observation.source_frame_counts.items() if count > 0
    }
    both_sources = set(required_sources).issubset(observed_sources)
    expected_domain = (runtime_identity.host_id, runtime_identity.boot_id)
    single_expected_domain = observation.clock_domains == {expected_domain}
    expected_hl_acks = {
        SubscriptionKey(channel=channel, coin=coin)
        for coin in config.hyperliquid.coins
        for channel in config.hyperliquid.channels
    }
    all_hl_acks = expected_hl_acks.issubset(observation.hl_acks)
    all_binance_acks = _EXPECTED_BINANCE_ACK_IDS.issubset(observation.binance_ack_ids)
    manifest_sources = (
        recorder_status.sealed_record.source_ids
        if recorder_status.sealed_record is not None
        else ()
    )

    exit_code = _exit_code(
        recorder=recorder_status,
        audit_clean=audit.clean,
        both_sources_observed=both_sources,
        single_expected_clock_domain=single_expected_domain,
        all_hyperliquid_acks_observed=all_hl_acks,
        all_binance_acks_observed=all_binance_acks,
        manifest_source_ids=manifest_sources,
        required_source_ids=required_sources,
    )

    return DualSourceRecorderSummary(
        status="SUCCESS" if exit_code is DualSourceExitCode.SUCCESS else "FAILED",
        exit_code=int(exit_code),
        run_id=runtime_identity.run_id,
        host_id=runtime_identity.host_id,
        boot_id=runtime_identity.boot_id,
        duration_seconds=elapsed_ns(start, end) / 1_000_000_000,
        recorder=recorder_status,
        audit_clean=audit.clean,
        audit_items=audit.items,
        source_frame_counts=tuple(sorted(observation.source_frame_counts.items())),
        kind_counts=tuple(sorted(observation.kind_counts.items())),
        source_connection_ids=tuple(
            sorted(
                (source, tuple(sorted(ids))) for source, ids in observation.connection_ids.items()
            )
        ),
        clock_domains=tuple(sorted(observation.clock_domains)),
        hyperliquid_subscription_acks=tuple(sorted(observation.hl_acks)),
        expected_hyperliquid_subscription_acks=len(expected_hl_acks),
        binance_subscription_ack_ids=tuple(sorted(observation.binance_ack_ids)),
        required_source_ids=required_sources,
        manifest_source_ids=manifest_sources,
        both_sources_observed=both_sources,
        single_expected_clock_domain=single_expected_domain,
        all_hyperliquid_acks_observed=all_hl_acks,
        all_binance_acks_observed=all_binance_acks,
    )


async def _observe_frames(
    source: AsyncIterator[CaptureFrame],
    observation: _Observation,
    *,
    hl_source_id: str,
    binance_source_id: str,
) -> AsyncIterator[CaptureFrame]:
    async for frame in source:
        observation.observe(
            frame,
            hl_source_id=hl_source_id,
            binance_source_id=binance_source_id,
        )
        yield frame


def _exit_code(
    *,
    recorder: RecorderStatus,
    audit_clean: bool,
    both_sources_observed: bool,
    single_expected_clock_domain: bool,
    all_hyperliquid_acks_observed: bool,
    all_binance_acks_observed: bool,
    manifest_source_ids: tuple[str, ...],
    required_source_ids: tuple[str, str],
) -> DualSourceExitCode:
    if (
        recorder.state is not RecorderState.COMPLETE
        or recorder.shutdown_outcome is not ShutdownOutcome.CLEAN_DURABLE
    ):
        return DualSourceExitCode.RECORDER_FAILED
    if not audit_clean:
        return DualSourceExitCode.STORAGE_AUDIT_FAILED
    if not both_sources_observed or not set(required_source_ids).issubset(set(manifest_source_ids)):
        return DualSourceExitCode.SOURCE_COVERAGE_FAILED
    if not single_expected_clock_domain:
        return DualSourceExitCode.CLOCK_DOMAIN_FAILED
    if not all_hyperliquid_acks_observed or not all_binance_acks_observed:
        return DualSourceExitCode.SUBSCRIPTION_ACK_FAILED
    return DualSourceExitCode.SUCCESS


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DualSourceConfigError(f"{label} must be a string-keyed object")
    return cast(dict[str, object], value)


def _require_exact_fields(
    value: dict[str, object],
    expected: set[str],
    label: str,
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise DualSourceConfigError(f"{label} fields mismatch: missing={missing}, extra={extra}")


def _str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DualSourceConfigError(f"{label} must be a non-empty string")
    return value


def _str_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise DualSourceConfigError(f"{label} must be an array of non-empty strings")
    return tuple(cast(list[str], value))


def _int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DualSourceConfigError(f"{label} must be an integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DualSourceConfigError(f"{label} must be a number")
    return float(value)


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise DualSourceConfigError(f"{label} must be boolean")
    return value
