from __future__ import annotations

from pathlib import Path

import pytest

from cryptobot.data.rawlog import (
    CHECKSUM_SIZE,
    PREFIX,
    RawFrameMetadata,
    RawLog,
    RawLogCorruptionError,
    TailState,
    encode_raw_metadata,
    scan_raw_log,
    truncate_incomplete_tail,
)


def _metadata(seq: int) -> RawFrameMetadata:
    return RawFrameMetadata(
        schema_version=1,
        source_id="source",
        recv_wall_ns=1000 + seq,
        recv_mono_ns=2000 + seq,
        host_id="host",
        boot_id="boot",
        connection_id="conn",
        ingest_seq=seq,
        channel_hint=None,
        capture_flags=(),
    )


@pytest.mark.parametrize("cut_region", ["magic", "lengths", "metadata", "payload", "checksum"])
def test_truncated_final_frame_recovers_only_valid_prefix(
    tmp_path: Path,
    cut_region: str,
) -> None:
    path = tmp_path / f"{cut_region}.raw"
    second_payload = b"second-payload"

    with RawLog.open(path, "segment-1") as log:
        first = log.append(_metadata(1), b"first")
        second = log.append(_metadata(2), second_payload)
        log.sync()

    metadata_length = len(encode_raw_metadata(_metadata(2)))
    relative_cut = {
        "magic": 2,
        "lengths": PREFIX.size - 1,
        "metadata": PREFIX.size + max(1, metadata_length // 2),
        "payload": PREFIX.size + metadata_length + max(1, len(second_payload) // 2),
        "checksum": second.frame_length - max(1, CHECKSUM_SIZE // 2),
    }[cut_region]

    with path.open("r+b") as file:
        file.truncate(second.offset + relative_cut)

    scan = scan_raw_log(path, "segment-1")

    assert scan.tail_state is TailState.INCOMPLETE
    assert scan.valid_frames == 1
    assert scan.valid_bytes == first.frame_length
    assert scan.first_bad_offset == second.offset

    truncated_to = truncate_incomplete_tail(path, scan)
    recovered = scan_raw_log(path, "segment-1")

    assert truncated_to == first.frame_length
    assert recovered.tail_state is TailState.CLEAN
    assert recovered.valid_frames == 1
    assert recovered.valid_bytes == first.frame_length


def test_middle_frame_corruption_is_never_auto_truncated(tmp_path: Path) -> None:
    path = tmp_path / "middle-corrupt.raw"

    with RawLog.open(path, "segment-1") as log:
        first = log.append(_metadata(1), b"first")
        second = log.append(_metadata(2), b"second")
        log.append(_metadata(3), b"third")
        log.sync()

    with path.open("r+b") as file:
        file.seek(second.offset + second.frame_length - 1)
        current = file.read(1)
        file.seek(second.offset + second.frame_length - 1)
        file.write(bytes([current[0] ^ 0x01]))

    scan = scan_raw_log(path, "segment-1")

    assert scan.tail_state is TailState.CORRUPT
    assert scan.valid_frames == 1
    assert scan.valid_bytes == first.frame_length
    assert scan.first_bad_offset == second.offset
    with pytest.raises(RawLogCorruptionError, match="only for an incomplete tail"):
        truncate_incomplete_tail(path, scan)


def test_garbage_after_valid_frame_is_corruption(tmp_path: Path) -> None:
    path = tmp_path / "garbage.raw"

    with RawLog.open(path, "segment-1") as log:
        first = log.append(_metadata(1), b"first")
        log.sync()

    with path.open("ab") as file:
        file.write(b"GARBAGE-GARBAGE!")

    scan = scan_raw_log(path, "segment-1")

    assert scan.tail_state is TailState.CORRUPT
    assert scan.valid_frames == 1
    assert scan.valid_bytes == first.frame_length
    assert scan.first_bad_offset == first.frame_length
