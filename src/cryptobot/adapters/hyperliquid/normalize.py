from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias, cast

from cryptobot.data.events import (
    AvailabilityKind,
    BBO,
    BookLevel,
    EventEnvelope,
    EventType,
    ExchangeTimestampSemantics,
    L2Snapshot,
    QualityFlag,
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


PARSE_VERSION = "hyperliquid-book-v1"
_TIMESTAMP_RESOLUTION_NS = 1_000_000
_TARGET_CHANNELS = frozenset({"l2Book", "bbo"})


class BookParseErrorCode(StrEnum):
    INVALID_JSON = "INVALID_JSON"
    INVALID_ENVELOPE = "INVALID_ENVELOPE"
    INVALID_DATA = "INVALID_DATA"
    UNSUPPORTED_COIN = "UNSUPPORTED_COIN"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    INVALID_LEVEL_SHAPE = "INVALID_LEVEL_SHAPE"
    INVALID_BBO_SHAPE = "INVALID_BBO_SHAPE"
    INVALID_NUMERIC = "INVALID_NUMERIC"
    INVALID_PROVENANCE = "INVALID_PROVENANCE"


class BookNormalizationStatus(StrEnum):
    EVENT = "EVENT"
    ERROR = "ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class BookParseError:
    code: BookParseErrorCode
    channel: str | None
    raw_segment_id: str
    raw_offset: int
    raw_sha256: str
    detail: str


NormalizedBookEvent: TypeAlias = L2Snapshot | BBO


@dataclass(frozen=True, slots=True)
class BookNormalizationResult:
    status: BookNormalizationStatus
    channel: str | None
    event: NormalizedBookEvent | None = None
    error: BookParseError | None = None

    def __post_init__(self) -> None:
        if self.status is BookNormalizationStatus.EVENT:
            if self.event is None or self.error is not None:
                raise ValueError("EVENT result requires exactly one event")
        elif self.status is BookNormalizationStatus.ERROR:
            if self.error is None or self.event is not None:
                raise ValueError("ERROR result requires exactly one error")
        elif self.event is not None or self.error is not None:
            raise ValueError("NOT_APPLICABLE result cannot contain event or error")


def normalize_book_frame(
    frame: RawFrame,
    registry: InstrumentRegistry,
) -> BookNormalizationResult:
    provenance_error = _validate_raw_provenance(frame)
    if provenance_error is not None:
        return _error_result(frame, None, BookParseErrorCode.INVALID_PROVENANCE, provenance_error)

    try:
        decoded = json.loads(frame.payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error_result(
            frame,
            None,
            BookParseErrorCode.INVALID_JSON,
            "payload is not valid UTF-8 JSON",
        )

    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        return _error_result(
            frame,
            None,
            BookParseErrorCode.INVALID_ENVELOPE,
            "top-level message must be a string-keyed object",
        )
    message = cast(dict[str, object], decoded)

    channel = message.get("channel")
    if not isinstance(channel, str):
        return _error_result(
            frame,
            None,
            BookParseErrorCode.INVALID_ENVELOPE,
            "top-level channel must be a string",
        )
    if channel not in _TARGET_CHANNELS:
        return BookNormalizationResult(
            status=BookNormalizationStatus.NOT_APPLICABLE,
            channel=channel,
        )

    data = message.get("data")
    if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
        return _error_result(
            frame,
            channel,
            BookParseErrorCode.INVALID_DATA,
            "target-channel data must be a string-keyed object",
        )
    payload = cast(dict[str, object], data)

    coin = payload.get("coin")
    if not isinstance(coin, str) or not coin:
        return _error_result(
            frame,
            channel,
            BookParseErrorCode.UNSUPPORTED_COIN,
            "data.coin must be a non-empty string",
        )
    instrument = _instrument_for_coin(registry, coin)
    if instrument is None:
        return _error_result(
            frame,
            channel,
            BookParseErrorCode.UNSUPPORTED_COIN,
            f"coin is not a configured Hyperliquid mainnet perpetual: {coin}",
        )

    time_value = payload.get("time")
    if (
        isinstance(time_value, bool)
        or not isinstance(time_value, int)
        or time_value < 0
    ):
        return _error_result(
            frame,
            channel,
            BookParseErrorCode.INVALID_TIMESTAMP,
            "data.time must be a non-negative integer Unix millisecond value",
        )
    exchange_ts_ns = time_value * _TIMESTAMP_RESOLUTION_NS

    availability = _availability_kind(frame)
    if availability is None:
        return _error_result(
            frame,
            channel,
            BookParseErrorCode.INVALID_PROVENANCE,
            "capture_flags do not identify a supported availability kind",
        )

    if channel == "l2Book":
        return _normalize_l2(
            frame=frame,
            payload=payload,
            instrument=instrument,
            exchange_ts_ns=exchange_ts_ns,
            availability=availability,
        )
    return _normalize_bbo(
        frame=frame,
        payload=payload,
        instrument=instrument,
        exchange_ts_ns=exchange_ts_ns,
        availability=availability,
    )


def serialize_normalized_book_event(event: NormalizedBookEvent) -> bytes:
    envelope = event.envelope.as_dict()
    if isinstance(event, L2Snapshot):
        payload: dict[str, object] = {
            "bids": [_level_as_dict(level) for level in event.bids],
            "asks": [_level_as_dict(level) for level in event.asks],
            "depth_limit": event.depth_limit,
            "aggregation": event.aggregation,
            "full_snapshot": event.full_snapshot,
        }
    else:
        payload = {
            "bid_price": _decimal_or_none(event.bid_price),
            "bid_size": _decimal_or_none(event.bid_size),
            "ask_price": _decimal_or_none(event.ask_price),
            "ask_size": _decimal_or_none(event.ask_size),
        }
    return json.dumps(
        {"envelope": envelope, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def _normalize_l2(
    *,
    frame: RawFrame,
    payload: Mapping[str, object],
    instrument: Instrument,
    exchange_ts_ns: int,
    availability: AvailabilityKind,
) -> BookNormalizationResult:
    levels = payload.get("levels")
    if not isinstance(levels, list) or len(levels) != 2:
        return _error_result(
            frame,
            "l2Book",
            BookParseErrorCode.INVALID_LEVEL_SHAPE,
            "data.levels must contain exactly [bids, asks]",
        )
    bids_raw, asks_raw = levels
    if not isinstance(bids_raw, list) or not isinstance(asks_raw, list):
        return _error_result(
            frame,
            "l2Book",
            BookParseErrorCode.INVALID_LEVEL_SHAPE,
            "both l2Book sides must be arrays",
        )

    try:
        bids = tuple(_parse_level(level) for level in bids_raw)
        asks = tuple(_parse_level(level) for level in asks_raw)
    except _LevelShapeError as exc:
        return _error_result(
            frame,
            "l2Book",
            BookParseErrorCode.INVALID_LEVEL_SHAPE,
            str(exc),
        )
    except NumericValidationError as exc:
        return _error_result(
            frame,
            "l2Book",
            BookParseErrorCode.INVALID_NUMERIC,
            str(exc),
        )

    quality = _book_quality_flags(bids, asks)
    envelope = _envelope(
        frame=frame,
        instrument=instrument,
        event_type=EventType.L2_SNAPSHOT,
        exchange_ts_ns=exchange_ts_ns,
        availability=availability,
        quality_flags=quality,
    )
    event = L2Snapshot(
        envelope=envelope,
        bids=bids,
        asks=asks,
        depth_limit=None,
        aggregation=None,
        full_snapshot=True,
    )
    return BookNormalizationResult(
        status=BookNormalizationStatus.EVENT,
        channel="l2Book",
        event=event,
    )


def _normalize_bbo(
    *,
    frame: RawFrame,
    payload: Mapping[str, object],
    instrument: Instrument,
    exchange_ts_ns: int,
    availability: AvailabilityKind,
) -> BookNormalizationResult:
    bbo = payload.get("bbo")
    if not isinstance(bbo, list) or len(bbo) != 2:
        return _error_result(
            frame,
            "bbo",
            BookParseErrorCode.INVALID_BBO_SHAPE,
            "data.bbo must contain exactly [best_bid, best_ask]",
        )

    try:
        bid = None if bbo[0] is None else _parse_level(bbo[0])
        ask = None if bbo[1] is None else _parse_level(bbo[1])
    except _LevelShapeError as exc:
        return _error_result(
            frame,
            "bbo",
            BookParseErrorCode.INVALID_BBO_SHAPE,
            str(exc),
        )
    except NumericValidationError as exc:
        return _error_result(
            frame,
            "bbo",
            BookParseErrorCode.INVALID_NUMERIC,
            str(exc),
        )

    quality = QualityFlag.NONE
    if bid is not None and ask is not None and bid.price >= ask.price:
        quality |= QualityFlag.SUSPECT

    envelope = _envelope(
        frame=frame,
        instrument=instrument,
        event_type=EventType.BBO,
        exchange_ts_ns=exchange_ts_ns,
        availability=availability,
        quality_flags=quality,
    )
    event = BBO(
        envelope=envelope,
        bid_price=None if bid is None else bid.price,
        bid_size=None if bid is None else bid.size,
        ask_price=None if ask is None else ask.price,
        ask_size=None if ask is None else ask.size,
    )
    return BookNormalizationResult(
        status=BookNormalizationStatus.EVENT,
        channel="bbo",
        event=event,
    )


class _LevelShapeError(ValueError):
    pass


def _parse_level(raw: object) -> BookLevel:
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise _LevelShapeError("book level must be a string-keyed object")
    level = cast(dict[str, object], raw)
    for field in ("px", "sz", "n"):
        if field not in level:
            raise _LevelShapeError(f"book level is missing required field: {field}")

    px = level["px"]
    sz = level["sz"]
    n = level["n"]
    if not isinstance(px, str) or not isinstance(sz, str):
        raise _LevelShapeError("book level px and sz must be strings")
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise _LevelShapeError("book level n must be a non-negative integer")

    price = parse_exact_decimal(px)
    size = parse_exact_decimal(sz)
    if price <= 0:
        raise NumericValidationError("book level px must be positive")
    if size <= 0:
        raise NumericValidationError("book level sz must be positive")
    return BookLevel(price=price, size=size, order_count=n)


def _book_quality_flags(
    bids: tuple[BookLevel, ...],
    asks: tuple[BookLevel, ...],
) -> QualityFlag:
    suspect = False
    if any(left.price < right.price for left, right in zip(bids, bids[1:], strict=False)):
        suspect = True
    if any(left.price > right.price for left, right in zip(asks, asks[1:], strict=False)):
        suspect = True
    if bids and asks and bids[0].price >= asks[0].price:
        suspect = True
    return QualityFlag.SUSPECT if suspect else QualityFlag.NONE


def _envelope(
    *,
    frame: RawFrame,
    instrument: Instrument,
    event_type: EventType,
    exchange_ts_ns: int,
    availability: AvailabilityKind,
    quality_flags: QualityFlag,
) -> EventEnvelope:
    return EventEnvelope(
        schema_version=1,
        event_id=_event_id(frame, event_type),
        event_type=event_type,
        source=frame.metadata.source_id,
        instrument_id=instrument.instrument_id,
        native_symbol=instrument.native_symbol,
        exchange_ts_ns=exchange_ts_ns,
        exchange_ts_resolution_ns=_TIMESTAMP_RESOLUTION_NS,
        exchange_ts_semantics=ExchangeTimestampSemantics.UNKNOWN,
        recv_wall_ns=frame.metadata.recv_wall_ns,
        recv_mono_ns=frame.metadata.recv_mono_ns,
        host_id=frame.metadata.host_id,
        boot_id=frame.metadata.boot_id,
        connection_id=frame.metadata.connection_id,
        ingest_seq=frame.metadata.ingest_seq,
        native_sequence=None,
        native_update_id=None,
        raw_segment_id=frame.ref.segment_id,
        raw_offset=frame.ref.offset,
        raw_sha256=frame.ref.payload_sha256,
        parse_version=PARSE_VERSION,
        quality_flags=quality_flags,
        availability_kind=availability,
    )


def _event_id(frame: RawFrame, event_type: EventType) -> str:
    material = "\0".join(
        (
            PARSE_VERSION,
            event_type.value,
            frame.ref.segment_id,
            str(frame.ref.offset),
            frame.ref.payload_sha256,
        )
    ).encode()
    return hashlib.sha256(material).hexdigest()


def _instrument_for_coin(
    registry: InstrumentRegistry,
    coin: str,
) -> Instrument | None:
    matches = [
        instrument
        for instrument in registry.instruments
        if instrument.venue == "hyperliquid"
        and instrument.environment is Environment.MAINNET
        and instrument.product_type is ProductType.PERPETUAL
        and instrument.native_symbol == coin
    ]
    return matches[0] if len(matches) == 1 else None


def _availability_kind(frame: RawFrame) -> AvailabilityKind | None:
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
    actual_sha = hashlib.sha256(frame.payload).hexdigest()
    if actual_sha != frame.ref.payload_sha256:
        return "raw payload SHA-256 does not match payload bytes"
    return None


def _error_result(
    frame: RawFrame,
    channel: str | None,
    code: BookParseErrorCode,
    detail: str,
) -> BookNormalizationResult:
    return BookNormalizationResult(
        status=BookNormalizationStatus.ERROR,
        channel=channel,
        error=BookParseError(
            code=code,
            channel=channel,
            raw_segment_id=frame.ref.segment_id,
            raw_offset=frame.ref.offset,
            raw_sha256=frame.ref.payload_sha256,
            detail=detail,
        ),
    )


def _level_as_dict(level: BookLevel) -> dict[str, object]:
    return {
        "price": serialize_exact_decimal(level.price),
        "size": serialize_exact_decimal(level.size),
        "order_count": level.order_count,
    }


def _decimal_or_none(value: object) -> str | None:
    if value is None:
        return None
    return serialize_exact_decimal(cast("str | int", value))
