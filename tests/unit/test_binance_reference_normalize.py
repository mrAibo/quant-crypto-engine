from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from cryptobot.adapters.binance.normalize import (
    BinanceReferenceNormalizationStatus,
    BinanceReferenceParseErrorCode,
    normalize_binance_reference_frame,
    serialize_binance_reference_event,
)
from cryptobot.data.events import (
    ExchangeTimestampSemantics,
    QualityFlag,
    ReferenceBBO,
    ReferenceTrade,
    TradeSide,
)
from cryptobot.data.instruments import InstrumentRegistry, load_instrument_registry
from cryptobot.data.rawlog import RawFrame, RawFrameMetadata, RawRef


def _registry() -> InstrumentRegistry:
    return load_instrument_registry("config/instruments.yaml")


def _raw(payload: bytes, *, offset: int = 0) -> RawFrame:
    sha = hashlib.sha256(payload).hexdigest()
    return RawFrame(
        ref=RawRef(
            segment_id="binance-ref-segment",
            offset=offset,
            frame_length=len(payload) + 100,
            payload_length=len(payload),
            payload_sha256=sha,
            frame_checksum="0" * 64,
        ),
        metadata=RawFrameMetadata(
            schema_version=1,
            source_id="binance-usdm-reference-public",
            recv_wall_ns=1_790_196_000_500_000_000,
            recv_mono_ns=777,
            host_id="host",
            boot_id="boot",
            connection_id="public-conn",
            ingest_seq=3,
            channel_hint="btcusdt@bookTicker",
            capture_flags=("LIVE_CAPTURE", "WS_PUBLIC", "BINANCE_PUBLIC"),
        ),
        payload=payload,
    )


def _bbo(
    *,
    symbol: str = "BTCUSDT",
    bid: object = "84000.00",
    ask: object = "84000.10",
    st: object = 1,
    stream: str | None = None,
) -> bytes:
    if stream is None:
        stream = f"{symbol.lower()}@bookTicker"
    return json.dumps(
        {
            "stream": stream,
            "data": {
                "e": "bookTicker",
                "u": 400900217,
                "E": 1_790_196_000_100,
                "T": 1_790_196_000_099,
                "s": symbol,
                "ps": symbol,
                "b": bid,
                "B": "1.2500",
                "a": ask,
                "A": "2.500",
                "st": st,
            },
        },
        separators=(",", ":"),
    ).encode()


def _trade(
    *,
    symbol: str = "BTCUSDT",
    maker: object = False,
    st: object = 1,
    aggregate_id: object = 5933014,
    stream: str | None = None,
) -> bytes:
    if stream is None:
        stream = f"{symbol.lower()}@aggTrade"
    return json.dumps(
        {
            "stream": stream,
            "data": {
                "e": "aggTrade",
                "E": 1_790_196_000_200,
                "s": symbol,
                "a": aggregate_id,
                "p": "84000.05",
                "q": "0.0100",
                "nq": "0.0100",
                "f": 100,
                "l": 105,
                "T": 1_790_196_000_198,
                "m": maker,
                "st": st,
            },
        },
        separators=(",", ":"),
    ).encode()


def test_book_ticker_normalizes_to_reference_bbo() -> None:
    result = normalize_binance_reference_frame(_raw(_bbo(), offset=10), _registry())

    assert result.status is BinanceReferenceNormalizationStatus.EVENT
    assert isinstance(result.event, ReferenceBBO)
    event = result.event
    assert event.bid_price == Decimal("84000.00")
    assert event.bid_size == Decimal("1.2500")
    assert event.ask_price == Decimal("84000.10")
    assert event.ask_size == Decimal("2.500")
    assert event.sampling_mode == "REALTIME_BOOK_TICKER"
    assert event.envelope.instrument_id == "binance_usdm.reference.perpetual.btcusdt"
    assert event.envelope.exchange_ts_ns == 1_790_196_000_100_000_000
    assert event.envelope.exchange_ts_semantics is ExchangeTimestampSemantics.EVENT_TIME
    assert event.envelope.native_update_id == "400900217"
    assert event.envelope.raw_offset == 10


def test_eth_book_ticker_maps_to_reference_instrument() -> None:
    result = normalize_binance_reference_frame(_raw(_bbo(symbol="ETHUSDT")), _registry())

    assert isinstance(result.event, ReferenceBBO)
    assert result.event.envelope.instrument_id == "binance_usdm.reference.perpetual.ethusdt"


def test_crossed_reference_bbo_is_preserved_and_marked_suspect() -> None:
    result = normalize_binance_reference_frame(
        _raw(_bbo(bid="84001", ask="84000")),
        _registry(),
    )

    assert isinstance(result.event, ReferenceBBO)
    assert result.event.bid_price == Decimal("84001")
    assert result.event.ask_price == Decimal("84000")
    assert result.event.envelope.quality_flags & QualityFlag.SUSPECT


@pytest.mark.parametrize(
    ("maker", "native_side", "aggressor"),
    [
        (True, "BUYER_MAKER", TradeSide.SELL),
        (False, "BUYER_TAKER", TradeSide.BUY),
    ],
)
def test_aggtrade_maps_documented_maker_flag_to_aggressor(
    maker: bool,
    native_side: str,
    aggressor: TradeSide,
) -> None:
    result = normalize_binance_reference_frame(_raw(_trade(maker=maker)), _registry())

    assert isinstance(result.event, ReferenceTrade)
    event = result.event
    assert event.price == Decimal("84000.05")
    assert event.size == Decimal("0.0100")
    assert event.native_side == native_side
    assert event.aggressor_side is aggressor
    assert event.trade_id == "BTCUSDT:5933014"
    assert event.envelope.exchange_ts_ns == 1_790_196_000_198_000_000
    assert event.envelope.exchange_ts_semantics is ExchangeTimestampSemantics.TRADE_TIME
    assert event.envelope.native_update_id == event.trade_id


def test_subscription_ack_is_not_applicable_to_normalizer() -> None:
    result = normalize_binance_reference_frame(
        _raw(b'{"result":null,"id":"task013-public"}'),
        _registry(),
    )

    assert result.status is BinanceReferenceNormalizationStatus.NOT_APPLICABLE
    assert result.event is None


def test_serialization_is_exact_and_deterministic() -> None:
    frame = _raw(_trade())
    first = normalize_binance_reference_frame(frame, _registry())
    second = normalize_binance_reference_frame(frame, _registry())

    assert first.event is not None
    assert second.event is not None
    assert serialize_binance_reference_event(first.event) == serialize_binance_reference_event(
        second.event
    )
    decoded = json.loads(serialize_binance_reference_event(first.event))
    assert decoded["price"] == "84000.05"
    assert decoded["size"] == "0.0100"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"not-json", BinanceReferenceParseErrorCode.INVALID_JSON),
        (_bbo(symbol="SOLUSDT"), BinanceReferenceParseErrorCode.UNSUPPORTED_SYMBOL),
        (_bbo(st=2), BinanceReferenceParseErrorCode.WRONG_SYMBOL_TYPE),
        (_bbo(st=True), BinanceReferenceParseErrorCode.WRONG_SYMBOL_TYPE),
        (_bbo(stream="ethusdt@bookTicker"), BinanceReferenceParseErrorCode.UNSUPPORTED_STREAM),
        (_bbo(bid="NaN"), BinanceReferenceParseErrorCode.INVALID_NUMERIC),
        (_trade(maker="false"), BinanceReferenceParseErrorCode.INVALID_MAKER_FLAG),
        (_trade(st=2), BinanceReferenceParseErrorCode.WRONG_SYMBOL_TYPE),
        (_trade(aggregate_id=-1), BinanceReferenceParseErrorCode.INVALID_NATIVE_ID),
        (_trade(stream="ethusdt@aggTrade"), BinanceReferenceParseErrorCode.UNSUPPORTED_STREAM),
    ],
)
def test_structured_reference_parse_errors(
    payload: bytes,
    code: BinanceReferenceParseErrorCode,
) -> None:
    result = normalize_binance_reference_frame(_raw(payload), _registry())

    assert result.status is BinanceReferenceNormalizationStatus.ERROR
    assert result.event is None
    assert result.error is not None
    assert result.error.code is code
    assert result.error.raw_sha256 == hashlib.sha256(payload).hexdigest()


def test_raw_sha_mismatch_is_provenance_error() -> None:
    frame = _raw(_bbo())
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

    result = normalize_binance_reference_frame(bad, _registry())

    assert result.status is BinanceReferenceNormalizationStatus.ERROR
    assert result.error is not None
    assert result.error.code is BinanceReferenceParseErrorCode.INVALID_PROVENANCE
