from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from cryptobot.data.manifest import (
    AuditState,
    ManifestError,
    audit_storage,
    recover_open_segment,
    seal_segment,
)
from cryptobot.data.rawlog import RawFrameMetadata, RawLog


class InjectedCrash(RuntimeError):
    pass


def _metadata(seq: int) -> RawFrameMetadata:
    return RawFrameMetadata(
        schema_version=1,
        source_id="source",
        recv_wall_ns=1_000 + seq,
        recv_mono_ns=2_000 + seq,
        host_id="host",
        boot_id="boot",
        connection_id="conn",
        ingest_seq=seq,
        channel_hint=None,
        capture_flags=(),
    )


def _make_open(root: Path, segment_id: str = "segment-1") -> tuple[Path, Path, Path]:
    segments = root / "segments"
    open_path = segments / f"{segment_id}.raw.open"
    final_path = segments / f"{segment_id}.raw"
    manifest_path = root / "manifest.json"
    with RawLog.open(open_path, segment_id) as log:
        log.append(_metadata(1), b"first")
        log.append(_metadata(2), b"second")
        log.sync()
    return open_path, final_path, manifest_path


def _crash_at(phase: str) -> Callable[[str], None]:
    def hook(current: str) -> None:
        if current == phase:
            raise InjectedCrash(phase)

    return hook


@pytest.mark.parametrize(
    ("phase", "expected_state"),
    [
        ("before_segment_fsync", AuditState.OPEN_RECOVERABLE),
        ("after_segment_fsync", AuditState.OPEN_RECOVERABLE),
        ("after_segment_rename", AuditState.ORPHAN_COMPLETE),
        ("after_segment_dir_fsync", AuditState.ORPHAN_COMPLETE),
        ("before_manifest_temp_write", AuditState.ORPHAN_COMPLETE),
        ("after_manifest_temp_write", AuditState.ORPHAN_COMPLETE),
        ("after_manifest_temp_fsync", AuditState.ORPHAN_COMPLETE),
        ("after_manifest_replace", AuditState.VALID),
        ("after_manifest_dir_fsync", AuditState.VALID),
    ],
)
def test_crash_points_have_deterministic_recovery_classification(
    tmp_path: Path,
    phase: str,
    expected_state: AuditState,
) -> None:
    root = tmp_path / phase
    open_path, final_path, manifest_path = _make_open(root)

    with pytest.raises(InjectedCrash, match=phase):
        seal_segment(
            open_path=open_path,
            final_path=final_path,
            storage_root=root,
            manifest_path=manifest_path,
            segment_id="segment-1",
            sealed_wall_ns=5_000,
            fault_hook=_crash_at(phase),
        )

    audit = audit_storage(root, manifest_path)
    states = [item.state for item in audit.items]

    assert expected_state in states
    if phase in {"after_manifest_temp_write", "after_manifest_temp_fsync"}:
        assert AuditState.STALE_MANIFEST_TEMP in states


def test_orphan_complete_is_preserved_not_deleted(tmp_path: Path) -> None:
    root = tmp_path / "orphan"
    _, final_path, manifest_path = _make_open(root)
    open_path = root / "segments" / "segment-1.raw.open"
    open_path.replace(final_path)

    audit = audit_storage(root, manifest_path)

    item = next(item for item in audit.items if item.segment_id == "segment-1")
    assert item.state is AuditState.ORPHAN_COMPLETE
    assert final_path.exists()


def test_incomplete_open_segment_is_classified_and_recoverable(tmp_path: Path) -> None:
    root = tmp_path / "incomplete"
    open_path, _, manifest_path = _make_open(root)
    with open_path.open("r+b") as file:
        file.truncate(open_path.stat().st_size - 10)

    audit_before = audit_storage(root, manifest_path)
    item_before = next(item for item in audit_before.items if item.segment_id == "segment-1")
    assert item_before.state is AuditState.OPEN_INCOMPLETE_RECOVERABLE

    recovered = recover_open_segment(open_path, "segment-1")
    audit_after = audit_storage(root, manifest_path)

    assert recovered.state is AuditState.OPEN_RECOVERABLE
    item_after = next(item for item in audit_after.items if item.segment_id == "segment-1")
    assert item_after.state is AuditState.OPEN_RECOVERABLE


def test_corrupt_open_segment_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "corrupt"
    open_path, _, manifest_path = _make_open(root)

    with open_path.open("r+b") as file:
        file.seek(-1, 2)
        original = file.read(1)
        file.seek(-1, 2)
        file.write(bytes([original[0] ^ 0xFF]))

    audit = audit_storage(root, manifest_path)
    item = next(item for item in audit.items if item.segment_id == "segment-1")

    assert item.state is AuditState.CORRUPT
    with pytest.raises(ManifestError, match="cannot be auto-recovered"):
        recover_open_segment(open_path, "segment-1")


def test_manifest_referenced_file_missing_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "missing"
    open_path, final_path, manifest_path = _make_open(root)
    seal_segment(
        open_path=open_path,
        final_path=final_path,
        storage_root=root,
        manifest_path=manifest_path,
        segment_id="segment-1",
        sealed_wall_ns=5_000,
    )
    final_path.unlink()

    audit = audit_storage(root, manifest_path)

    assert any(item.state is AuditState.MISSING for item in audit.items)


def test_stale_manifest_temp_is_reported_without_deletion(tmp_path: Path) -> None:
    root = tmp_path / "stale-temp"
    root.mkdir()
    manifest_path = root / "manifest.json"
    temp = root / "manifest.json.tmp"
    temp.write_bytes(b'{"partial":')

    audit = audit_storage(root, manifest_path)

    assert any(item.state is AuditState.STALE_MANIFEST_TEMP for item in audit.items)
    assert temp.exists()
