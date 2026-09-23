from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptobot.adapters.hyperliquid.trades import (
    TradeNormalizationStatus,
    TradeParseErrorCode,
    normalize_trade_frame,
    serialize_normalized_trades,
)
from cryptobot.data.instruments import load_instrument_registry
from cryptobot.data.rawlog import RawFrameMetadata, RawLog, iter_raw_frames


def _metadata(seq: int, channel: str) -> RawFrameMetadata:
    return RawFrameMetadata(
        schema_version=1,
        source_id="hyperliquid-mainnet-public",
        recv_wall_ns=1_790_195_471_000_000_000 + seq,
        recv_mono_ns=20_000 + seq,
        host_id="host",
        boot_id="boot",
        connection_id="conn",
        ingest_seq=seq,
        channel_hint=channel,
        capture_flags=("LIVE_CAPTURE", "WS_PUBLIC"),
    )


def _trade(tid: int, *, coin: str = "BTC") -> dict[str, object]:
    return {
        "coin": coin,
        "side": "B" if tid % 2 else "A",
        "px": "65100.0",
        "sz": "0.01",
        "hash": "0x" + format(tid, "064x"),
        "time": 1_790_195_471_030,
        "tid": tid,
        "users": ["0x" + "1" * 40, "0x" + "2" * 40],
    }


def test_qcr1_trade_replay_preserves_multi_event_provenance_and_determinism(
    tmp_path: Path,
) -> None:
    segment_id = "trade-replay-segment"
    path = tmp_path / f"{segment_id}.raw.open"
    payloads = [
        json.dumps(
            {"channel": "trades", "data": [_trade(101), _trade(102)]},
            separators=(",", ":"),
        ).encode(),
        json.dumps(
            {"channel": "trades", "data": [_trade(201, coin="ETH")]},
            separators=(",", ":"),
        ).encode(),
        b'{"channel":"bbo","data":{}}',
        b'{"channel":"trades","data":[{"coin":"BTC"}]}',
    ]

    log = RawLog.open(path, segment_id)
    for seq, payload in enumerate(payloads, start=1):
        decoded = json.loads(payload)
        channel = decoded.get("channel")
        assert isinstance(channel, str)
        log.append(_metadata(seq, channel), payload)
    log.sync()
    log.close()

    frames = list(iter_raw_frames(path, segment_id))
    registry = load_instrument_registry("config/instruments.yaml")
    results = [normalize_trade_frame(frame, registry) for frame in frames]
    repeated = [normalize_trade_frame(frame, registry) for frame in frames]

    assert results[0].status is TradeNormalizationStatus.EVENTS
    assert [event.trade_id for event in results[0].events] == [
        "1790195471030:BTC:101",
        "1790195471030:BTC:102",
    ]
    assert results[1].status is TradeNormalizationStatus.EVENTS
    assert results[1].events[0].envelope.instrument_id == "hyperliquid.mainnet.perpetual.eth"
    assert results[2].status is TradeNormalizationStatus.NOT_APPLICABLE
    assert results[3].status is TradeNormalizationStatus.ERROR
    assert results[3].error is not None
    assert results[3].error.code is TradeParseErrorCode.INVALID_TRADE_OBJECT

    for frame, first, second in zip(frames, results, repeated, strict=True):
        assert frame.ref.payload_sha256 == hashlib.sha256(frame.payload).hexdigest()
        if first.status is TradeNormalizationStatus.EVENTS:
            assert serialize_normalized_trades(first.events) == serialize_normalized_trades(
                second.events
            )
            for event in first.events:
                assert event.envelope.raw_segment_id == segment_id
                assert event.envelope.raw_offset == frame.ref.offset
                assert event.envelope.raw_sha256 == frame.ref.payload_sha256

    ids = [event.envelope.event_id for result in results for event in result.events]
    assert len(ids) == len(set(ids))


def test_qcr1_reconnect_duplicate_identity_remains_auditable(
    tmp_path: Path,
) -> None:
    segment_id = "duplicate-replay-segment"
    path = tmp_path / f"{segment_id}.raw.open"
    payload = json.dumps(
        {"channel": "trades", "data": [_trade(555)]},
        separators=(",", ":"),
    ).encode()

    log = RawLog.open(path, segment_id)
    log.append(_metadata(1, "trades"), payload)
    log.append(_metadata(2, "trades"), payload)
    log.sync()
    log.close()

    frames = list(iter_raw_frames(path, segment_id))
    registry = load_instrument_registry("config/instruments.yaml")
    first = normalize_trade_frame(frames[0], registry)
    second = normalize_trade_frame(frames[1], registry)

    assert first.events[0].trade_id == second.events[0].trade_id
    assert first.events[0].envelope.event_id != second.events[0].envelope.event_id
    assert first.events[0].envelope.raw_offset != second.events[0].envelope.raw_offset
