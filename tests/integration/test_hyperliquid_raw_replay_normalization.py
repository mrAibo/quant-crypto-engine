from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptobot.adapters.hyperliquid.normalize import (
    BookNormalizationStatus,
    BookParseErrorCode,
    normalize_book_frame,
    serialize_normalized_book_event,
)
from cryptobot.data.events import BBO, L2Snapshot
from cryptobot.data.instruments import load_instrument_registry
from cryptobot.data.rawlog import RawFrameMetadata, RawLog, iter_raw_frames


def _metadata(seq: int, channel: str) -> RawFrameMetadata:
    return RawFrameMetadata(
        schema_version=1,
        source_id="hyperliquid-mainnet-public",
        recv_wall_ns=1_790_193_802_000_000_000 + seq,
        recv_mono_ns=10_000 + seq,
        host_id="host",
        boot_id="boot",
        connection_id="conn",
        ingest_seq=seq,
        channel_hint=channel,
        capture_flags=("LIVE_CAPTURE", "WS_PUBLIC"),
    )


def test_qcr1_replay_normalizes_deterministically_with_exact_provenance(
    tmp_path: Path,
) -> None:
    segment_id = "replay-segment"
    path = tmp_path / f"{segment_id}.raw.open"
    payloads = [
        json.dumps(
            {
                "channel": "l2Book",
                "data": {
                    "coin": "BTC",
                    "time": 1_790_193_801_460,
                    "levels": [
                        [{"px": "100", "sz": "1.5", "n": 2}],
                        [{"px": "101", "sz": "2.5", "n": 3}],
                    ],
                },
            },
            separators=(",", ":"),
        ).encode(),
        json.dumps(
            {
                "channel": "bbo",
                "data": {
                    "coin": "ETH",
                    "time": 1_790_193_801_866,
                    "bbo": [
                        {"px": "2500", "sz": "4", "n": 1},
                        {"px": "2501", "sz": "5", "n": 2},
                    ],
                },
            },
            separators=(",", ":"),
        ).encode(),
        b'{"channel":"trades","data":[]}',
        b'{"channel":"bbo","data":{"coin":"BTC","time":1,"bbo":[null]}}',
    ]

    log = RawLog.open(path, segment_id)
    for seq, payload in enumerate(payloads, start=1):
        channel = json.loads(payload).get("channel")
        assert isinstance(channel, str)
        log.append(_metadata(seq, channel), payload)
    log.sync()
    log.close()

    frames = list(iter_raw_frames(path, segment_id))
    registry = load_instrument_registry("config/instruments.yaml")
    results = [normalize_book_frame(frame, registry) for frame in frames]
    replayed = [normalize_book_frame(frame, registry) for frame in frames]

    assert results[0].status is BookNormalizationStatus.EVENT
    assert isinstance(results[0].event, L2Snapshot)
    assert results[1].status is BookNormalizationStatus.EVENT
    assert isinstance(results[1].event, BBO)
    assert results[2].status is BookNormalizationStatus.NOT_APPLICABLE
    assert results[3].status is BookNormalizationStatus.ERROR
    assert results[3].error is not None
    assert results[3].error.code is BookParseErrorCode.INVALID_BBO_SHAPE

    for frame, first, second in zip(frames, results, replayed, strict=True):
        assert frame.ref.payload_sha256 == hashlib.sha256(frame.payload).hexdigest()
        if first.event is not None and second.event is not None:
            assert first.event.envelope.raw_segment_id == segment_id
            assert first.event.envelope.raw_offset == frame.ref.offset
            assert first.event.envelope.raw_sha256 == frame.ref.payload_sha256
            assert serialize_normalized_book_event(first.event) == serialize_normalized_book_event(
                second.event
            )

    assert results[0].event is not None
    assert results[1].event is not None
    assert results[0].event.envelope.event_id != results[1].event.envelope.event_id
    assert results[0].event.envelope.raw_offset != results[1].event.envelope.raw_offset
