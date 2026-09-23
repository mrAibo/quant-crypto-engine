from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import cast

from cryptobot.data.rawlog import (
    FRAME_VERSION,
    RawLogCorruptionError,
    TailState,
    iter_raw_frames,
    scan_raw_log,
    truncate_incomplete_tail,
)


MANIFEST_SCHEMA_VERSION = 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FaultHook = Callable[[str], None]


class ManifestError(ValueError):
    """Raised when sealed-segment or manifest state cannot be trusted."""


class PublicationStatus(StrEnum):
    PUBLISHED = "PUBLISHED"


class AuditState(StrEnum):
    VALID = "VALID"
    MISSING = "MISSING"
    MISMATCH = "MISMATCH"
    ORPHAN_COMPLETE = "ORPHAN_COMPLETE"
    OPEN_RECOVERABLE = "OPEN_RECOVERABLE"
    OPEN_INCOMPLETE_RECOVERABLE = "OPEN_INCOMPLETE_RECOVERABLE"
    CORRUPT = "CORRUPT"
    STALE_MANIFEST_TEMP = "STALE_MANIFEST_TEMP"
    MANIFEST_CORRUPT = "MANIFEST_CORRUPT"


_RECORD_FIELDS = frozenset(
    {
        "record_version",
        "segment_id",
        "relative_path",
        "byte_length",
        "sha256",
        "raw_frame_version",
        "frame_count",
        "min_recv_wall_ns",
        "max_recv_wall_ns",
        "min_ingest_seq",
        "max_ingest_seq",
        "source_ids",
        "sealed_wall_ns",
        "recorder_version",
        "event_schema_version",
        "publication_status",
    }
)
_MANIFEST_FIELDS = frozenset({"schema_version", "records"})


@dataclass(frozen=True, slots=True)
class SegmentManifestRecord:
    record_version: int
    segment_id: str
    relative_path: str
    byte_length: int
    sha256: str
    raw_frame_version: int
    frame_count: int
    min_recv_wall_ns: int | None
    max_recv_wall_ns: int | None
    min_ingest_seq: int | None
    max_ingest_seq: int | None
    source_ids: tuple[str, ...]
    sealed_wall_ns: int
    recorder_version: str | None
    event_schema_version: int | None
    publication_status: PublicationStatus

    def __post_init__(self) -> None:
        if self.record_version != 1:
            raise ManifestError("record_version must be integer 1")
        if not self.segment_id.strip():
            raise ManifestError("segment_id must be non-empty")
        _validate_relative_path(self.relative_path)
        _require_nonnegative_int(self.byte_length, "byte_length")
        if not _SHA256_RE.fullmatch(self.sha256):
            raise ManifestError("sha256 must contain 64 lowercase hex characters")
        if self.raw_frame_version != FRAME_VERSION:
            raise ManifestError(
                f"raw_frame_version must be {FRAME_VERSION}"
            )
        _require_nonnegative_int(self.frame_count, "frame_count")
        _validate_optional_range(
            self.min_recv_wall_ns,
            self.max_recv_wall_ns,
            "recv_wall_ns",
        )
        _validate_optional_range(
            self.min_ingest_seq,
            self.max_ingest_seq,
            "ingest_seq",
        )
        _require_nonnegative_int(self.sealed_wall_ns, "sealed_wall_ns")
        if self.recorder_version is not None and not self.recorder_version.strip():
            raise ManifestError("recorder_version must be null or non-empty")
        if self.event_schema_version is not None:
            _require_nonnegative_int(
                self.event_schema_version,
                "event_schema_version",
            )
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ManifestError("source_ids must not contain duplicates")
        if tuple(sorted(self.source_ids)) != self.source_ids:
            raise ManifestError("source_ids must be sorted")
        if any(not value.strip() for value in self.source_ids):
            raise ManifestError("source_ids must contain only non-empty strings")

        if self.frame_count == 0:
            if any(
                value is not None
                for value in (
                    self.min_recv_wall_ns,
                    self.max_recv_wall_ns,
                    self.min_ingest_seq,
                    self.max_ingest_seq,
                )
            ):
                raise ManifestError("empty segment cannot have min/max frame metadata")
        elif any(
            value is None
            for value in (
                self.min_recv_wall_ns,
                self.max_recv_wall_ns,
                self.min_ingest_seq,
                self.max_ingest_seq,
            )
        ):
            raise ManifestError("non-empty segment requires min/max frame metadata")

    def as_dict(self) -> dict[str, object]:
        return {
            "record_version": self.record_version,
            "segment_id": self.segment_id,
            "relative_path": self.relative_path,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
            "raw_frame_version": self.raw_frame_version,
            "frame_count": self.frame_count,
            "min_recv_wall_ns": self.min_recv_wall_ns,
            "max_recv_wall_ns": self.max_recv_wall_ns,
            "min_ingest_seq": self.min_ingest_seq,
            "max_ingest_seq": self.max_ingest_seq,
            "source_ids": list(self.source_ids),
            "sealed_wall_ns": self.sealed_wall_ns,
            "recorder_version": self.recorder_version,
            "event_schema_version": self.event_schema_version,
            "publication_status": self.publication_status.value,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> SegmentManifestRecord:
        _require_exact_fields(raw, _RECORD_FIELDS, "manifest record")
        source_ids_raw = raw["source_ids"]
        if not isinstance(source_ids_raw, list) or not all(
            isinstance(value, str) for value in source_ids_raw
        ):
            raise ManifestError("source_ids must be an array of strings")
        source_ids = tuple(cast(list[str], source_ids_raw))

        status_raw = raw["publication_status"]
        if not isinstance(status_raw, str):
            raise ManifestError("publication_status must be a string")
        try:
            status = PublicationStatus(status_raw)
        except ValueError as exc:
            raise ManifestError(
                f"unsupported publication_status: {status_raw}"
            ) from exc

        return cls(
            record_version=_mapping_int(raw, "record_version"),
            segment_id=_mapping_str(raw, "segment_id"),
            relative_path=_mapping_str(raw, "relative_path"),
            byte_length=_mapping_int(raw, "byte_length"),
            sha256=_mapping_str(raw, "sha256"),
            raw_frame_version=_mapping_int(raw, "raw_frame_version"),
            frame_count=_mapping_int(raw, "frame_count"),
            min_recv_wall_ns=_mapping_optional_int(raw, "min_recv_wall_ns"),
            max_recv_wall_ns=_mapping_optional_int(raw, "max_recv_wall_ns"),
            min_ingest_seq=_mapping_optional_int(raw, "min_ingest_seq"),
            max_ingest_seq=_mapping_optional_int(raw, "max_ingest_seq"),
            source_ids=source_ids,
            sealed_wall_ns=_mapping_int(raw, "sealed_wall_ns"),
            recorder_version=_mapping_optional_str(raw, "recorder_version"),
            event_schema_version=_mapping_optional_int(raw, "event_schema_version"),
            publication_status=status,
        )


@dataclass(frozen=True, slots=True)
class SegmentManifest:
    schema_version: int
    records: tuple[SegmentManifestRecord, ...]

    def __post_init__(self) -> None:
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ManifestError(
                f"schema_version must be {MANIFEST_SCHEMA_VERSION}"
            )
        ids = [record.segment_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ManifestError("duplicate segment_id in manifest")
        paths = [record.relative_path for record in self.records]
        if len(paths) != len(set(paths)):
            raise ManifestError("duplicate relative_path in manifest")
        ordered = tuple(sorted(self.records, key=lambda record: record.segment_id))
        object.__setattr__(self, "records", ordered)

    @classmethod
    def empty(cls) -> SegmentManifest:
        return cls(schema_version=MANIFEST_SCHEMA_VERSION, records=())

    def with_record(self, record: SegmentManifestRecord) -> SegmentManifest:
        if any(existing.segment_id == record.segment_id for existing in self.records):
            raise ManifestError(f"duplicate segment_id: {record.segment_id}")
        if any(
            existing.relative_path == record.relative_path for existing in self.records
        ):
            raise ManifestError(f"duplicate relative_path: {record.relative_path}")
        return SegmentManifest(
            schema_version=self.schema_version,
            records=(*self.records, record),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "records": [record.as_dict() for record in self.records],
        }


@dataclass(frozen=True, slots=True)
class SegmentStats:
    frame_count: int
    min_recv_wall_ns: int | None
    max_recv_wall_ns: int | None
    min_ingest_seq: int | None
    max_ingest_seq: int | None
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StorageAuditItem:
    relative_path: str
    segment_id: str | None
    state: AuditState
    detail: str


@dataclass(frozen=True, slots=True)
class StorageAuditReport:
    items: tuple[StorageAuditItem, ...]

    @property
    def clean(self) -> bool:
        return all(item.state is AuditState.VALID for item in self.items)


def load_manifest(path: str | Path) -> SegmentManifest:
    target = Path(path)
    if not target.exists():
        return SegmentManifest.empty()
    try:
        decoded = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"manifest cannot be decoded: {target}") from exc
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str) for key in decoded
    ):
        raise ManifestError("manifest root must be a string-keyed object")
    raw = cast(dict[str, object], decoded)
    _require_exact_fields(raw, _MANIFEST_FIELDS, "manifest")

    schema_version = _mapping_int(raw, "schema_version")
    records_raw = raw["records"]
    if not isinstance(records_raw, list):
        raise ManifestError("manifest records must be an array")
    records: list[SegmentManifestRecord] = []
    for item in records_raw:
        if not isinstance(item, dict) or not all(
            isinstance(key, str) for key in item
        ):
            raise ManifestError("manifest record must be a string-keyed object")
        records.append(
            SegmentManifestRecord.from_mapping(cast(dict[str, object], item))
        )
    return SegmentManifest(schema_version=schema_version, records=tuple(records))


def encode_manifest(manifest: SegmentManifest) -> bytes:
    return (
        json.dumps(
            manifest.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def commit_manifest(
    path: str | Path,
    manifest: SegmentManifest,
    *,
    fault_hook: FaultHook | None = None,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f"{target.name}.tmp")
    _fault(fault_hook, "before_manifest_temp_write")
    payload = encode_manifest(manifest)

    with temp.open("wb") as file:
        file.write(payload)
        _fault(fault_hook, "after_manifest_temp_write")
        file.flush()
        os.fsync(file.fileno())
    _fault(fault_hook, "after_manifest_temp_fsync")

    os.replace(temp, target)
    _fault(fault_hook, "after_manifest_replace")
    _fsync_directory(target.parent)
    _fault(fault_hook, "after_manifest_dir_fsync")


def seal_segment(
    *,
    open_path: str | Path,
    final_path: str | Path,
    storage_root: str | Path,
    manifest_path: str | Path,
    segment_id: str,
    sealed_wall_ns: int,
    recorder_version: str | None = None,
    event_schema_version: int | None = None,
    fault_hook: FaultHook | None = None,
) -> SegmentManifestRecord:
    source = Path(open_path)
    final = Path(final_path)
    root = Path(storage_root)

    if not source.exists():
        raise ManifestError(f"open segment does not exist: {source}")
    if final.exists():
        raise ManifestError(f"sealed segment already exists: {final}")
    if not segment_id.strip():
        raise ManifestError("segment_id must be non-empty")
    _require_nonnegative_int(sealed_wall_ns, "sealed_wall_ns")

    final.parent.mkdir(parents=True, exist_ok=True)
    if source.parent.stat().st_dev != final.parent.stat().st_dev:
        raise ManifestError("segment rename must stay on the same filesystem")

    scan = scan_raw_log(source, segment_id)
    if scan.tail_state is not TailState.CLEAN:
        raise ManifestError(
            f"segment must be CLEAN before sealing, got {scan.tail_state.value}"
        )
    stats = derive_segment_stats(source, segment_id)

    _fault(fault_hook, "before_segment_fsync")
    with source.open("rb") as file:
        os.fsync(file.fileno())
    _fault(fault_hook, "after_segment_fsync")

    byte_length = source.stat().st_size
    sha256 = _sha256_file(source)
    os.replace(source, final)
    _fault(fault_hook, "after_segment_rename")
    _fsync_directory(final.parent)
    _fault(fault_hook, "after_segment_dir_fsync")

    relative_path = _relative_to_root(final, root)
    record = SegmentManifestRecord(
        record_version=1,
        segment_id=segment_id,
        relative_path=relative_path,
        byte_length=byte_length,
        sha256=sha256,
        raw_frame_version=FRAME_VERSION,
        frame_count=stats.frame_count,
        min_recv_wall_ns=stats.min_recv_wall_ns,
        max_recv_wall_ns=stats.max_recv_wall_ns,
        min_ingest_seq=stats.min_ingest_seq,
        max_ingest_seq=stats.max_ingest_seq,
        source_ids=stats.source_ids,
        sealed_wall_ns=sealed_wall_ns,
        recorder_version=recorder_version,
        event_schema_version=event_schema_version,
        publication_status=PublicationStatus.PUBLISHED,
    )

    manifest = load_manifest(manifest_path).with_record(record)
    commit_manifest(manifest_path, manifest, fault_hook=fault_hook)
    return record


def derive_segment_stats(path: str | Path, segment_id: str) -> SegmentStats:
    frames = list(iter_raw_frames(path, segment_id))
    if not frames:
        return SegmentStats(
            frame_count=0,
            min_recv_wall_ns=None,
            max_recv_wall_ns=None,
            min_ingest_seq=None,
            max_ingest_seq=None,
            source_ids=(),
        )

    recv_values = [frame.metadata.recv_wall_ns for frame in frames]
    ingest_values = [frame.metadata.ingest_seq for frame in frames]
    source_ids = tuple(sorted({frame.metadata.source_id for frame in frames}))
    return SegmentStats(
        frame_count=len(frames),
        min_recv_wall_ns=min(recv_values),
        max_recv_wall_ns=max(recv_values),
        min_ingest_seq=min(ingest_values),
        max_ingest_seq=max(ingest_values),
        source_ids=source_ids,
    )


def recover_open_segment(path: str | Path, segment_id: str) -> StorageAuditItem:
    target = Path(path)
    scan = scan_raw_log(target, segment_id)
    if scan.tail_state is TailState.CORRUPT:
        raise ManifestError("corrupt open segment cannot be auto-recovered")
    if scan.tail_state is TailState.INCOMPLETE:
        truncate_incomplete_tail(target, scan)
        final_scan = scan_raw_log(target, segment_id)
        if final_scan.tail_state is not TailState.CLEAN:
            raise ManifestError("open segment did not recover to CLEAN state")
        return StorageAuditItem(
            relative_path=target.name,
            segment_id=segment_id,
            state=AuditState.OPEN_RECOVERABLE,
            detail="incomplete tail truncated to valid prefix",
        )
    return StorageAuditItem(
        relative_path=target.name,
        segment_id=segment_id,
        state=AuditState.OPEN_RECOVERABLE,
        detail="open segment already clean",
    )


def audit_storage(
    storage_root: str | Path,
    manifest_path: str | Path,
) -> StorageAuditReport:
    root = Path(storage_root)
    target_manifest = Path(manifest_path)
    items: list[StorageAuditItem] = []

    try:
        manifest = load_manifest(target_manifest)
    except ManifestError as exc:
        manifest = SegmentManifest.empty()
        items.append(
            StorageAuditItem(
                relative_path=_display_path(target_manifest, root),
                segment_id=None,
                state=AuditState.MANIFEST_CORRUPT,
                detail=str(exc),
            )
        )

    temp = target_manifest.with_name(f"{target_manifest.name}.tmp")
    if temp.exists():
        items.append(
            StorageAuditItem(
                relative_path=_display_path(temp, root),
                segment_id=None,
                state=AuditState.STALE_MANIFEST_TEMP,
                detail="manifest temp file exists",
            )
        )

    claimed_paths: set[str] = set()
    for record in manifest.records:
        claimed_paths.add(record.relative_path)
        final = root / PurePosixPath(record.relative_path)
        if not final.exists():
            items.append(
                StorageAuditItem(
                    relative_path=record.relative_path,
                    segment_id=record.segment_id,
                    state=AuditState.MISSING,
                    detail="manifest references missing sealed file",
                )
            )
            continue

        detail = _verify_record_file(final, record)
        state = AuditState.VALID if detail is None else AuditState.MISMATCH
        items.append(
            StorageAuditItem(
                relative_path=record.relative_path,
                segment_id=record.segment_id,
                state=state,
                detail="manifest and sealed file match" if detail is None else detail,
            )
        )

    if root.exists():
        for final in sorted(root.rglob("*.raw")):
            relative = final.relative_to(root).as_posix()
            if relative in claimed_paths:
                continue
            scan = scan_raw_log(final, final.stem)
            state = (
                AuditState.ORPHAN_COMPLETE
                if scan.tail_state is TailState.CLEAN
                else AuditState.CORRUPT
            )
            items.append(
                StorageAuditItem(
                    relative_path=relative,
                    segment_id=final.stem,
                    state=state,
                    detail=(
                        "clean sealed file has no manifest entry"
                        if state is AuditState.ORPHAN_COMPLETE
                        else f"orphan sealed file is {scan.tail_state.value}"
                    ),
                )
            )

        for open_file in sorted(root.rglob("*.raw.open")):
            relative = open_file.relative_to(root).as_posix()
            segment_id = open_file.name.removesuffix(".raw.open")
            scan = scan_raw_log(open_file, segment_id)
            if scan.tail_state is TailState.CLEAN:
                state = AuditState.OPEN_RECOVERABLE
                detail = "open segment is clean"
            elif scan.tail_state is TailState.INCOMPLETE:
                state = AuditState.OPEN_INCOMPLETE_RECOVERABLE
                detail = "open segment has incomplete tail"
            else:
                state = AuditState.CORRUPT
                detail = "open segment is corrupt"
            items.append(
                StorageAuditItem(
                    relative_path=relative,
                    segment_id=segment_id,
                    state=state,
                    detail=detail,
                )
            )

    return StorageAuditReport(
        items=tuple(
            sorted(
                items,
                key=lambda item: (
                    item.relative_path,
                    item.segment_id or "",
                    item.state.value,
                ),
            )
        )
    )


def _verify_record_file(
    path: Path,
    record: SegmentManifestRecord,
) -> str | None:
    if path.stat().st_size != record.byte_length:
        return "sealed file byte length does not match manifest"
    if _sha256_file(path) != record.sha256:
        return "sealed file sha256 does not match manifest"
    scan = scan_raw_log(path, record.segment_id)
    if scan.tail_state is not TailState.CLEAN:
        return f"sealed file raw log is {scan.tail_state.value}"
    if scan.valid_frames != record.frame_count:
        return "sealed file frame count does not match manifest"
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_to_root(path: Path, root: Path) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ManifestError("sealed segment must be inside storage_root") from exc
    value = relative.as_posix()
    _validate_relative_path(value)
    return value


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _validate_relative_path(value: str) -> None:
    if not value.strip() or "\\" in value:
        raise ManifestError("relative_path must be a non-empty POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) == ".":
        raise ManifestError("relative_path must stay inside storage root")


def _validate_optional_range(
    minimum: int | None,
    maximum: int | None,
    field: str,
) -> None:
    if minimum is None and maximum is None:
        return
    if minimum is None or maximum is None:
        raise ManifestError(f"{field} min/max must both be null or present")
    _require_nonnegative_int(minimum, f"min_{field}")
    _require_nonnegative_int(maximum, f"max_{field}")
    if minimum > maximum:
        raise ManifestError(f"min_{field} must not exceed max_{field}")


def _require_nonnegative_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ManifestError(f"{field} must be a non-negative integer")


def _require_exact_fields(
    raw: Mapping[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    unknown = set(raw) - expected
    missing = expected - set(raw)
    if unknown:
        raise ManifestError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        raise ManifestError(f"{label} is missing fields: {', '.join(sorted(missing))}")


def _mapping_int(raw: Mapping[str, object], field: str) -> int:
    value = raw[field]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestError(f"{field} must be an integer")
    return value


def _mapping_optional_int(
    raw: Mapping[str, object],
    field: str,
) -> int | None:
    value = raw[field]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestError(f"{field} must be null or an integer")
    return value


def _mapping_str(raw: Mapping[str, object], field: str) -> str:
    value = raw[field]
    if not isinstance(value, str):
        raise ManifestError(f"{field} must be a string")
    return value


def _mapping_optional_str(
    raw: Mapping[str, object],
    field: str,
) -> str | None:
    value = raw[field]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ManifestError(f"{field} must be null or a string")
    return value


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fault(hook: FaultHook | None, phase: str) -> None:
    if hook is not None:
        hook(phase)
