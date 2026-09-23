from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from cryptobot.data.instruments import (
    Environment,
    InstrumentRegistry,
    InstrumentValidationError,
)


class RecorderConfigError(ValueError):
    """Raised when recorder configuration is structurally or semantically invalid."""


_SUPPORTED_CHANNELS: dict[str, frozenset[str]] = {
    "hyperliquid": frozenset({"l2Book", "bbo", "trades", "activeAssetCtx"}),
}
_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "sources",
        "reference_feed",
        "storage",
        "buffering",
        "rollover",
        "reconnect",
        "clock_health",
    }
)
_SOURCE_FIELDS = frozenset(
    {"source_id", "venue", "environment", "enabled", "instrument_ids", "channels"}
)
_REFERENCE_FIELDS = frozenset({"required", "selected_source_id"})
_STORAGE_FIELDS = frozenset({"root", "raw_path", "normalized_path", "artifact_path"})
_BUFFERING_FIELDS = frozenset({"queue_capacity", "high_watermark_fraction"})
_ROLLOVER_FIELDS = frozenset({"max_segment_bytes", "max_segment_age_seconds"})
_RECONNECT_FIELDS = frozenset(
    {"base_delay_seconds", "max_delay_seconds", "jitter_fraction"}
)
_CLOCK_FIELDS = frozenset({"record"})


@dataclass(frozen=True, slots=True)
class RecorderSource:
    source_id: str
    venue: str
    environment: Environment
    enabled: bool
    instrument_ids: tuple[str, ...]
    channels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReferenceFeedConfig:
    required: bool
    selected_source_id: str | None


@dataclass(frozen=True, slots=True)
class StorageConfig:
    root: PurePosixPath
    raw_path: PurePosixPath
    normalized_path: PurePosixPath
    artifact_path: PurePosixPath


@dataclass(frozen=True, slots=True)
class BufferingConfig:
    queue_capacity: int | None
    high_watermark_fraction: float | None


@dataclass(frozen=True, slots=True)
class RolloverConfig:
    max_segment_bytes: int | None
    max_segment_age_seconds: float | None


@dataclass(frozen=True, slots=True)
class ReconnectConfig:
    base_delay_seconds: float | None
    max_delay_seconds: float | None
    jitter_fraction: float | None


@dataclass(frozen=True, slots=True)
class ClockHealthConfig:
    record: bool


@dataclass(frozen=True, slots=True)
class RecorderConfig:
    schema_version: int
    sources: tuple[RecorderSource, ...]
    reference_feed: ReferenceFeedConfig
    storage: StorageConfig
    buffering: BufferingConfig
    rollover: RolloverConfig
    reconnect: ReconnectConfig
    clock_health: ClockHealthConfig

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sources": [
                {
                    "source_id": source.source_id,
                    "venue": source.venue,
                    "environment": source.environment.value,
                    "enabled": source.enabled,
                    "instrument_ids": list(source.instrument_ids),
                    "channels": list(source.channels),
                }
                for source in self.sources
            ],
            "reference_feed": {
                "required": self.reference_feed.required,
                "selected_source_id": self.reference_feed.selected_source_id,
            },
            "storage": {
                "root": str(self.storage.root),
                "raw_path": str(self.storage.raw_path),
                "normalized_path": str(self.storage.normalized_path),
                "artifact_path": str(self.storage.artifact_path),
            },
            "buffering": {
                "queue_capacity": self.buffering.queue_capacity,
                "high_watermark_fraction": self.buffering.high_watermark_fraction,
            },
            "rollover": {
                "max_segment_bytes": self.rollover.max_segment_bytes,
                "max_segment_age_seconds": self.rollover.max_segment_age_seconds,
            },
            "reconnect": {
                "base_delay_seconds": self.reconnect.base_delay_seconds,
                "max_delay_seconds": self.reconnect.max_delay_seconds,
                "jitter_fraction": self.reconnect.jitter_fraction,
            },
            "clock_health": {"record": self.clock_health.record},
        }


def load_recorder_config(path: str | Path, registry: InstrumentRegistry) -> RecorderConfig:
    raw = _load_json_yaml_object(path)
    _require_exact_fields(raw, _ROOT_FIELDS, "recorder config")

    schema_version = raw["schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
    ):
        raise RecorderConfigError("schema_version must be integer 1")

    sources = _parse_sources(raw["sources"], registry)
    reference_feed = _parse_reference_feed(raw["reference_feed"], sources)
    storage = _parse_storage(raw["storage"])
    buffering = _parse_buffering(raw["buffering"])
    rollover = _parse_rollover(raw["rollover"])
    reconnect = _parse_reconnect(raw["reconnect"])
    clock_health = _parse_clock_health(raw["clock_health"])

    return RecorderConfig(
        schema_version=schema_version,
        sources=sources,
        reference_feed=reference_feed,
        storage=storage,
        buffering=buffering,
        rollover=rollover,
        reconnect=reconnect,
        clock_health=clock_health,
    )


def _parse_sources(value: Any, registry: InstrumentRegistry) -> tuple[RecorderSource, ...]:
    if not isinstance(value, list) or not value:
        raise RecorderConfigError("sources must be a non-empty array")

    sources = tuple(_parse_source(item, index, registry) for index, item in enumerate(value))
    source_ids = [source.source_id for source in sources]
    duplicates = sorted({source_id for source_id in source_ids if source_ids.count(source_id) > 1})
    if duplicates:
        raise RecorderConfigError(f"duplicate source_id values: {', '.join(duplicates)}")
    return sources


def _parse_source(raw: Any, index: int, registry: InstrumentRegistry) -> RecorderSource:
    if not isinstance(raw, dict):
        raise RecorderConfigError(f"sources[{index}] must be an object")
    _require_exact_fields(raw, _SOURCE_FIELDS, f"sources[{index}]")

    source_id = _required_string(raw, "source_id", f"sources[{index}]")
    venue = _required_string(raw, "venue", f"sources[{index}]")
    if venue != venue.lower():
        raise RecorderConfigError(f"sources[{index}].venue must be lowercase")

    environment = _parse_environment(raw["environment"], f"sources[{index}].environment")
    enabled = _required_bool(raw["enabled"], f"sources[{index}].enabled")
    instrument_ids = _parse_unique_strings(
        raw["instrument_ids"], f"sources[{index}].instrument_ids"
    )
    channels = _parse_unique_strings(raw["channels"], f"sources[{index}].channels")

    supported = _SUPPORTED_CHANNELS.get(venue)
    if supported is None:
        raise RecorderConfigError(f"sources[{index}] has unsupported venue: {venue}")
    unsupported_channels = sorted(set(channels) - supported)
    if unsupported_channels:
        raise RecorderConfigError(
            f"sources[{index}] has unsupported channels for {venue}: "
            f"{', '.join(unsupported_channels)}"
        )

    for instrument_id in instrument_ids:
        try:
            instrument = registry.get(instrument_id)
        except InstrumentValidationError as exc:
            raise RecorderConfigError(str(exc)) from exc
        if instrument.venue != venue or instrument.environment is not environment:
            raise RecorderConfigError(
                f"sources[{index}] instrument {instrument_id} does not match "
                f"{venue}/{environment.value}"
            )

    return RecorderSource(
        source_id=source_id,
        venue=venue,
        environment=environment,
        enabled=enabled,
        instrument_ids=instrument_ids,
        channels=channels,
    )


def _parse_reference_feed(
    raw: Any, sources: tuple[RecorderSource, ...]
) -> ReferenceFeedConfig:
    if not isinstance(raw, dict):
        raise RecorderConfigError("reference_feed must be an object")
    _require_exact_fields(raw, _REFERENCE_FIELDS, "reference_feed")

    required = _required_bool(raw["required"], "reference_feed.required")
    selected_source_id = _optional_string(
        raw["selected_source_id"], "reference_feed.selected_source_id"
    )
    if selected_source_id is not None:
        source_ids = {source.source_id for source in sources}
        if selected_source_id not in source_ids:
            raise RecorderConfigError(
                "reference_feed.selected_source_id must reference a configured source"
            )
    return ReferenceFeedConfig(required=required, selected_source_id=selected_source_id)


def _parse_storage(raw: Any) -> StorageConfig:
    if not isinstance(raw, dict):
        raise RecorderConfigError("storage must be an object")
    _require_exact_fields(raw, _STORAGE_FIELDS, "storage")
    return StorageConfig(
        root=_relative_path(raw["root"], "storage.root"),
        raw_path=_relative_path(raw["raw_path"], "storage.raw_path"),
        normalized_path=_relative_path(raw["normalized_path"], "storage.normalized_path"),
        artifact_path=_relative_path(raw["artifact_path"], "storage.artifact_path"),
    )


def _parse_buffering(raw: Any) -> BufferingConfig:
    if not isinstance(raw, dict):
        raise RecorderConfigError("buffering must be an object")
    _require_exact_fields(raw, _BUFFERING_FIELDS, "buffering")
    queue_capacity = _optional_positive_int(raw["queue_capacity"], "buffering.queue_capacity")
    high_watermark = _optional_fraction(
        raw["high_watermark_fraction"], "buffering.high_watermark_fraction"
    )
    return BufferingConfig(
        queue_capacity=queue_capacity,
        high_watermark_fraction=high_watermark,
    )


def _parse_rollover(raw: Any) -> RolloverConfig:
    if not isinstance(raw, dict):
        raise RecorderConfigError("rollover must be an object")
    _require_exact_fields(raw, _ROLLOVER_FIELDS, "rollover")
    return RolloverConfig(
        max_segment_bytes=_optional_positive_int(
            raw["max_segment_bytes"], "rollover.max_segment_bytes"
        ),
        max_segment_age_seconds=_optional_positive_number(
            raw["max_segment_age_seconds"], "rollover.max_segment_age_seconds"
        ),
    )


def _parse_reconnect(raw: Any) -> ReconnectConfig:
    if not isinstance(raw, dict):
        raise RecorderConfigError("reconnect must be an object")
    _require_exact_fields(raw, _RECONNECT_FIELDS, "reconnect")

    base = _optional_positive_number(raw["base_delay_seconds"], "reconnect.base_delay_seconds")
    maximum = _optional_positive_number(raw["max_delay_seconds"], "reconnect.max_delay_seconds")
    jitter = _optional_fraction(raw["jitter_fraction"], "reconnect.jitter_fraction")

    if base is not None and maximum is not None and base > maximum:
        raise RecorderConfigError(
            "reconnect.base_delay_seconds must not exceed reconnect.max_delay_seconds"
        )
    return ReconnectConfig(
        base_delay_seconds=base,
        max_delay_seconds=maximum,
        jitter_fraction=jitter,
    )


def _parse_clock_health(raw: Any) -> ClockHealthConfig:
    if not isinstance(raw, dict):
        raise RecorderConfigError("clock_health must be an object")
    _require_exact_fields(raw, _CLOCK_FIELDS, "clock_health")
    return ClockHealthConfig(record=_required_bool(raw["record"], "clock_health.record"))


def _load_json_yaml_object(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RecorderConfigError(
            f"{source} must be JSON-compatible YAML: {exc.msg} at line {exc.lineno}"
        ) from exc
    if not isinstance(raw, dict):
        raise RecorderConfigError("recorder config root must be an object")
    return raw


def _require_exact_fields(raw: dict[str, Any], expected: frozenset[str], label: str) -> None:
    unknown = set(raw) - expected
    if unknown:
        raise RecorderConfigError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
    missing = expected - set(raw)
    if missing:
        raise RecorderConfigError(f"{label} is missing fields: {', '.join(sorted(missing))}")


def _required_string(raw: dict[str, Any], field: str, label: str) -> str:
    value = raw[field]
    if not isinstance(value, str) or not value.strip():
        raise RecorderConfigError(f"{label}.{field} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RecorderConfigError(f"{field} must be null or a non-empty string")
    return value.strip()


def _required_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise RecorderConfigError(f"{field} must be boolean")
    return value


def _parse_unique_strings(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise RecorderConfigError(f"{field} must be a non-empty array")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise RecorderConfigError(f"{field}[{index}] must be a non-empty string")
        result.append(item.strip())
    if len(result) != len(set(result)):
        raise RecorderConfigError(f"{field} must not contain duplicates")
    return tuple(result)


def _parse_environment(value: Any, field: str) -> Environment:
    if not isinstance(value, str):
        raise RecorderConfigError(f"{field} must be a string")
    try:
        return Environment(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in Environment)
        raise RecorderConfigError(f"{field} must be one of: {allowed}") from exc


def _relative_path(value: Any, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise RecorderConfigError(f"{field} must be a non-empty relative path")
    normalized = PurePosixPath(value.strip())
    if normalized.is_absolute() or ".." in normalized.parts:
        raise RecorderConfigError(f"{field} must not be absolute or traverse parent directories")
    if str(normalized) == ".":
        raise RecorderConfigError(f"{field} must not resolve to current directory")
    return normalized


def _optional_positive_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RecorderConfigError(f"{field} must be null or a positive integer")
    return value


def _optional_positive_number(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise RecorderConfigError(f"{field} must be null or a positive number")
    return float(value)


def _optional_fraction(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RecorderConfigError(f"{field} must be null or a number in (0, 1)")
    parsed = float(value)
    if not 0 < parsed < 1:
        raise RecorderConfigError(f"{field} must be null or a number in (0, 1)")
    return parsed
