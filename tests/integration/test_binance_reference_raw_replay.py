from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptobot.adapters.binance.normalize import (
    BinanceReferenceNormalizationStatus,
    normalize_binance_reference_frame,
    serialize_binance_reference_event,
)
from cryptobot.data.events import ReferenceBBO, ReferenceTrade
from cryptobot.data.instruments import load_instrument_registry
from cryptobot.data.rawlog import RawFrameMetadata, RawLog, iter_raw_frames


def _meta(seq: int, hint: str) -> RawFrameMetadata:
    return RawFrameMetadata(
        schema_version=1,
        source_id="binance-usdm-reference-public",
        recv_wall_ns=1_790_196_000_500_000_000 + seq,
        recv_mono_ns=40_000 + seq,
        host_id="host",
        boot_id="boot",
        connection_id="ref-conn",
        ingest_seq=seq,
        channel_hint=hint,
        capture_flags=("BINANCE_PUBLIC", "LIVE_CAPTURE", "WS_PUBLIC"),
    )


def _bbo(symbol: str) -> bytes:
    return json.dumps(
        {
            "stream": f"{symbol.lower()}@bookTicker",
            "data": {
                "e": "bookTicker",
                "u": 100,
                "E": 1790196000100,
                "T": 1790196000099,
                "s": symbol,
                "ps": symbol,
                "b": "100",
                "B": "1",
                "a": "101",
                "A": "2",
                "st": 1,
            },
        },
        separators=(",", ":"),
    ).encode()


def _trade(symbol: str) -> bytes:
    return json.dumps(
        {
            "stream": f"{symbol.lower()}@aggTrade",
            "data": {
                "e": "aggTrade",
                "E": 1790196000200,
                "s": symbol,
                "a": 77,
                "p": "100.5",
                "q": "0.5",
                "nq": "0.5",
                "f": 10,
                "l": 12,
                "T": 1790196000198,
                "m": False,
                "st": 1,
            },
        },
        separators=(",", ":"),
    ).encode()


def test_qcr1_reference_replay_is_deterministic_and_preserves_provenance(tmp_path: Path) -> None:
    segment_id = "binance-reference-replay"
    path = tmp_path / f"{segment_id}.raw.open"
    payloads = [
        _bbo("BTCUSDT"),
        _trade("BTCUSDT"),
        _bbo("ETHUSDT"),
        _trade("ETHUSDT"),
        b'{"result":null,"id":"task013-public"}',
    ]

    log = RawLog.open(path, segment_id)
    for seq, payload in enumerate(payloads, start=1):
        log.append(_meta(seq, "reference"), payload)
    log.sync()
    log.close()

    frames = list(iter_raw_frames(path, segment_id))
    registry = load_instrument_registry("config/instruments.yaml")
    results = [normalize_binance_reference_frame(frame, registry) for frame in frames]
    repeated = [normalize_binance_reference_frame(frame, registry) for frame in frames]

    assert isinstance(results[0].event, ReferenceBBO)
    assert isinstance(results[1].event, ReferenceTrade)
    assert isinstance(results[2].event, ReferenceBBO)
    assert isinstance(results[3].event, ReferenceTrade)
    assert results[4].status is BinanceReferenceNormalizationStatus.NOT_APPLICABLE

    for frame, first, second in zip(frames, results, repeated, strict=True):
        assert frame.ref.payload_sha256 == hashlib.sha256(frame.payload).hexdigest()
        if first.event is not None and second.event is not None:
            assert first.event.envelope.raw_segment_id == segment_id
            assert first.event.envelope.raw_offset == frame.ref.offset
            assert first.event.envelope.raw_sha256 == frame.ref.payload_sha256
            assert serialize_binance_reference_event(
                first.event
            ) == serialize_binance_reference_event(second.event)

    event_ids = [result.event.envelope.event_id for result in results if result.event is not None]
    assert len(event_ids) == len(set(event_ids))
