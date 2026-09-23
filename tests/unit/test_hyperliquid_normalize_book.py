from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from cryptobot.adapters.hyperliquid.normalize import (
    PARSE_VERSION,
    BookNormalizationStatus,
    BookParseErrorCode,
    normalize_book_frame,
    serialize_normalized_book_event,
)
from cryptobot.data.events import (
    BBO,
    AvailabilityKind,
    ExchangeTimestampSemantics,
    L2Snapshot,
    QualityFlag,
)
from cryptobot.data.instruments import InstrumentRegistry, load_instrument_registry
from cryptobot.data.rawlog import RawFrame, RawFrameMetadata, RawRef


def _registry() -> InstrumentRegistry:
    return load_instrument_registry("config/instruments.yaml")


def _raw_frame(
    payload: bytes,
    *,
    offset: int = 0,
    flags: tuple[str, ...] = ("LIVE_CAPTURE", "WS_PUBLIC"),
) -> RawFrame:
    sha = hashlib.sha256(payload).hexdigest()
    return RawFrame(
        ref=RawRef(
            segment_id="segment-test",
            offset=offset,
            frame_length=len(payload) + 100,
            payload_length=len(payload),
            payload_sha256=sha,
            frame_checksum="0" * 64,
        ),
        metadata=RawFrameMetadata(
            schema_version=1,
            source_id="hyperliquid-mainnet-public",
            recv_wall_ns=1_790_193_802_192_000_000,
            recv_mono_ns=123_456_789,
            host_id="host-test",
            boot_id="boot-test",
            connection_id="conn-test",
            ingest_seq=7,
            channel_hint="l2Book",
            capture_flags=flags,
        ),
        payload=payload,
    )


def _l2_payload(*, coin: str = "BTC", time: object = 1_790_193_801_460) -> bytes:
    return json.dumps(
        {
            "channel": "l2Book",
            "data": {
                "coin": coin,
                "time": time,
                "levels": [
                    [
                        {"px": "100.10", "sz": "1.2500", "n": 2},
                        {"px": "99.5", "sz": "2", "n": 1},
                    ],
                    [
                        {"px": "100.20", "sz": "0.75", "n": 3},
                        {"px": "101.0", "sz": "4.5", "n": 4},
                    ],
                ],
            },
        },
        separators=(",", ":"),
    ).encode()


def _bbo_payload(
    bbo: list[object],
    *,
    coin: str = "ETH",
    time: object = 1_790_193_801_866,
) -> bytes:
    return json.dumps(
        {
            "channel": "bbo",
            "data": {"coin": coin, "time": time, "bbo": bbo},
        },
        separators=(",", ":"),
    ).encode()


def test_l2_snapshot_normalizes_exactly_with_raw_provenance() -> None:
    frame = _raw_frame(_l2_payload(), offset=321)

    result = normalize_book_frame(frame, _registry())

    assert result.status is BookNormalizationStatus.EVENT
    assert result.error is None
    assert isinstance(result.event, L2Snapshot)
    event = result.event
    assert event.bids[0].price == Decimal("100.10")
    assert event.bids[0].size == Decimal("1.2500")
    assert event.bids[0].order_count == 2
    assert event.asks[1].price == Decimal("101.0")
    assert event.full_snapshot is True
    assert event.depth_limit is None
    assert event.aggregation is None
    assert event.envelope.instrument_id == "hyperliquid.mainnet.perpetual.btc"
    assert event.envelope.native_symbol == "BTC"
    assert event.envelope.exchange_ts_ns == 1_790_193_801_460_000_000
    assert event.envelope.exchange_ts_resolution_ns == 1_000_000
    assert event.envelope.exchange_ts_semantics is ExchangeTimestampSemantics.UNKNOWN
    assert event.envelope.availability_kind is AvailabilityKind.LIVE_CAPTURE
    assert event.envelope.raw_segment_id == "segment-test"
    assert event.envelope.raw_offset == 321
    assert event.envelope.raw_sha256 == frame.ref.payload_sha256
    assert event.envelope.parse_version == PARSE_VERSION
    assert event.envelope.quality_flags is QualityFlag.NONE


def test_empty_l2_sides_are_preserved_without_synthesizing_levels() -> None:
    payload = b'{"channel":"l2Book","data":{"coin":"BTC","time":1790193801460,"levels":[[],[]]}}'

    result = normalize_book_frame(_raw_frame(payload), _registry())

    assert isinstance(result.event, L2Snapshot)
    assert result.event.bids == ()
    assert result.event.asks == ()
    assert result.event.envelope.quality_flags is QualityFlag.NONE


def test_bbo_preserves_independent_null_side() -> None:
    frame = _raw_frame(_bbo_payload([{"px": "2500.5", "sz": "3.25", "n": 6}, None]))

    result = normalize_book_frame(frame, _registry())

    assert isinstance(result.event, BBO)
    assert result.event.bid_price == Decimal("2500.5")
    assert result.event.bid_size == Decimal("3.25")
    assert result.event.ask_price is None
    assert result.event.ask_size is None


def test_bbo_crossed_state_is_preserved_and_marked_suspect() -> None:
    frame = _raw_frame(
        _bbo_payload(
            [
                {"px": "2501", "sz": "1", "n": 1},
                {"px": "2500", "sz": "2", "n": 2},
            ]
        )
    )

    result = normalize_book_frame(frame, _registry())

    assert isinstance(result.event, BBO)
    assert result.event.bid_price == Decimal("2501")
    assert result.event.ask_price == Decimal("2500")
    assert result.event.envelope.quality_flags & QualityFlag.SUSPECT


def test_unsorted_l2_is_not_reordered_and_is_marked_suspect() -> None:
    payload = json.dumps(
        {
            "channel": "l2Book",
            "data": {
                "coin": "BTC",
                "time": 1_790_193_801_460,
                "levels": [
                    [
                        {"px": "99", "sz": "1", "n": 1},
                        {"px": "100", "sz": "1", "n": 1},
                    ],
                    [
                        {"px": "102", "sz": "1", "n": 1},
                        {"px": "101", "sz": "1", "n": 1},
                    ],
                ],
            },
        }
    ).encode()

    result = normalize_book_frame(_raw_frame(payload), _registry())

    assert isinstance(result.event, L2Snapshot)
    assert [level.price for level in result.event.bids] == [Decimal("99"), Decimal("100")]
    assert [level.price for level in result.event.asks] == [Decimal("102"), Decimal("101")]
    assert result.event.envelope.quality_flags & QualityFlag.SUSPECT


def test_additive_future_fields_are_ignored_but_required_fields_remain_strict() -> None:
    message = json.loads(_l2_payload())
    message["futureTopLevel"] = {"opaque": True}
    message["data"]["futureDataField"] = "opaque"
    message["data"]["levels"][0][0]["futureLevelField"] = 123
    payload = json.dumps(message).encode()

    result = normalize_book_frame(_raw_frame(payload), _registry())

    assert result.status is BookNormalizationStatus.EVENT
    assert isinstance(result.event, L2Snapshot)


def test_non_target_channel_is_not_applicable() -> None:
    payload = b'{"channel":"trades","data":[]}'

    result = normalize_book_frame(_raw_frame(payload), _registry())

    assert result.status is BookNormalizationStatus.NOT_APPLICABLE
    assert result.channel == "trades"
    assert result.event is None
    assert result.error is None


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"not-json", BookParseErrorCode.INVALID_JSON),
        (b"[]", BookParseErrorCode.INVALID_ENVELOPE),
        (b'{"data":{}}', BookParseErrorCode.INVALID_ENVELOPE),
        (b'{"channel":"l2Book","data":[]}', BookParseErrorCode.INVALID_DATA),
        (
            b'{"channel":"l2Book","data":{"coin":"SOL","time":1,"levels":[[],[]]}}',
            BookParseErrorCode.UNSUPPORTED_COIN,
        ),
        (
            b'{"channel":"l2Book","data":{"coin":"BTC","time":"1","levels":[[],[]]}}',
            BookParseErrorCode.INVALID_TIMESTAMP,
        ),
        (
            b'{"channel":"l2Book","data":{"coin":"BTC","time":1,"levels":[[{"px":"1","sz":"2"}],[]]}}',
            BookParseErrorCode.INVALID_LEVEL_SHAPE,
        ),
        (
            b'{"channel":"l2Book","data":{"coin":"BTC","time":1,"levels":[[{"px":"NaN","sz":"2","n":1}],[]]}}',
            BookParseErrorCode.INVALID_NUMERIC,
        ),
        (
            b'{"channel":"bbo","data":{"coin":"BTC","time":1,"bbo":[null]}}',
            BookParseErrorCode.INVALID_BBO_SHAPE,
        ),
    ],
)
def test_structured_target_parse_errors(payload: bytes, code: BookParseErrorCode) -> None:
    result = normalize_book_frame(_raw_frame(payload), _registry())

    assert result.status is BookNormalizationStatus.ERROR
    assert result.event is None
    assert result.error is not None
    assert result.error.code is code
    assert result.error.raw_segment_id == "segment-test"
    assert result.error.raw_sha256 == hashlib.sha256(payload).hexdigest()
    assert payload not in result.error.detail.encode()


def test_raw_sha_mismatch_is_a_provenance_error() -> None:
    frame = _raw_frame(_l2_payload())
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

    result = normalize_book_frame(bad, _registry())

    assert result.status is BookNormalizationStatus.ERROR
    assert result.error is not None
    assert result.error.code is BookParseErrorCode.INVALID_PROVENANCE


def test_event_id_and_serialization_are_deterministic_and_offset_sensitive() -> None:
    payload = _l2_payload()
    first = normalize_book_frame(_raw_frame(payload, offset=100), _registry())
    repeated = normalize_book_frame(_raw_frame(payload, offset=100), _registry())
    moved = normalize_book_frame(_raw_frame(payload, offset=101), _registry())

    assert isinstance(first.event, L2Snapshot)
    assert isinstance(repeated.event, L2Snapshot)
    assert isinstance(moved.event, L2Snapshot)
    assert first.event.envelope.event_id == repeated.event.envelope.event_id
    assert first.event.envelope.event_id != moved.event.envelope.event_id
    assert serialize_normalized_book_event(first.event) == serialize_normalized_book_event(
        repeated.event
    )


def test_exact_serialization_avoids_binary_float_and_exponent_notation() -> None:
    frame = _raw_frame(
        _bbo_payload(
            [
                {"px": "1E+3", "sz": "0.0100", "n": 1},
                {"px": "1001", "sz": "2E-3", "n": 1},
            ]
        )
    )

    result = normalize_book_frame(frame, _registry())

    assert isinstance(result.event, BBO)
    serialized = serialize_normalized_book_event(result.event)
    decoded = json.loads(serialized)
    assert decoded["payload"]["bid_price"] == "1000"
    assert decoded["payload"]["bid_size"] == "0.0100"
    assert decoded["payload"]["ask_size"] == "0.002"
