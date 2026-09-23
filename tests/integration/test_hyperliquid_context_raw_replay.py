from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptobot.adapters.hyperliquid.context import (
    ContextNormalizationStatus,
    ContextParseErrorCode,
    normalize_context_frame,
    serialize_normalized_context,
)
from cryptobot.data.events import FundingRateObservation, MarkPrice, OraclePrice
from cryptobot.data.instruments import load_instrument_registry
from cryptobot.data.rawlog import RawFrameMetadata, RawLog, iter_raw_frames


def _metadata(seq: int, channel: str) -> RawFrameMetadata:
    return RawFrameMetadata(
        schema_version=1,
        source_id="hyperliquid-mainnet-public",
        recv_wall_ns=1_790_196_115_000_000_000 + seq,
        recv_mono_ns=30_000 + seq,
        host_id="host",
        boot_id="boot",
        connection_id="conn",
        ingest_seq=seq,
        channel_hint=channel,
        capture_flags=("LIVE_CAPTURE", "WS_PUBLIC"),
    )


def _payload(coin: str, funding: str, mark: str, oracle: str) -> bytes:
    return json.dumps(
        {
            "channel": "activeAssetCtx",
            "data": {
                "coin": coin,
                "ctx": {
                    "dayBaseVlm": "100",
                    "dayNtlVlm": "1000000",
                    "funding": funding,
                    "impactPxs": ["99", "101"],
                    "markPx": mark,
                    "midPx": "100",
                    "openInterest": "1000",
                    "oraclePx": oracle,
                    "premium": "0.0001",
                    "prevDayPx": "98",
                },
            },
        },
        separators=(",", ":"),
    ).encode()


def test_qcr1_context_replay_preserves_shared_raw_provenance_and_determinism(
    tmp_path: Path,
) -> None:
    segment_id = "context-replay-segment"
    path = tmp_path / f"{segment_id}.raw.open"
    payloads = [
        _payload("BTC", "0.00001", "100", "100.1"),
        _payload("ETH", "-0.00002", "2000", "2001"),
        b'{"channel":"trades","data":[]}',
        b'{"channel":"activeAssetCtx","data":{"coin":"BTC","ctx":{}}}',
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
    results = [normalize_context_frame(frame, registry) for frame in frames]
    repeated = [normalize_context_frame(frame, registry) for frame in frames]

    assert results[0].status is ContextNormalizationStatus.EVENTS
    assert [type(event) for event in results[0].events] == [
        FundingRateObservation,
        MarkPrice,
        OraclePrice,
    ]
    assert results[1].status is ContextNormalizationStatus.EVENTS
    assert all(
        event.envelope.instrument_id == "hyperliquid.mainnet.perpetual.eth"
        for event in results[1].events
    )
    assert results[2].status is ContextNormalizationStatus.NOT_APPLICABLE
    assert results[3].status is ContextNormalizationStatus.ERROR
    assert results[3].error is not None
    assert results[3].error.code is ContextParseErrorCode.INVALID_FUNDING

    for frame, first, second in zip(frames, results, repeated, strict=True):
        assert frame.ref.payload_sha256 == hashlib.sha256(frame.payload).hexdigest()
        if first.status is ContextNormalizationStatus.EVENTS:
            assert serialize_normalized_context(first.events) == serialize_normalized_context(
                second.events
            )
            assert len({event.envelope.event_id for event in first.events}) == len(
                first.events
            )
            for event in first.events:
                assert event.envelope.raw_segment_id == segment_id
                assert event.envelope.raw_offset == frame.ref.offset
                assert event.envelope.raw_sha256 == frame.ref.payload_sha256
                assert event.envelope.exchange_ts_ns is None


def test_context_replay_event_ids_change_with_capture_occurrence(tmp_path: Path) -> None:
    segment_id = "context-duplicate-segment"
    path = tmp_path / f"{segment_id}.raw.open"
    payload = _payload("BTC", "0.00001", "100", "100.1")

    log = RawLog.open(path, segment_id)
    log.append(_metadata(1, "activeAssetCtx"), payload)
    log.append(_metadata(2, "activeAssetCtx"), payload)
    log.sync()
    log.close()

    frames = list(iter_raw_frames(path, segment_id))
    registry = load_instrument_registry("config/instruments.yaml")
    first = normalize_context_frame(frames[0], registry)
    second = normalize_context_frame(frames[1], registry)

    assert len(first.events) == 3
    assert len(second.events) == 3
    assert [event.envelope.event_id for event in first.events] != [
        event.envelope.event_id for event in second.events
    ]
    assert first.events[0].envelope.raw_offset != second.events[0].envelope.raw_offset
