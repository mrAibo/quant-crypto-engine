from __future__ import annotations

import json
from pathlib import Path

from cryptobot.data.events import EventType, Trade
from cryptobot.data.instruments import load_instrument_registry
from cryptobot.data.normalization_pipeline import (
    BINANCE_SOURCE_ID,
    HL_SOURCE_ID,
    FrameOutcome,
    build_pipeline_report,
    normalize_frames,
    serialize_causal_records,
    serialize_pipeline_report,
    strict_causal_records,
)
from cryptobot.data.rawlog import RawFrameMetadata, RawLog, iter_raw_frames


def _metadata(
    *,
    source: str,
    mono: int,
    wall: int,
    seq: int,
    channel_hint: str,
) -> RawFrameMetadata:
    flags = (
        ("BINANCE_PUBLIC", "LIVE_CAPTURE", "WS_PUBLIC")
        if source == BINANCE_SOURCE_ID
        else ("LIVE_CAPTURE", "WS_PUBLIC")
    )
    return RawFrameMetadata(
        schema_version=1,
        source_id=source,
        recv_wall_ns=wall,
        recv_mono_ns=mono,
        host_id="shared-recorder",
        boot_id="shared-boot",
        connection_id=f"{source}-conn",
        ingest_seq=seq,
        channel_hint=channel_hint,
        capture_flags=flags,
    )


def _hl_bbo() -> bytes:
    return json.dumps(
        {
            "channel": "bbo",
            "data": {
                "coin": "BTC",
                "time": 1_790_196_100_000,
                "bbo": [
                    {"px": "100", "sz": "1", "n": 1},
                    {"px": "101", "sz": "2", "n": 1},
                ],
            },
        },
        separators=(",", ":"),
    ).encode()


def _hl_trade(tid: int) -> bytes:
    return json.dumps(
        {
            "channel": "trades",
            "data": [
                {
                    "coin": "BTC",
                    "side": "B",
                    "px": "100.5",
                    "sz": "0.01",
                    "hash": "0x" + "a" * 64,
                    "time": 1_790_196_100_100,
                    "tid": tid,
                    "users": ["0x" + "1" * 40, "0x" + "2" * 40],
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def _hl_context() -> bytes:
    return json.dumps(
        {
            "channel": "activeAssetCtx",
            "data": {
                "coin": "BTC",
                "ctx": {
                    "funding": "0.00001",
                    "markPx": "100.2",
                    "oraclePx": "100.0",
                },
            },
        },
        separators=(",", ":"),
    ).encode()


def _binance_bbo() -> bytes:
    return json.dumps(
        {
            "stream": "btcusdt@bookTicker",
            "data": {
                "e": "bookTicker",
                "u": 11,
                "E": 1_790_196_100_200,
                "T": 1_790_196_100_199,
                "s": "BTCUSDT",
                "ps": "BTCUSDT",
                "b": "100.0",
                "B": "1.2",
                "a": "100.1",
                "A": "1.3",
                "st": 1,
            },
        },
        separators=(",", ":"),
    ).encode()


def _binance_trade() -> bytes:
    return json.dumps(
        {
            "stream": "btcusdt@aggTrade",
            "data": {
                "e": "aggTrade",
                "E": 1_790_196_100_300,
                "s": "BTCUSDT",
                "a": 21,
                "p": "100.05",
                "q": "0.1",
                "nq": "0.1",
                "f": 100,
                "l": 101,
                "T": 1_790_196_100_299,
                "m": False,
                "st": 1,
            },
        },
        separators=(",", ":"),
    ).encode()


def _write_segment(
    path: Path,
    segment_id: str,
    source: str,
    frames: list[tuple[int, int, str, bytes]],
) -> None:
    log = RawLog.open(path, segment_id)
    for seq, (mono, wall, hint, payload) in enumerate(frames, start=1):
        log.append(
            _metadata(
                source=source,
                mono=mono,
                wall=wall,
                seq=seq,
                channel_hint=hint,
            ),
            payload,
        )
    log.sync()
    log.close()


def test_qcr1_two_venue_causal_replay_is_deterministic_and_auditable(
    tmp_path: Path,
) -> None:
    hl_segment = "hl-segment"
    binance_segment = "binance-segment"
    hl_path = tmp_path / f"{hl_segment}.raw"
    binance_path = tmp_path / f"{binance_segment}.raw"

    duplicate_trade = _hl_trade(777)
    _write_segment(
        hl_path,
        hl_segment,
        HL_SOURCE_ID,
        [
            (100, 10_100, "bbo", _hl_bbo()),
            (300, 10_300, "trades", duplicate_trade),
            (500, 10_500, "trades", duplicate_trade),
            (700, 10_700, "activeAssetCtx", _hl_context()),
            (
                900,
                10_900,
                "subscriptionResponse",
                b'{"channel":"subscriptionResponse","data":{}}',
            ),
            (
                1_100,
                11_100,
                "trades",
                b'{"channel":"trades","data":[{"coin":"BTC"}]}',
            ),
        ],
    )
    _write_segment(
        binance_path,
        binance_segment,
        BINANCE_SOURCE_ID,
        [
            (200, 10_200, "bookTicker", _binance_bbo()),
            (400, 10_400, "aggTrade", _binance_trade()),
            (800, 10_800, "subscription", b'{"result":null,"id":1301}'),
        ],
    )

    registry = load_instrument_registry("config/instruments.yaml")
    hl_frames = tuple(iter_raw_frames(hl_path, hl_segment))
    binance_frames = tuple(iter_raw_frames(binance_path, binance_segment))

    results_first = normalize_frames((*hl_frames, *binance_frames), registry)
    results_second = normalize_frames((*reversed(binance_frames), *reversed(hl_frames)), registry)

    records_first = strict_causal_records(results_first)
    records_second = strict_causal_records(results_second)
    report_first = build_pipeline_report(results_first)
    report_second = build_pipeline_report(results_second)

    assert [record.recv_mono_ns for record in records_first] == [
        100,
        200,
        300,
        400,
        500,
        700,
        700,
        700,
    ]
    assert [record.event.envelope.event_type for record in records_first] == [
        EventType.BBO,
        EventType.REFERENCE_BBO,
        EventType.TRADE,
        EventType.REFERENCE_TRADE,
        EventType.TRADE,
        EventType.FUNDING_RATE_OBSERVATION,
        EventType.MARK_PRICE,
        EventType.ORACLE_PRICE,
    ]

    context_records = [record for record in records_first if record.recv_mono_ns == 700]
    assert [record.event_ordinal for record in context_records] == [0, 1, 2]

    trades = [
        record.event
        for record in records_first
        if isinstance(record.event, Trade)
    ]
    assert len(trades) == 2
    assert trades[0].trade_id == trades[1].trade_id
    assert trades[0].envelope.event_id != trades[1].envelope.event_id

    for record in records_first:
        matching = [
            frame
            for frame in (*hl_frames, *binance_frames)
            if frame.ref.segment_id == record.raw_segment_id
            and frame.ref.offset == record.raw_offset
        ]
        assert len(matching) == 1
        assert record.event.envelope.raw_sha256 == matching[0].ref.payload_sha256
        assert record.event.envelope.raw_segment_id == record.raw_segment_id
        assert record.event.envelope.raw_offset == record.raw_offset

    assert sum(result.outcome is FrameOutcome.NOT_APPLICABLE for result in results_first) == 2
    errors = [result for result in results_first if result.outcome is FrameOutcome.ERROR]
    assert len(errors) == 1
    assert errors[0].error is not None
    assert errors[0].error.parser_code == "INVALID_TRADE_OBJECT"

    assert report_first.total_raw_frames == 9
    assert report_first.normalized_record_count == 8
    assert report_first.duplicate_stable_trade_id_count == 1
    assert report_first.causal_domain_count == 1
    assert report_first.clock_order_anomaly_count == 0

    assert serialize_causal_records(records_first) == serialize_causal_records(records_second)
    assert serialize_pipeline_report(report_first) == serialize_pipeline_report(report_second)
    assert report_first.normalized_records_sha256 == report_second.normalized_records_sha256
