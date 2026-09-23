from __future__ import annotations

import hashlib
import json

import pytest

from cryptobot.data.events import (
    EventType,
    FundingObservationKind,
    FundingRateObservation,
    Trade,
)
from cryptobot.data.instruments import InstrumentRegistry, load_instrument_registry
from cryptobot.data.normalization_pipeline import (
    BINANCE_SOURCE_ID,
    HL_SOURCE_ID,
    CausalDomainError,
    FrameOutcome,
    PipelineErrorCode,
    build_pipeline_report,
    normalize_frame,
    normalize_frames,
    serialize_causal_records,
    serialize_pipeline_report,
    strict_causal_records,
)
from cryptobot.data.rawlog import RawFrame, RawFrameMetadata, RawRef


def _registry() -> InstrumentRegistry:
    return load_instrument_registry("config/instruments.yaml")


def _raw(
    *,
    source: str,
    payload: bytes,
    mono: int = 100,
    wall: int = 1_000,
    host: str = "host-a",
    boot: str = "boot-a",
    segment: str = "segment-a",
    offset: int = 0,
    seq: int = 1,
    channel_hint: str | None = None,
    flags: tuple[str, ...] = ("LIVE_CAPTURE", "WS_PUBLIC"),
) -> RawFrame:
    sha = hashlib.sha256(payload).hexdigest()
    return RawFrame(
        ref=RawRef(
            segment_id=segment,
            offset=offset,
            frame_length=len(payload) + 100,
            payload_length=len(payload),
            payload_sha256=sha,
            frame_checksum="0" * 64,
        ),
        metadata=RawFrameMetadata(
            schema_version=1,
            source_id=source,
            recv_wall_ns=wall,
            recv_mono_ns=mono,
            host_id=host,
            boot_id=boot,
            connection_id=f"{source}-conn",
            ingest_seq=seq,
            channel_hint=channel_hint,
            capture_flags=flags,
        ),
        payload=payload,
    )


def _hl_bbo(*, coin: str = "BTC", bid: str = "100", ask: str = "101") -> bytes:
    return json.dumps(
        {
            "channel": "bbo",
            "data": {
                "coin": coin,
                "time": 1_790_196_000_000,
                "bbo": [
                    {"px": bid, "sz": "1.25", "n": 2},
                    {"px": ask, "sz": "2.50", "n": 3},
                ],
            },
        },
        separators=(",", ":"),
    ).encode()


def _hl_trade(*, tid: int = 1, time: int = 1_790_196_000_100) -> bytes:
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
                    "time": time,
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


def _binance_bbo(*, symbol: str = "BTCUSDT") -> bytes:
    return json.dumps(
        {
            "stream": f"{symbol.lower()}@bookTicker",
            "data": {
                "e": "bookTicker",
                "u": 7,
                "E": 1_790_196_000_200,
                "T": 1_790_196_000_199,
                "s": symbol,
                "ps": symbol,
                "b": "100.0",
                "B": "1.2",
                "a": "100.1",
                "A": "1.3",
                "st": 1,
            },
        },
        separators=(",", ":"),
    ).encode()


def _binance_trade(*, aggregate_id: int = 9) -> bytes:
    return json.dumps(
        {
            "stream": "btcusdt@aggTrade",
            "data": {
                "e": "aggTrade",
                "E": 1_790_196_000_300,
                "s": "BTCUSDT",
                "a": aggregate_id,
                "p": "100.05",
                "q": "0.1",
                "nq": "0.1",
                "f": 10,
                "l": 11,
                "T": 1_790_196_000_299,
                "m": False,
                "st": 1,
            },
        },
        separators=(",", ":"),
    ).encode()


def _hl_frame(
    payload: bytes,
    *,
    mono: int = 100,
    wall: int = 1_000,
    host: str = "host-a",
    boot: str = "boot-a",
    segment: str = "segment-a",
    offset: int = 0,
    seq: int = 1,
) -> RawFrame:
    return _raw(
        source=HL_SOURCE_ID,
        payload=payload,
        mono=mono,
        wall=wall,
        host=host,
        boot=boot,
        segment=segment,
        offset=offset,
        seq=seq,
        channel_hint="hyperliquid",
    )


def _binance_frame(
    payload: bytes,
    *,
    mono: int = 100,
    wall: int = 1_000,
    host: str = "host-a",
    boot: str = "boot-a",
    segment: str = "segment-a",
    offset: int = 0,
    seq: int = 1,
) -> RawFrame:
    return _raw(
        source=BINANCE_SOURCE_ID,
        payload=payload,
        mono=mono,
        wall=wall,
        host=host,
        boot=boot,
        segment=segment,
        offset=offset,
        seq=seq,
        channel_hint="binance",
        flags=("BINANCE_PUBLIC", "LIVE_CAPTURE", "WS_PUBLIC"),
    )


def test_dispatches_hyperliquid_book_trade_and_context() -> None:
    frames = (
        _hl_frame(_hl_bbo(), mono=10, offset=10),
        _hl_frame(_hl_trade(), mono=20, offset=20),
        _hl_frame(_hl_context(), mono=30, offset=30),
    )

    results = normalize_frames(frames, _registry())

    assert [result.outcome for result in results] == [
        FrameOutcome.EVENTS,
        FrameOutcome.EVENTS,
        FrameOutcome.EVENTS,
    ]
    assert [event.envelope.event_type for event in results[0].events] == [EventType.BBO]
    assert [event.envelope.event_type for event in results[1].events] == [EventType.TRADE]
    assert [event.envelope.event_type for event in results[2].events] == [
        EventType.FUNDING_RATE_OBSERVATION,
        EventType.MARK_PRICE,
        EventType.ORACLE_PRICE,
    ]
    funding = results[2].events[0]
    assert isinstance(funding, FundingRateObservation)
    assert funding.kind is FundingObservationKind.CURRENT


def test_dispatches_binance_reference_events() -> None:
    results = normalize_frames(
        (
            _binance_frame(_binance_bbo(), mono=10, offset=10),
            _binance_frame(_binance_trade(), mono=20, offset=20),
        ),
        _registry(),
    )

    assert [event.envelope.event_type for result in results for event in result.events] == [
        EventType.REFERENCE_BBO,
        EventType.REFERENCE_TRADE,
    ]


def test_control_messages_are_explicit_not_applicable() -> None:
    hl = _hl_frame(b'{"channel":"subscriptionResponse","data":{}}')
    binance = _binance_frame(b'{"result":null,"id":1301}', offset=200)

    results = normalize_frames((hl, binance), _registry())

    assert all(result.outcome is FrameOutcome.NOT_APPLICABLE for result in results)
    assert all(result.events == () and result.error is None for result in results)


def test_empty_trade_batch_is_explicit_empty() -> None:
    result = normalize_frame(
        _hl_frame(b'{"channel":"trades","data":[]}'),
        _registry(),
    )

    assert result.outcome is FrameOutcome.EMPTY
    assert result.events == ()
    assert result.error is None


def test_unsupported_source_is_explicit_error() -> None:
    result = normalize_frame(
        _raw(source="other-source", payload=b"{}"),
        _registry(),
    )

    assert result.outcome is FrameOutcome.ERROR
    assert result.error is not None
    assert result.error.code is PipelineErrorCode.UNSUPPORTED_SOURCE


def test_malformed_hyperliquid_json_is_dispatch_error() -> None:
    payload = b"not-json"
    result = normalize_frame(_hl_frame(payload), _registry())

    assert result.outcome is FrameOutcome.ERROR
    assert result.error is not None
    assert result.error.code is PipelineErrorCode.INVALID_JSON
    assert payload not in result.error.detail.encode()


def test_target_parser_error_is_preserved_structurally() -> None:
    payload = b'{"channel":"trades","data":[{"coin":"BTC"}]}'
    result = normalize_frame(_hl_frame(payload), _registry())

    assert result.outcome is FrameOutcome.ERROR
    assert result.error is not None
    assert result.error.code is PipelineErrorCode.PARSER_ERROR
    assert result.error.parser_code == "INVALID_TRADE_OBJECT"
    assert payload not in result.error.detail.encode()


def test_raw_sha_mismatch_fails_before_dispatch() -> None:
    frame = _hl_frame(_hl_bbo())
    bad = RawFrame(
        ref=RawRef(
            segment_id=frame.ref.segment_id,
            offset=frame.ref.offset,
            frame_length=frame.ref.frame_length,
            payload_length=frame.ref.payload_length,
            payload_sha256="f" * 64,
            frame_checksum=frame.ref.frame_checksum,
        ),
        metadata=frame.metadata,
        payload=frame.payload,
    )

    result = normalize_frame(bad, _registry())

    assert result.outcome is FrameOutcome.ERROR
    assert result.error is not None
    assert result.error.code is PipelineErrorCode.INVALID_PROVENANCE


def test_multi_event_frame_preserves_parser_event_ordinal() -> None:
    result = normalize_frame(_hl_frame(_hl_context()), _registry())

    records = strict_causal_records((result,))

    assert [record.event_ordinal for record in records] == [0, 1, 2]
    assert [record.event.envelope.event_type for record in records] == [
        EventType.FUNDING_RATE_OBSERVATION,
        EventType.MARK_PRICE,
        EventType.ORACLE_PRICE,
    ]


def test_strict_causal_order_uses_monotonic_time_not_input_order() -> None:
    later = normalize_frame(
        _binance_frame(_binance_bbo(), mono=200, wall=1_200, offset=20),
        _registry(),
    )
    earlier = normalize_frame(
        _hl_frame(_hl_bbo(), mono=100, wall=1_100, offset=10),
        _registry(),
    )

    records = strict_causal_records((later, earlier))

    assert [record.recv_mono_ns for record in records] == [100, 200]
    assert [record.source_id for record in records] == [HL_SOURCE_ID, BINANCE_SOURCE_ID]


def test_equal_monotonic_time_uses_deterministic_nonsemantic_tie_break() -> None:
    first = normalize_frame(
        _hl_frame(_hl_bbo(), mono=100, wall=1_100, offset=10),
        _registry(),
    )
    second = normalize_frame(
        _binance_frame(_binance_bbo(), mono=100, wall=1_050, offset=20),
        _registry(),
    )

    records = strict_causal_records((first, second))

    assert [record.recv_wall_ns for record in records] == [1_050, 1_100]


def test_wall_clock_regression_is_reported_but_monotonic_order_wins() -> None:
    first = normalize_frame(
        _hl_frame(_hl_bbo(), mono=100, wall=1_200, offset=10),
        _registry(),
    )
    second = normalize_frame(
        _binance_frame(_binance_bbo(), mono=200, wall=1_100, offset=20),
        _registry(),
    )

    records = strict_causal_records((second, first))
    report = build_pipeline_report((second, first))

    assert [record.recv_mono_ns for record in records] == [100, 200]
    assert report.clock_order_anomaly_count == 1


@pytest.mark.parametrize(
    ("first_host", "first_boot", "second_host", "second_boot"),
    [
        ("host-a", "boot-a", "host-b", "boot-a"),
        ("host-a", "boot-a", "host-a", "boot-b"),
    ],
)
def test_strict_merge_rejects_mixed_clock_domains(
    first_host: str,
    first_boot: str,
    second_host: str,
    second_boot: str,
) -> None:
    first = normalize_frame(
        _hl_frame(
            _hl_bbo(),
            mono=100,
            offset=10,
            host=first_host,
            boot=first_boot,
        ),
        _registry(),
    )
    second = normalize_frame(
        _binance_frame(
            _binance_bbo(),
            mono=200,
            offset=20,
            host=second_host,
            boot=second_boot,
        ),
        _registry(),
    )

    with pytest.raises(CausalDomainError):
        strict_causal_records((first, second))


def test_reconnect_duplicate_trade_id_is_counted_not_removed() -> None:
    payload = _hl_trade(tid=777)
    first = normalize_frame(
        _hl_frame(payload, mono=100, segment="seg-1", offset=10),
        _registry(),
    )
    second = normalize_frame(
        _hl_frame(payload, mono=200, segment="seg-2", offset=10),
        _registry(),
    )

    records = strict_causal_records((first, second))
    report = build_pipeline_report((first, second))

    assert len(records) == 2
    assert isinstance(records[0].event, Trade)
    assert isinstance(records[1].event, Trade)
    assert records[0].event.trade_id == records[1].event.trade_id
    assert records[0].event.envelope.event_id != records[1].event.envelope.event_id
    assert report.duplicate_stable_trade_id_count == 1


def test_report_and_record_serialization_are_deterministic() -> None:
    results = normalize_frames(
        (
            _hl_frame(_hl_trade(tid=1), mono=100, offset=10),
            _binance_frame(_binance_trade(aggregate_id=2), mono=200, offset=20),
            _hl_frame(b'{"channel":"subscriptionResponse","data":{}}', mono=300, offset=30),
        ),
        _registry(),
    )

    records_first = strict_causal_records(results)
    records_second = strict_causal_records(tuple(reversed(results)))
    report_first = build_pipeline_report(results)
    report_second = build_pipeline_report(tuple(reversed(results)))

    assert serialize_causal_records(records_first) == serialize_causal_records(records_second)
    assert serialize_pipeline_report(report_first) == serialize_pipeline_report(report_second)
    assert report_first.normalized_records_sha256 == report_second.normalized_records_sha256
    assert report_first.total_raw_frames == 3
    assert dict(report_first.outcome_counts)[FrameOutcome.NOT_APPLICABLE.value] == 1
