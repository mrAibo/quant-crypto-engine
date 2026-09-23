from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from cryptobot.adapters.hyperliquid.trades import (
    PARSE_VERSION,
    TradeNormalizationStatus,
    TradeParseErrorCode,
    normalize_trade_frame,
    serialize_normalized_trades,
)
from cryptobot.data.events import (
    ExchangeTimestampSemantics,
    TradeSide,
)
from cryptobot.data.instruments import InstrumentRegistry, load_instrument_registry
from cryptobot.data.rawlog import RawFrame, RawFrameMetadata, RawRef


def _registry() -> InstrumentRegistry:
    return load_instrument_registry("config/instruments.yaml")


def _raw_frame(payload: bytes, *, offset: int = 0) -> RawFrame:
    sha = hashlib.sha256(payload).hexdigest()
    return RawFrame(
        ref=RawRef(
            segment_id="trade-segment",
            offset=offset,
            frame_length=len(payload) + 100,
            payload_length=len(payload),
            payload_sha256=sha,
            frame_checksum="0" * 64,
        ),
        metadata=RawFrameMetadata(
            schema_version=1,
            source_id="hyperliquid-mainnet-public",
            recv_wall_ns=1_790_195_471_361_000_000,
            recv_mono_ns=987_654_321,
            host_id="host-test",
            boot_id="boot-test",
            connection_id="conn-test",
            ingest_seq=17,
            channel_hint="trades",
            capture_flags=("LIVE_CAPTURE", "WS_PUBLIC"),
        ),
        payload=payload,
    )


def _trade(
    *,
    coin: str = "BTC",
    side: str = "B",
    px: object = "65100.0",
    sz: object = "0.100",
    time: object = 1_790_195_471_030,
    tid: object = 123_456_789,
    hash_value: object = "0x" + "a" * 64,
    users: object = None,
) -> dict[str, object]:
    if users is None:
        users = ["0x" + "1" * 40, "0x" + "2" * 40]
    return {
        "coin": coin,
        "side": side,
        "px": px,
        "sz": sz,
        "hash": hash_value,
        "time": time,
        "tid": tid,
        "users": users,
    }


def _payload(trades: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {"channel": "trades", "data": trades},
        separators=(",", ":"),
    ).encode()


def test_single_trade_normalizes_with_stable_native_identity_and_raw_provenance() -> None:
    frame = _raw_frame(_payload([_trade()]), offset=333)

    result = normalize_trade_frame(frame, _registry())

    assert result.status is TradeNormalizationStatus.EVENTS
    assert result.error is None
    assert len(result.events) == 1
    event = result.events[0]
    assert event.price == Decimal("65100.0")
    assert event.size == Decimal("0.100")
    assert event.native_side == "B"
    assert event.aggressor_side is TradeSide.UNKNOWN
    assert event.trade_id == "1790195471030:BTC:123456789"
    assert event.transaction_hash == "0x" + "a" * 64
    assert event.envelope.instrument_id == "hyperliquid.mainnet.perpetual.btc"
    assert event.envelope.exchange_ts_ns == 1_790_195_471_030_000_000
    assert event.envelope.exchange_ts_resolution_ns == 1_000_000
    assert event.envelope.exchange_ts_semantics is ExchangeTimestampSemantics.UNKNOWN
    assert event.envelope.native_update_id == event.trade_id
    assert event.envelope.raw_segment_id == "trade-segment"
    assert event.envelope.raw_offset == 333
    assert event.envelope.raw_sha256 == frame.ref.payload_sha256
    assert event.envelope.parse_version == PARSE_VERSION


def test_eth_trade_maps_to_replication_instrument() -> None:
    result = normalize_trade_frame(
        _raw_frame(_payload([_trade(coin="ETH", tid=44)])),
        _registry(),
    )

    assert len(result.events) == 1
    assert result.events[0].envelope.instrument_id == "hyperliquid.mainnet.perpetual.eth"
    assert result.events[0].trade_id == "1790195471030:ETH:44"


def test_multi_trade_frame_preserves_source_order_and_unique_event_ids() -> None:
    trades = [
        _trade(side="A", tid=101, px="65099.5"),
        _trade(side="B", tid=102, px="65100.0"),
        _trade(side="A", tid=103, px="65099.0"),
    ]

    result = normalize_trade_frame(_raw_frame(_payload(trades)), _registry())

    assert [event.native_side for event in result.events] == ["A", "B", "A"]
    assert [event.trade_id for event in result.events] == [
        "1790195471030:BTC:101",
        "1790195471030:BTC:102",
        "1790195471030:BTC:103",
    ]
    assert len({event.envelope.event_id for event in result.events}) == 3


def test_native_side_is_preserved_without_inventing_aggressor_semantics() -> None:
    result = normalize_trade_frame(
        _raw_frame(_payload([_trade(side="A"), _trade(side="B", tid=2)])),
        _registry(),
    )

    assert [event.native_side for event in result.events] == ["A", "B"]
    assert all(event.aggressor_side is TradeSide.UNKNOWN for event in result.events)


def test_empty_trade_array_is_valid_zero_event_batch() -> None:
    result = normalize_trade_frame(_raw_frame(_payload([])), _registry())

    assert result.status is TradeNormalizationStatus.EVENTS
    assert result.events == ()
    assert result.error is None


def test_additive_future_fields_are_ignored() -> None:
    trade = _trade()
    trade["futureField"] = {"opaque": True}
    payload = json.dumps(
        {
            "channel": "trades",
            "futureEnvelopeField": 123,
            "data": [trade],
        }
    ).encode()

    result = normalize_trade_frame(_raw_frame(payload), _registry())

    assert result.status is TradeNormalizationStatus.EVENTS
    assert len(result.events) == 1


def test_exact_decimal_serialization_avoids_binary_float() -> None:
    result = normalize_trade_frame(
        _raw_frame(_payload([_trade(px="1E+3", sz="0.0100")])),
        _registry(),
    )

    serialized = serialize_normalized_trades(result.events)
    decoded = json.loads(serialized)
    assert decoded[0]["price"] == "1000"
    assert decoded[0]["size"] == "0.0100"


def test_reconnect_duplicate_has_same_trade_id_but_distinct_capture_event_id() -> None:
    payload = _payload([_trade(tid=999)])
    first = normalize_trade_frame(_raw_frame(payload, offset=100), _registry())
    replay = normalize_trade_frame(_raw_frame(payload, offset=900), _registry())

    assert first.events[0].trade_id == replay.events[0].trade_id
    assert first.events[0].envelope.event_id != replay.events[0].envelope.event_id


def test_equal_price_and_size_do_not_merge_distinct_native_trades() -> None:
    result = normalize_trade_frame(
        _raw_frame(_payload([_trade(tid=1), _trade(tid=2)])),
        _registry(),
    )

    assert len(result.events) == 2
    assert result.events[0].price == result.events[1].price
    assert result.events[0].size == result.events[1].size
    assert result.events[0].trade_id != result.events[1].trade_id


def test_repeated_normalization_is_byte_deterministic() -> None:
    frame = _raw_frame(_payload([_trade(tid=11), _trade(tid=12)]))

    first = normalize_trade_frame(frame, _registry())
    second = normalize_trade_frame(frame, _registry())

    assert serialize_normalized_trades(first.events) == serialize_normalized_trades(second.events)
    assert [event.envelope.event_id for event in first.events] == [
        event.envelope.event_id for event in second.events
    ]


def test_non_target_channel_is_not_applicable() -> None:
    result = normalize_trade_frame(
        _raw_frame(b'{"channel":"bbo","data":{}}'),
        _registry(),
    )

    assert result.status is TradeNormalizationStatus.NOT_APPLICABLE
    assert result.channel == "bbo"
    assert result.events == ()
    assert result.error is None


@pytest.mark.parametrize(
    ("payload", "code", "index"),
    [
        (b"not-json", TradeParseErrorCode.INVALID_JSON, None),
        (b"[]", TradeParseErrorCode.INVALID_ENVELOPE, None),
        (b'{"data":[]}', TradeParseErrorCode.INVALID_ENVELOPE, None),
        (
            b'{"channel":"trades","data":{}}',
            TradeParseErrorCode.INVALID_TRADES_ARRAY,
            None,
        ),
        (
            b'{"channel":"trades","data":[1]}',
            TradeParseErrorCode.INVALID_TRADE_OBJECT,
            0,
        ),
        (
            _payload([_trade(coin="SOL")]),
            TradeParseErrorCode.UNSUPPORTED_COIN,
            0,
        ),
        (
            _payload([_trade(side="X")]),
            TradeParseErrorCode.INVALID_NATIVE_SIDE,
            0,
        ),
        (
            _payload([_trade(time="1")]),
            TradeParseErrorCode.INVALID_TIMESTAMP,
            0,
        ),
        (
            _payload([_trade(px=1.0)]),
            TradeParseErrorCode.INVALID_NUMERIC,
            0,
        ),
        (
            _payload([_trade(sz="NaN")]),
            TradeParseErrorCode.INVALID_NUMERIC,
            0,
        ),
        (
            _payload([_trade(tid=-1)]),
            TradeParseErrorCode.INVALID_TID,
            0,
        ),
        (
            _payload([_trade(tid=1 << 50)]),
            TradeParseErrorCode.INVALID_TID,
            0,
        ),
        (
            _payload([_trade(hash_value="")]),
            TradeParseErrorCode.INVALID_TRANSACTION_HASH,
            0,
        ),
        (
            _payload([_trade(users=["one"])]),
            TradeParseErrorCode.INVALID_USERS,
            0,
        ),
    ],
)
def test_structured_trade_parse_errors(
    payload: bytes,
    code: TradeParseErrorCode,
    index: int | None,
) -> None:
    result = normalize_trade_frame(_raw_frame(payload), _registry())

    assert result.status is TradeNormalizationStatus.ERROR
    assert result.events == ()
    assert result.error is not None
    assert result.error.code is code
    assert result.error.trade_index == index
    assert result.error.raw_sha256 == hashlib.sha256(payload).hexdigest()
    assert payload not in result.error.detail.encode()


def test_missing_required_trade_field_fails_whole_target_frame() -> None:
    malformed = _trade(tid=2)
    del malformed["users"]
    payload = _payload([_trade(tid=1), malformed, _trade(tid=3)])

    result = normalize_trade_frame(_raw_frame(payload), _registry())

    assert result.status is TradeNormalizationStatus.ERROR
    assert result.events == ()
    assert result.error is not None
    assert result.error.trade_index == 1
    assert result.error.code is TradeParseErrorCode.INVALID_TRADE_OBJECT


def test_raw_sha_mismatch_is_a_provenance_error() -> None:
    frame = _raw_frame(_payload([_trade()]))
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

    result = normalize_trade_frame(bad, _registry())

    assert result.status is TradeNormalizationStatus.ERROR
    assert result.error is not None
    assert result.error.code is TradeParseErrorCode.INVALID_PROVENANCE
