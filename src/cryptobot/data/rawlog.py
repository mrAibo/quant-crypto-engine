from __future__ import annotations

import hashlib
import json
import os
import struct
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Self, cast


MAGIC = b"QCR1"
FRAME_VERSION = 1
PREFIX = struct.Struct(">4sIQ")
CHECKSUM_SIZE = 32
MAX_METADATA_BYTES = 1_048_576
MAX_PAYLOAD_BYTES = 268_435_456


class RawLogError(ValueError):
    """Base error for the raw framed log."""


class RawLogClosedError(RawLogError):
    """Raised when operating on a closed raw log."""


class RawLogCorruptionError(RawLogError):
    """Raised when raw log bytes cannot be trusted or safely recovered."""


class TailState(StrEnum):
    CLEAN = "CLEAN"
    INCOMPLETE = "INCOMPLETE"
    CORRUPT = "CORRUPT"


_METADATA_FIELDS = frozenset(
    {
        "schema_version",
        "source_id",
        "recv_wall_ns",
        "recv_mono_ns",
        "host_id",
        "boot_id",
        "connection_id",
        "ingest_seq",
        "channel_hint",
        "capture_flags",
    }
)


@dataclass(frozen=True, slots=True)
class RawFrameMetadata:
    schema_version: int
    source_id: str
    recv_wall_ns: int
    recv_mono_ns: int
    host_id: str
    boot_id: str
    connection_id: str
    ingest_seq: int
    channel_hint: str | None
    capture_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != FRAME_VERSION
        ):
            raise RawLogError(f"schema_version must be integer {FRAME_VERSION}")
        for field, value in (
            ("source_id", self.source_id),
            ("host_id", self.host_id),
            ("boot_id", self.boot_id),
            ("connection_id", self.connection_id),
        ):
            if not value.strip():
                raise RawLogError(f"{field} must be non-empty")

        _require_nonnegative_int(self.recv_wall_ns, "recv_wall_ns")
        _require_nonnegative_int(self.recv_mono_ns, "recv_mono_ns")
        _require_nonnegative_int(self.ingest_seq, "ingest_seq")

        if self.channel_hint is not None and not self.channel_hint.strip():
            raise RawLogError("channel_hint must be null or non-empty")
        if any(not flag.strip() for flag in self.capture_flags):
            raise RawLogError("capture_flags must contain only non-empty strings")
        if len(set(self.capture_flags)) != len(self.capture_flags):
            raise RawLogError("capture_flags must not contain duplicates")
        if tuple(sorted(self.capture_flags)) != self.capture_flags:
            raise RawLogError("capture_flags must be sorted for deterministic encoding")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "recv_wall_ns": self.recv_wall_ns,
            "recv_mono_ns": self.recv_mono_ns,
            "host_id": self.host_id,
            "boot_id": self.boot_id,
            "connection_id": self.connection_id,
            "ingest_seq": self.ingest_seq,
            "channel_hint": self.channel_hint,
            "capture_flags": list(self.capture_flags),
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> Self:
        unknown = set(raw) - _METADATA_FIELDS
        missing = _METADATA_FIELDS - set(raw)
        if unknown:
            raise RawLogCorruptionError(
                f"raw metadata has unknown fields: {', '.join(sorted(unknown))}"
            )
        if missing:
            raise RawLogCorruptionError(
                f"raw metadata is missing fields: {', '.join(sorted(missing))}"
            )

        flags = raw["capture_flags"]
        if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
            raise RawLogCorruptionError("capture_flags must be an array of strings")
        flag_values = cast(list[str], flags)

        try:
            return cls(
                schema_version=_require_mapping_int(raw, "schema_version"),
                source_id=_require_mapping_str(raw, "source_id"),
                recv_wall_ns=_require_mapping_int(raw, "recv_wall_ns"),
                recv_mono_ns=_require_mapping_int(raw, "recv_mono_ns"),
                host_id=_require_mapping_str(raw, "host_id"),
                boot_id=_require_mapping_str(raw, "boot_id"),
                connection_id=_require_mapping_str(raw, "connection_id"),
                ingest_seq=_require_mapping_int(raw, "ingest_seq"),
                channel_hint=_require_mapping_optional_str(raw, "channel_hint"),
                capture_flags=tuple(flag_values),
            )
        except RawLogError as exc:
            raise RawLogCorruptionError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class RawRef:
    segment_id: str
    offset: int
    frame_length: int
    payload_length: int
    payload_sha256: str
    frame_checksum: str


@dataclass(frozen=True, slots=True)
class RawFrame:
    ref: RawRef
    metadata: RawFrameMetadata
    payload: bytes


@dataclass(frozen=True, slots=True)
class RawScanResult:
    valid_frames: int
    valid_bytes: int
    tail_state: TailState
    first_bad_offset: int | None


class RawLog:
    def __init__(
        self,
        path: Path,
        segment_id: str,
        file: BinaryIO,
        *,
        durable_length: int,
    ) -> None:
        self._path = path
        self._segment_id = segment_id
        self._file = file
        self._closed = False
        self._durable_length = durable_length

    @classmethod
    def open(cls, path: str | Path, segment_id: str) -> Self:
        target = Path(path)
        if not segment_id.strip():
            raise RawLogError("segment_id must be non-empty")
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            scan = scan_raw_log(target, segment_id)
            if scan.tail_state is not TailState.CLEAN:
                raise RawLogCorruptionError(
                    f"cannot append to {scan.tail_state.value.lower()} raw log; recover first"
                )
            durable_length = scan.valid_bytes
        else:
            durable_length = 0

        file = target.open("ab")
        file.seek(0, os.SEEK_END)
        return cls(target, segment_id, file, durable_length=durable_length)

    @property
    def durable_length(self) -> int:
        return self._durable_length

    @property
    def closed(self) -> bool:
        return self._closed

    def append(self, metadata: RawFrameMetadata, payload: bytes) -> RawRef:
        self._require_open()
        if not isinstance(payload, bytes):
            raise RawLogError("payload must be bytes")

        metadata_bytes = encode_raw_metadata(metadata)
        _validate_lengths(len(metadata_bytes), len(payload))
        prefix = PREFIX.pack(MAGIC, len(metadata_bytes), len(payload))
        frame_body = prefix + metadata_bytes + payload
        checksum = hashlib.sha256(frame_body).digest()

        offset = self._file.tell()
        self._file.write(frame_body)
        self._file.write(checksum)

        return RawRef(
            segment_id=self._segment_id,
            offset=offset,
            frame_length=len(frame_body) + CHECKSUM_SIZE,
            payload_length=len(payload),
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            frame_checksum=checksum.hex(),
        )

    def sync(self) -> None:
        self._require_open()
        self._file.flush()
        os.fsync(self._file.fileno())
        self._durable_length = self._file.tell()

    def close(self) -> None:
        if self._closed:
            return
        self._file.close()
        self._closed = True

    def __enter__(self) -> Self:
        self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            raise RawLogClosedError("raw log is closed")


def encode_raw_metadata(metadata: RawFrameMetadata) -> bytes:
    encoded = json.dumps(
        metadata.as_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if len(encoded) > MAX_METADATA_BYTES:
        raise RawLogError(
            f"metadata exceeds maximum size of {MAX_METADATA_BYTES} bytes"
        )
    return encoded


def scan_raw_log(path: str | Path, segment_id: str) -> RawScanResult:
    target = Path(path)
    if not segment_id.strip():
        raise RawLogError("segment_id must be non-empty")
    if not target.exists():
        raise RawLogError(f"raw log does not exist: {target}")

    size = target.stat().st_size
    valid_frames = 0
    valid_bytes = 0

    with target.open("rb") as file:
        while valid_bytes < size:
            outcome = _read_one(file, segment_id, valid_bytes, size, include_payload=False)
            if isinstance(outcome, RawScanResult):
                return RawScanResult(
                    valid_frames=valid_frames,
                    valid_bytes=valid_bytes,
                    tail_state=outcome.tail_state,
                    first_bad_offset=outcome.first_bad_offset,
                )
            valid_frames += 1
            valid_bytes += outcome.ref.frame_length

    return RawScanResult(
        valid_frames=valid_frames,
        valid_bytes=valid_bytes,
        tail_state=TailState.CLEAN,
        first_bad_offset=None,
    )


def iter_raw_frames(path: str | Path, segment_id: str) -> Iterator[RawFrame]:
    target = Path(path)
    if not target.exists():
        raise RawLogError(f"raw log does not exist: {target}")
    if not segment_id.strip():
        raise RawLogError("segment_id must be non-empty")

    size = target.stat().st_size
    offset = 0
    with target.open("rb") as file:
        while offset < size:
            outcome = _read_one(file, segment_id, offset, size, include_payload=True)
            if isinstance(outcome, RawScanResult):
                raise RawLogCorruptionError(
                    f"raw log {outcome.tail_state.value.lower()} at offset "
                    f"{outcome.first_bad_offset}"
                )
            yield outcome
            offset += outcome.ref.frame_length


def truncate_incomplete_tail(
    path: str | Path,
    scan: RawScanResult,
) -> int:
    if scan.tail_state is not TailState.INCOMPLETE:
        raise RawLogCorruptionError(
            "automatic truncation is allowed only for an incomplete tail"
        )

    target = Path(path)
    with target.open("r+b") as file:
        file.truncate(scan.valid_bytes)
        file.flush()
        os.fsync(file.fileno())
    return scan.valid_bytes


def _read_one(
    file: BinaryIO,
    segment_id: str,
    offset: int,
    file_size: int,
    *,
    include_payload: bool,
) -> RawFrame | RawScanResult:
    file.seek(offset)
    remaining = file_size - offset
    if remaining < PREFIX.size:
        return _bad_tail(TailState.INCOMPLETE, offset)

    prefix = file.read(PREFIX.size)
    if len(prefix) != PREFIX.size:
        return _bad_tail(TailState.INCOMPLETE, offset)

    magic, metadata_length, payload_length = PREFIX.unpack(prefix)
    if magic != MAGIC:
        return _bad_tail(TailState.CORRUPT, offset)
    try:
        _validate_lengths(metadata_length, payload_length)
    except RawLogError:
        return _bad_tail(TailState.CORRUPT, offset)

    total_length = PREFIX.size + metadata_length + payload_length + CHECKSUM_SIZE
    if remaining < total_length:
        return _bad_tail(TailState.INCOMPLETE, offset)

    metadata_bytes = file.read(metadata_length)
    payload = file.read(payload_length)
    checksum = file.read(CHECKSUM_SIZE)
    if (
        len(metadata_bytes) != metadata_length
        or len(payload) != payload_length
        or len(checksum) != CHECKSUM_SIZE
    ):
        return _bad_tail(TailState.INCOMPLETE, offset)

    expected = hashlib.sha256(prefix + metadata_bytes + payload).digest()
    if checksum != expected:
        return _bad_tail(TailState.CORRUPT, offset)

    try:
        metadata = _decode_raw_metadata(metadata_bytes)
    except RawLogCorruptionError:
        return _bad_tail(TailState.CORRUPT, offset)

    ref = RawRef(
        segment_id=segment_id,
        offset=offset,
        frame_length=total_length,
        payload_length=payload_length,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        frame_checksum=checksum.hex(),
    )
    return RawFrame(
        ref=ref,
        metadata=metadata,
        payload=payload if include_payload else b"",
    )


def _decode_raw_metadata(value: bytes) -> RawFrameMetadata:
    try:
        decoded = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RawLogCorruptionError("raw metadata is not valid canonical UTF-8 JSON") from exc
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str) for key in decoded
    ):
        raise RawLogCorruptionError("raw metadata must decode to a string-keyed object")
    raw = cast(dict[str, object], decoded)
    return RawFrameMetadata.from_mapping(raw)


def _validate_lengths(metadata_length: int, payload_length: int) -> None:
    if metadata_length < 0 or metadata_length > MAX_METADATA_BYTES:
        raise RawLogError(f"invalid metadata length: {metadata_length}")
    if payload_length < 0 or payload_length > MAX_PAYLOAD_BYTES:
        raise RawLogError(f"invalid payload length: {payload_length}")


def _bad_tail(state: TailState, offset: int) -> RawScanResult:
    return RawScanResult(
        valid_frames=0,
        valid_bytes=0,
        tail_state=state,
        first_bad_offset=offset,
    )


def _require_nonnegative_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RawLogError(f"{field} must be a non-negative integer")


def _require_mapping_int(raw: Mapping[str, object], field: str) -> int:
    value = raw[field]
    if isinstance(value, bool) or not isinstance(value, int):
        raise RawLogCorruptionError(f"{field} must be an integer")
    return value


def _require_mapping_str(raw: Mapping[str, object], field: str) -> str:
    value = raw[field]
    if not isinstance(value, str):
        raise RawLogCorruptionError(f"{field} must be a string")
    return value


def _require_mapping_optional_str(
    raw: Mapping[str, object],
    field: str,
) -> str | None:
    value = raw[field]
    if value is None:
        return None
    if not isinstance(value, str):
        raise RawLogCorruptionError(f"{field} must be null or a string")
    return value
