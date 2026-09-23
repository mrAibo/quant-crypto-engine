from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import cast

from cryptobot.data.events import (
    AvailabilityKind,
    EventEnvelope,
    EventType,
    ExchangeTimestampSemantics,
    QualityFlag,
    ReferenceBBO,
    ReferenceTrade,
    TradeSide,
)
from cryptobot.data.instruments import (
    Environment,
    Instrument,
    InstrumentRegistry,
    ProductType,
)
from cryptobot.data.numeric import (
    NumericValidationError,
    parse_exact_decimal,
    serialize_exact_decimal,
)
from cryptobot.data.rawlog import RawFrame

PARSE_VERSION = "binance-usdm-reference-v1"
_SOURCE_VENUE = "binance_usdm"
_TIMESTAMP_RESOLUTION_NS = 1_000_000


class BinanceReferenceParseErrorCode(StrEnum):
    INVALID_JSON = "INVALID_JSON"
    INVALID_ENVELOPE = "INVALID_ENVELOPE"
    UNSUPPORTED_STREAM = "UNSUPPORTED_STREAM"
    UNSUPPORTED_SYMBOL = "UNSUPPORTED_SYMBOL"
    WRONG_SYMBOL_TYPE = "WRONG_SYMBOL_TYPE"
    INVALID_EVENT_TIMESTAMP = "INVALID_EVENT_TIMESTAMP"
    INVALID_TRADE_TIMESTAMP = "INVALID_TRADE_TIMESTAMP"
    INVALID_NATIVE_ID = "INVALID_NATIVE_ID"
    INVALID_NUMERIC = "INVALID_NUMERIC"
    INVALID_MAKER_FLAG = "INVALID_MAKER_FLAG"
    INVALID_PROVENANCE = "INVALID_PROVENANCE"


class BinanceReferenceNormalizationStatus(StrEnum):
    EVENT = "EVENT"
    ERROR = "ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


type ReferenceEvent = ReferenceBBO | ReferenceTrade


@dataclass(frozen=True, slots=True)
class BinanceReferenceParseError:
    code: BinanceReferenceParseErrorCode
    stream: str | None
    raw_segment_id: str
    raw_offset: int
    raw_sha256: str
    detail: str


@dataclass(frozen=True, slots=True)
class BinanceReferenceNormalizationResult:
    status: BinanceReferenceNormalizationStatus
    stream: str | None
    event: ReferenceEvent | None = None
    error: BinanceReferenceParseError | None = None

    def __post_init__(self) -> None:
        if self.status is BinanceReferenceNormalizationStatus.EVENT:
            if self.event is None or self.error is not None:
                raise ValueError("EVENT result requires exactly one event")
        elif self.status is BinanceReferenceNormalizationStatus.ERROR:
            if self.error is None or self.event is not None:
                raise ValueError("ERROR result requires exactly one error")
        elif self.event is not None or self.error is not None:
            raise ValueError("NOT_APPLICABLE result cannot contain event or error")


def normalize_binance_reference_frame(
    frame: RawFrame,
    registry: InstrumentRegistry,
) -> BinanceReferenceNormalizationResult:
    provenance_error = _validate_raw_provenance(frame)
    if provenance_error is not None:
        return _error(
            frame,
            None,
            BinanceReferenceParseErrorCode.INVALID_PROVENANCE,
            provenance_error,
        )
    availability = _availability(frame)
    if availability is None:
        return _error(
            frame,
            None,
            BinanceReferenceParseErrorCode.INVALID_PROVENANCE,
            "capture_flags do not identify a supported availability kind",
        )
    try:
        decoded = json.loads(frame.payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error(
            frame,
            None,
            BinanceReferenceParseErrorCode.INVALID_JSON,
            "payload is not valid UTF-8 JSON",
        )
    if not isinstance(decoded, dict) or not all(isinstance(k, str) for k in decoded):
        return _error(
            frame, None, BinanceReferenceParseErrorCode.INVALID_ENVELOPE,
            "top-level message must be a string-keyed object"
        )
    obj = cast(dict[str, object], decoded)
    if "result" in obj and "id" in obj:
        return BinanceReferenceNormalizationResult(
            status=BinanceReferenceNormalizationStatus.NOT_APPLICABLE, stream=None
        )
    stream = obj.get("stream")
    data = obj.get("data")
    if not isinstance(stream, str) or not isinstance(data, dict) or not all(
        isinstance(k, str) for k in data
    ):
        return _error(
            frame, None, BinanceReferenceParseErrorCode.INVALID_ENVELOPE,
            "combined stream message must contain stream and object data"
        )
    payload = cast(dict[str, object], data)
    event_type = payload.get("e")
    if event_type == "bookTicker":
        return _normalize_book_ticker(frame, stream, payload, registry, availability)
    if event_type == "aggTrade":
        return _normalize_agg_trade(frame, stream, payload, registry, availability)
    return BinanceReferenceNormalizationResult(
        status=BinanceReferenceNormalizationStatus.NOT_APPLICABLE, stream=stream
    )


def serialize_binance_reference_event(event: ReferenceEvent) -> bytes:
    item: dict[str, object] = {"envelope": event.envelope.as_dict()}
    if isinstance(event, ReferenceBBO):
        item.update(
            {
                "bid_price": _decimal(event.bid_price),
                "bid_size": _decimal(event.bid_size),
                "ask_price": _decimal(event.ask_price),
                "ask_size": _decimal(event.ask_size),
                "sampling_mode": event.sampling_mode,
            }
        )
    else:
        item.update(
            {
                "price": serialize_exact_decimal(event.price),
                "size": serialize_exact_decimal(event.size),
                "native_side": event.native_side,
                "aggressor_side": event.aggressor_side.value,
                "trade_id": event.trade_id,
            }
        )
    return json.dumps(item, sort_keys=True, separators=(",", ":")).encode()


def _normalize_book_ticker(
    frame: RawFrame,
    stream: str,
    payload: dict[str, object],
    registry: InstrumentRegistry,
    availability: AvailabilityKind,
) -> BinanceReferenceNormalizationResult:
    instrument = _instrument(payload, registry, frame, stream)
    if isinstance(instrument, BinanceReferenceNormalizationResult):
        return instrument
    expected_stream = f"{instrument.native_symbol.lower()}@bookTicker"
    if stream != expected_stream:
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.UNSUPPORTED_STREAM,
            f"bookTicker wrapper stream must be {expected_stream}",
        )
    if payload.get("ps") != instrument.native_symbol:
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.UNSUPPORTED_SYMBOL,
            "bookTicker ps must match the USD-M symbol",
        )
    if not _is_int(payload.get("E")):
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.INVALID_EVENT_TIMESTAMP,
            "E must be non-negative integer milliseconds",
        )
    if not _is_int(payload.get("T")):
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.INVALID_EVENT_TIMESTAMP,
            "T must be non-negative integer milliseconds",
        )
    update_id = payload.get("u")
    if not _is_int(update_id):
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.INVALID_NATIVE_ID,
            "u must be a non-negative integer",
        )
    try:
        bid_price = _positive_decimal(payload.get("b"), "b")
        bid_size = _positive_decimal(payload.get("B"), "B")
        ask_price = _positive_decimal(payload.get("a"), "a")
        ask_size = _positive_decimal(payload.get("A"), "A")
    except (TypeError, NumericValidationError) as exc:
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.INVALID_NUMERIC,
            str(exc),
        )
    quality = QualityFlag.SUSPECT if bid_price >= ask_price else QualityFlag.NONE
    event = ReferenceBBO(
        envelope=_envelope(
            frame=frame,
            instrument=instrument,
            event_type=EventType.REFERENCE_BBO,
            exchange_ts_ms=cast(int, payload["E"]),
            semantics=ExchangeTimestampSemantics.EVENT_TIME,
            native_update_id=str(update_id),
            quality=quality,
            availability=availability,
        ),
        bid_price=bid_price,
        bid_size=bid_size,
        ask_price=ask_price,
        ask_size=ask_size,
        sampling_mode="REALTIME_BOOK_TICKER",
    )
    return BinanceReferenceNormalizationResult(
        status=BinanceReferenceNormalizationStatus.EVENT, stream=stream, event=event
    )


def _normalize_agg_trade(
    frame: RawFrame,
    stream: str,
    payload: dict[str, object],
    registry: InstrumentRegistry,
    availability: AvailabilityKind,
) -> BinanceReferenceNormalizationResult:
    instrument = _instrument(payload, registry, frame, stream)
    if isinstance(instrument, BinanceReferenceNormalizationResult):
        return instrument
    expected_stream = f"{instrument.native_symbol.lower()}@aggTrade"
    if stream != expected_stream:
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.UNSUPPORTED_STREAM,
            f"aggTrade wrapper stream must be {expected_stream}",
        )
    if not _is_int(payload.get("E")):
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.INVALID_EVENT_TIMESTAMP,
            "E must be non-negative integer milliseconds",
        )
    trade_time = payload.get("T")
    if not _is_int(trade_time):
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.INVALID_TRADE_TIMESTAMP,
            "T must be non-negative integer milliseconds",
        )
    aggregate_id = payload.get("a")
    if not _is_int(aggregate_id):
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.INVALID_NATIVE_ID,
            "a must be a non-negative integer",
        )
    first_id = payload.get("f")
    last_id = payload.get("l")
    if not _is_int(first_id) or not _is_int(last_id) or cast(int, first_id) > cast(int, last_id):
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.INVALID_NATIVE_ID,
            "f/l must be ordered non-negative integer trade IDs",
        )
    try:
        _nonnegative_decimal(payload.get("nq"), "nq")
    except (TypeError, NumericValidationError) as exc:
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.INVALID_NUMERIC,
            str(exc),
        )
    maker = payload.get("m")
    if not isinstance(maker, bool):
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.INVALID_MAKER_FLAG,
            "m must be boolean",
        )
    try:
        price = _positive_decimal(payload.get("p"), "p")
        size = _positive_decimal(payload.get("q"), "q")
    except (TypeError, NumericValidationError) as exc:
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.INVALID_NUMERIC,
            str(exc),
        )
    native_side = "BUYER_MAKER" if maker else "BUYER_TAKER"
    aggressor = TradeSide.SELL if maker else TradeSide.BUY
    trade_id = f"{instrument.native_symbol}:{aggregate_id}"
    event = ReferenceTrade(
        envelope=_envelope(
            frame=frame,
            instrument=instrument,
            event_type=EventType.REFERENCE_TRADE,
            exchange_ts_ms=cast(int, trade_time),
            semantics=ExchangeTimestampSemantics.TRADE_TIME,
            native_update_id=trade_id,
            quality=QualityFlag.NONE,
            availability=availability,
        ),
        price=price,
        size=size,
        native_side=native_side,
        aggressor_side=aggressor,
        trade_id=trade_id,
    )
    return BinanceReferenceNormalizationResult(
        status=BinanceReferenceNormalizationStatus.EVENT, stream=stream, event=event
    )


def _instrument(
    payload: dict[str, object],
    registry: InstrumentRegistry,
    frame: RawFrame,
    stream: str,
) -> Instrument | BinanceReferenceNormalizationResult:
    symbol = payload.get("s")
    if not isinstance(symbol, str):
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.UNSUPPORTED_SYMBOL,
            "s must be string",
        )
    st = payload.get("st")
    if isinstance(st, bool) or not isinstance(st, int) or st != 1:
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.WRONG_SYMBOL_TYPE,
            "st must be 1 for USD-M",
        )
    matches = [
        item
        for item in registry.instruments
        if item.venue == _SOURCE_VENUE
        and item.environment is Environment.REFERENCE
        and item.product_type is ProductType.PERPETUAL
        and item.native_symbol == symbol
    ]
    if len(matches) != 1:
        return _error(
            frame,
            stream,
            BinanceReferenceParseErrorCode.UNSUPPORTED_SYMBOL,
            f"unsupported Binance USD-M reference symbol: {symbol}",
        )
    return matches[0]


def _envelope(
    *,
    frame: RawFrame,
    instrument: Instrument,
    event_type: EventType,
    exchange_ts_ms: int,
    semantics: ExchangeTimestampSemantics,
    native_update_id: str,
    quality: QualityFlag,
    availability: AvailabilityKind,
) -> EventEnvelope:
    return EventEnvelope(
        schema_version=1,
        event_id=_event_id(frame, event_type, native_update_id),
        event_type=event_type,
        source=frame.metadata.source_id,
        instrument_id=instrument.instrument_id,
        native_symbol=instrument.native_symbol,
        exchange_ts_ns=exchange_ts_ms * _TIMESTAMP_RESOLUTION_NS,
        exchange_ts_resolution_ns=_TIMESTAMP_RESOLUTION_NS,
        exchange_ts_semantics=semantics,
        recv_wall_ns=frame.metadata.recv_wall_ns,
        recv_mono_ns=frame.metadata.recv_mono_ns,
        host_id=frame.metadata.host_id,
        boot_id=frame.metadata.boot_id,
        connection_id=frame.metadata.connection_id,
        ingest_seq=frame.metadata.ingest_seq,
        native_sequence=None,
        native_update_id=native_update_id,
        raw_segment_id=frame.ref.segment_id,
        raw_offset=frame.ref.offset,
        raw_sha256=frame.ref.payload_sha256,
        parse_version=PARSE_VERSION,
        quality_flags=quality,
        availability_kind=availability,
    )


def _event_id(frame: RawFrame, event_type: EventType, native_update_id: str) -> str:
    material = "\0".join(
        (
            PARSE_VERSION,
            event_type.value,
            frame.ref.segment_id,
            str(frame.ref.offset),
            frame.ref.payload_sha256,
            native_update_id,
        )
    ).encode()
    return hashlib.sha256(material).hexdigest()


def _positive_decimal(raw: object, field: str) -> Decimal:
    if not isinstance(raw, str):
        raise TypeError(f"{field} must be string")
    value = parse_exact_decimal(raw)
    if value <= 0:
        raise NumericValidationError(f"{field} must be positive")
    return value


def _nonnegative_decimal(raw: object, field: str) -> Decimal:
    if not isinstance(raw, str):
        raise TypeError(f"{field} must be string")
    value = parse_exact_decimal(raw)
    if value < 0:
        raise NumericValidationError(f"{field} must be non-negative")
    return value


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _availability(frame: RawFrame) -> AvailabilityKind | None:
    flags = set(frame.metadata.capture_flags)
    if "LIVE_CAPTURE" in flags:
        return AvailabilityKind.LIVE_CAPTURE
    if "LATE_BACKFILL" in flags:
        return AvailabilityKind.LATE_BACKFILL
    if "HISTORICAL_IMPORT" in flags:
        return AvailabilityKind.HISTORICAL_IMPORT
    return None


def _validate_raw_provenance(frame: RawFrame) -> str | None:
    if not frame.ref.segment_id.strip():
        return "raw segment_id must be non-empty"
    if frame.ref.offset < 0:
        return "raw offset must be non-negative"
    if hashlib.sha256(frame.payload).hexdigest() != frame.ref.payload_sha256:
        return "raw payload SHA-256 does not match payload bytes"
    return None


def _error(
    frame: RawFrame,
    stream: str | None,
    code: BinanceReferenceParseErrorCode,
    detail: str,
) -> BinanceReferenceNormalizationResult:
    return BinanceReferenceNormalizationResult(
        status=BinanceReferenceNormalizationStatus.ERROR,
        stream=stream,
        error=BinanceReferenceParseError(
            code=code,
            stream=stream,
            raw_segment_id=frame.ref.segment_id,
            raw_offset=frame.ref.offset,
            raw_sha256=frame.ref.payload_sha256,
            detail=detail,
        ),
    )


def _decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return serialize_exact_decimal(value)
