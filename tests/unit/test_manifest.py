from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cryptobot.data.manifest import (
    AuditState,
    ManifestError,
    PublicationStatus,
    SegmentManifest,
    SegmentManifestRecord,
    audit_storage,
    commit_manifest,
    derive_segment_stats,
    encode_manifest,
    load_manifest,
    seal_segment,
)
from cryptobot.data.rawlog import RawFrameMetadata, RawLog


def _metadata(seq: int, source_id: str = "source-a") -> RawFrameMetadata:
    return RawFrameMetadata(
        schema_version=1,
        source_id=source_id,
        recv_wall_ns=1_000 + seq,
        recv_mono_ns=2_000 + seq,
        host_id="host-a",
        boot_id="boot-a",
        connection_id="conn-a",
        ingest_seq=seq,
        channel_hint=None,
        capture_flags=(),
    )


def _write_open_segment(
    root: Path,
    segment_id: str = "segment-1",
) -> tuple[Path, Path]:
    segments = root / "segments"
    open_path = segments / f"{segment_id}.raw.open"
    final_path = segments / f"{segment_id}.raw"
    with RawLog.open(open_path, segment_id) as log:
        log.append(_metadata(3, "source-b"), b"three")
        log.append(_metadata(1, "source-a"), b"one")
        log.append(_metadata(2, "source-a"), b"two")
        log.sync()
    return open_path, final_path


def _record(**overrides: object) -> SegmentManifestRecord:
    values: dict[str, object] = {
        "record_version": 1,
        "segment_id": "segment-1",
        "relative_path": "segments/segment-1.raw",
        "byte_length": 100,
        "sha256": "a" * 64,
        "raw_frame_version": 1,
        "frame_count": 3,
        "min_recv_wall_ns": 1001,
        "max_recv_wall_ns": 1003,
        "min_ingest_seq": 1,
        "max_ingest_seq": 3,
        "source_ids": ("source-a", "source-b"),
        "sealed_wall_ns": 5_000,
        "recorder_version": "test",
        "event_schema_version": 1,
        "publication_status": PublicationStatus.PUBLISHED,
    }
    values.update(overrides)
    return SegmentManifestRecord(**values)  # type: ignore[arg-type]


def test_manifest_encoding_is_canonical_and_record_order_is_deterministic() -> None:
    second = _record(
        segment_id="segment-2",
        relative_path="segments/segment-2.raw",
        sha256="b" * 64,
    )
    first = _record()
    manifest = SegmentManifest(schema_version=1, records=(second, first))

    encoded_once = encode_manifest(manifest)
    encoded_twice = encode_manifest(manifest)

    assert encoded_once == encoded_twice
    assert manifest.records[0].segment_id == "segment-1"
    assert encoded_once.endswith(b"\n")


def test_duplicate_segment_id_is_rejected() -> None:
    with pytest.raises(ManifestError, match="duplicate segment_id"):
        SegmentManifest(schema_version=1, records=(_record(), _record()))


@pytest.mark.parametrize(
    "relative_path",
    ["/absolute/segment.raw", "../segment.raw", "segments/../segment.raw", ""],
)
def test_manifest_record_rejects_unsafe_relative_path(relative_path: str) -> None:
    with pytest.raises(ManifestError, match="relative_path"):
        _record(relative_path=relative_path)


def test_derive_segment_stats_reads_only_raw_metadata(tmp_path: Path) -> None:
    open_path, _ = _write_open_segment(tmp_path)

    stats = derive_segment_stats(open_path, "segment-1")

    assert stats.frame_count == 3
    assert stats.min_recv_wall_ns == 1001
    assert stats.max_recv_wall_ns == 1003
    assert stats.min_ingest_seq == 1
    assert stats.max_ingest_seq == 3
    assert stats.source_ids == ("source-a", "source-b")


def test_seal_segment_publishes_file_and_manifest(tmp_path: Path) -> None:
    open_path, final_path = _write_open_segment(tmp_path)
    manifest_path = tmp_path / "manifests" / "raw-manifest.json"

    record = seal_segment(
        open_path=open_path,
        final_path=final_path,
        storage_root=tmp_path,
        manifest_path=manifest_path,
        segment_id="segment-1",
        sealed_wall_ns=9_000,
        recorder_version="recorder-test",
        event_schema_version=1,
    )

    assert not open_path.exists()
    assert final_path.exists()
    assert record.relative_path == "segments/segment-1.raw"
    assert record.byte_length == final_path.stat().st_size
    assert record.sha256 == hashlib.sha256(final_path.read_bytes()).hexdigest()
    assert record.frame_count == 3
    assert record.source_ids == ("source-a", "source-b")

    loaded = load_manifest(manifest_path)
    assert loaded.records == (record,)

    audit = audit_storage(tmp_path, manifest_path)
    assert audit.clean
    assert audit.items[0].state is AuditState.VALID


def test_manifest_roundtrip_is_equal(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    manifest = SegmentManifest(schema_version=1, records=(_record(),))

    commit_manifest(path, manifest)

    assert load_manifest(path) == manifest


def test_seal_rejects_unclean_raw_log(tmp_path: Path) -> None:
    open_path, final_path = _write_open_segment(tmp_path)
    with open_path.open("ab") as file:
        file.write(b"partial")

    with pytest.raises(ManifestError, match="must be CLEAN"):
        seal_segment(
            open_path=open_path,
            final_path=final_path,
            storage_root=tmp_path,
            manifest_path=tmp_path / "manifest.json",
            segment_id="segment-1",
            sealed_wall_ns=9_000,
        )


def test_audit_detects_missing_manifest_referenced_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    commit_manifest(
        manifest_path,
        SegmentManifest(schema_version=1, records=(_record(),)),
    )

    audit = audit_storage(tmp_path, manifest_path)

    assert any(item.state is AuditState.MISSING for item in audit.items)
    assert not audit.clean


def test_audit_detects_checksum_or_size_mismatch(tmp_path: Path) -> None:
    open_path, final_path = _write_open_segment(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    seal_segment(
        open_path=open_path,
        final_path=final_path,
        storage_root=tmp_path,
        manifest_path=manifest_path,
        segment_id="segment-1",
        sealed_wall_ns=9_000,
    )

    with final_path.open("ab") as file:
        file.write(b"x")

    audit = audit_storage(tmp_path, manifest_path)

    assert any(item.state is AuditState.MISMATCH for item in audit.items)


def test_audit_detects_manifest_metadata_mismatch_even_when_file_hash_matches(
    tmp_path: Path,
) -> None:
    open_path, final_path = _write_open_segment(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    record = seal_segment(
        open_path=open_path,
        final_path=final_path,
        storage_root=tmp_path,
        manifest_path=manifest_path,
        segment_id="segment-1",
        sealed_wall_ns=9_000,
    )
    altered = SegmentManifestRecord(
        **{
            **record.as_dict(),
            "source_ids": ("wrong-source",),
            "publication_status": PublicationStatus.PUBLISHED,
        }
    )  # type: ignore[arg-type]
    commit_manifest(
        manifest_path,
        SegmentManifest(schema_version=1, records=(altered,)),
    )

    audit = audit_storage(tmp_path, manifest_path)

    mismatch = next(item for item in audit.items if item.segment_id == "segment-1")
    assert mismatch.state is AuditState.MISMATCH
    assert "derived metadata" in mismatch.detail
