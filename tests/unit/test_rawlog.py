from __future__ import annotations

from pathlib import Path

import pytest

from cryptobot.data.rawlog import (
    RawFrameMetadata,
    RawLog,
    RawLogClosedError,
    RawLogCorruptionError,
    RawLogError,
    TailState,
    encode_raw_metadata,
    iter_raw_frames,
    scan_raw_log,
)


def _metadata(seq: int = 1) -> RawFrameMetadata:
    return RawFrameMetadata(
        schema_version=1,
        source_id="hyperliquid-mainnet-public",
        recv_wall_ns=1_000_000 + seq,
        recv_mono_ns=500_000 + seq,
        host_id="recorder-a",
        boot_id="boot-a",
        connection_id="conn-a",
        ingest_seq=seq,
        channel_hint="trades",
        capture_flags=("LIVE",),
    )


def test_one_frame_roundtrip_preserves_payload_exactly(tmp_path: Path) -> None:
    path = tmp_path / "segment.raw"
    payload = b'{"coin":"BTC","px":"123.4500"}'

    log = RawLog.open(path, "segment-1")
    ref = log.append(_metadata(), payload)
    assert log.durable_length == 0
    log.sync()
    log.close()

    frames = list(iter_raw_frames(path, "segment-1"))

    assert len(frames) == 1
    assert frames[0].payload == payload
    assert frames[0].metadata == _metadata()
    assert frames[0].ref == ref
    assert scan_raw_log(path, "segment-1").tail_state is TailState.CLEAN


def test_multiple_frames_have_exact_append_offsets(tmp_path: Path) -> None:
    path = tmp_path / "segment.raw"
    with RawLog.open(path, "segment-1") as log:
        first = log.append(_metadata(1), b"one")
        second = log.append(_metadata(2), b"two")
        third = log.append(_metadata(3), b"three")
        log.sync()

    assert first.offset == 0
    assert second.offset == first.frame_length
    assert third.offset == first.frame_length + second.frame_length
    assert [frame.payload for frame in iter_raw_frames(path, "segment-1")] == [
        b"one",
        b"two",
        b"three",
    ]


def test_metadata_encoding_is_deterministic() -> None:
    first = encode_raw_metadata(_metadata())
    second = encode_raw_metadata(_metadata())

    assert first == second
    assert b' "source_id"' not in first


def test_empty_payload_is_supported(tmp_path: Path) -> None:
    path = tmp_path / "segment.raw"
    with RawLog.open(path, "segment-1") as log:
        ref = log.append(_metadata(), b"")
        log.sync()

    frame = next(iter_raw_frames(path, "segment-1"))

    assert ref.payload_length == 0
    assert frame.payload == b""


def test_large_payload_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "segment.raw"
    payload = b"x" * (1024 * 1024)

    with RawLog.open(path, "segment-1") as log:
        log.append(_metadata(), payload)
        log.sync()

    assert next(iter_raw_frames(path, "segment-1")).payload == payload


def test_checksum_corruption_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "segment.raw"
    with RawLog.open(path, "segment-1") as log:
        ref = log.append(_metadata(), b"payload")
        log.sync()

    with path.open("r+b") as file:
        file.seek(ref.offset + ref.frame_length - 1)
        byte = file.read(1)
        file.seek(ref.offset + ref.frame_length - 1)
        file.write(bytes([byte[0] ^ 0xFF]))

    scan = scan_raw_log(path, "segment-1")

    assert scan.tail_state is TailState.CORRUPT
    assert scan.first_bad_offset == 0
    with pytest.raises(RawLogCorruptionError, match="corrupt"):
        list(iter_raw_frames(path, "segment-1"))


def test_invalid_magic_is_corrupt_not_incomplete(tmp_path: Path) -> None:
    path = tmp_path / "segment.raw"
    path.write_bytes(b"BAD!" + b"\x00" * 12)

    scan = scan_raw_log(path, "segment-1")

    assert scan.tail_state is TailState.CORRUPT
    assert scan.first_bad_offset == 0


def test_append_after_close_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "segment.raw"
    log = RawLog.open(path, "segment-1")
    log.close()

    with pytest.raises(RawLogClosedError, match="closed"):
        log.append(_metadata(), b"payload")


def test_payload_must_be_bytes(tmp_path: Path) -> None:
    path = tmp_path / "segment.raw"
    with RawLog.open(path, "segment-1") as log:
        with pytest.raises(RawLogError, match="payload must be bytes"):
            log.append(_metadata(), bytearray(b"payload"))  # type: ignore[arg-type]


def test_sync_calls_fsync_and_advances_durable_length(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "segment.raw"
    calls: list[int] = []

    def fake_fsync(fd: int) -> None:
        calls.append(fd)

    monkeypatch.setattr("cryptobot.data.rawlog.os.fsync", fake_fsync)

    with RawLog.open(path, "segment-1") as log:
        ref = log.append(_metadata(), b"payload")
        assert log.durable_length == 0
        log.sync()
        assert log.durable_length == ref.frame_length

    assert len(calls) == 1


def test_open_refuses_unclean_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "segment.raw"
    path.write_bytes(b"partial")

    with pytest.raises(RawLogCorruptionError, match="recover first"):
        RawLog.open(path, "segment-1")


def test_metadata_flags_must_be_sorted_and_unique() -> None:
    with pytest.raises(RawLogError, match="sorted"):
        RawFrameMetadata(
            schema_version=1,
            source_id="source",
            recv_wall_ns=1,
            recv_mono_ns=1,
            host_id="host",
            boot_id="boot",
            connection_id="conn",
            ingest_seq=1,
            channel_hint=None,
            capture_flags=("Z", "A"),
        )
