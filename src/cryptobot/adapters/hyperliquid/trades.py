from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from cryptobot.data.events import (
    AvailabilityKind,
    EventEnvelope,
    EventType,
    ExchangeTimestampSemantics,
    QualityFlag,
    Trade,
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

PARSE_VERSION = "hyperliquid-trade-v1"
_TIMESTAMP_RESOLUTION_NS = 1_000_000
_TARGET_CHANNEL = "trades"
_VALID_NATIVE_SIDES = frozenset({"A", "B"})


class TradeParseErrorCode(StrEnum):
    INVALID_JSON = "INVALID_JSON"
    INVALID_ENVELOPE = "INVALID_ENVELOPE"
    INVALID_TRADES_ARRAY = "INVALID_TRADES_ARRAY"
    INVALID_TRADE_OBJECT = "INVALID_TRADE_OBJECT"
    UNSUPPORTED_COIN = "UNSUPPORTED_COIN"
    INVALID_NATIVE_SIDE = "INVALID_NATIVE_SIDE"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    INVALID_NUMERIC = "INVALID_NUMERIC"
    INVALID_TID = "INVALID_TID"
    INVALID_TRANSACTION_HASH = "INVALID_TRANSACTION_HASH"
    INVALID_USERS = "INVALID_USERS"
    INVALID_PROVENANCE = "INVALID_PROVENANCE"


class TradeNormalizationStatus(StrEnum):
    EVENTS = "EVENTS"
    ERROR = "ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class TradeParseError:
    code: TradeParseErrorCode
    channel: str | None
    trade_index: int | None
    raw_segment_id: str
    raw_offset: int
    raw_sha256: str
    detail: str


@dataclass(frozen=True, slots=True)
class TradeNormalizationResult:
    status: TradeNormalizationStatus
    channel: str | None
    events: tuple[Trade, ...] = ()
    error: TradeParseError | None = None

    def __post_init__(self) -> None:
        if self.status is TradeNormalizationStatus.EVENTS:
            if self.error is not None:
                raise ValueError("EVENTS result cannot contain an error")
        elif self.status is TradeNormalizationStatus.ERROR:
            if self.error is None or self.events:
                raise ValueError("ERROR result requires exactly one error and no events")
        elif self.events or self.error is not None:
            raise ValueError("NOT_APPLICABLE result cannot contain events or error")


def normalize_trade_frame(
    frame: RawFrame,
    registry: InstrumentRegistry,
) -> TradeNormalizationResult:
    provenance_error = _validate_raw_provenance(frame)
    if provenance_error is not None:
        return _error_result(
            frame,
            None,
            None,
            TradeParseErrorCode.INVALID_PROVENANCE,
            provenance_error,
        )

    try:
        decoded = json.loads(frame.payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error_result(
            frame,
            None,
            None,
            TradeParseErrorCode.INVALID_JSON,
            "payload is not valid UTF-8 JSON",
        )

    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        return _error_result(
            frame,
            None,
            None,
            TradeParseErrorCode.INVALID_ENVELOPE,
            "top-level message must be a string-keyed object",
        )
    message = cast(dict[str, object], decoded)

    channel = message.get("channel")
    if not isinstance(channel, str):
        return _error_result(
            frame,
            None,
            None,
            TradeParseErrorCode.INVALID_ENVELOPE,
            "top-level channel must be a string",
        )
    if channel != _TARGET_CHANNEL:
        return TradeNormalizationResult(
            status=TradeNormalizationStatus.NOT_APPLICABLE,
            channel=channel,
        )

    data = message.get("data")
    if not isinstance(data, list):
        return _error_result(
            frame,
            channel,
            None,
            TradeParseErrorCode.INVALID_TRADES_ARRAY,
            "trades data must be an array",
        )

    availability = _availability_kind(frame)
    if availability is None:
        return _error_result(
            frame,
            channel,
            None,
            TradeParseErrorCode.INVALID_PROVENANCE,
            "capture_flags do not identify a supported availability kind",
        )

    events: list[Trade] = []
    for index, raw_trade in enumerate(data):
        parsed = _parse_trade(
            frame=frame,
            raw_trade=raw_trade,
            trade_index=index,
            registry=registry,
            availability=availability,
        )
        if isinstance(parsed, TradeParseError):
            return TradeNormalizationResult(
                status=TradeNormalizationStatus.ERROR,
                channel=channel,
                error=parsed,
            )
        events.append(parsed)

    return TradeNormalizationResult(
        status=TradeNormalizationStatus.EVENTS,
        channel=channel,
        events=tuple(events),
    )


def serialize_normalized_trades(events: tuple[Trade, ...]) -> bytes:
    payload = []
    for event in events:
        payload.append(
            {
                "envelope": event.envelope.as_dict(),
                "price": serialize_exact_decimal(event.price),
                "size": serialize_exact_decimal(event.size),
                "native_side": event.native_side,
                "aggressor_side": event.aggressor_side.value,
                "trade_id": event.trade_id,
                "transaction_hash": event.transaction_hash,
            }
        )
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def _parse_trade(
    *,
    frame: RawFrame,
    raw_trade: object,
    trade_index: int,
    registry: InstrumentRegistry,
    availability: AvailabilityKind,
) -> Trade | TradeParseError:
    if not isinstance(raw_trade, dict) or not all(isinstance(key, str) for key in raw_trade):
        return _parse_error(
            frame,
            trade_index,
            TradeParseErrorCode.INVALID_TRADE_OBJECT,
            "trade element must be a string-keyed object",
        )
    trade = cast(dict[str, object], raw_trade)

    required = ("coin", "side", "px", "sz", "hash", "time", "tid", "users")
    missing = [field for field in required if field not in trade]
    if missing:
        return _parse_error(
            frame,
            trade_index,
            TradeParseErrorCode.INVALID_TRADE_OBJECT,
            "trade element is missing required fields: " + ",".join(sorted(missing)),
        )

    coin = trade["coin"]
    if not isinstance(coin, str) or not coin:
        return _parse_error(
            frame,
            trade_index,
            TradeParseErrorCode.UNSUPPORTED_COIN,
            "trade coin must be a non-empty string",
        )
    instrument = _instrument_for_coin(registry, coin)
    if instrument is None:
        return _parse_error(
            frame,
            trade_index,
            TradeParseErrorCode.UNSUPPORTED_COIN,
            f"coin is not a configured Hyperliquid mainnet perpetual: {coin}",
        )

    native_side = trade["side"]
    if not isinstance(native_side, str) or native_side not in _VALID_NATIVE_SIDES:
        return _parse_error(
            frame,
            trade_index,
            TradeParseErrorCode.INVALID_NATIVE_SIDE,
            "trade side must be official native value A or B",
        )

    px = trade["px"]
    sz = trade["sz"]
    if not isinstance(px, str) or not isinstance(sz, str):
        return _parse_error(
            frame,
            trade_index,
            TradeParseErrorCode.INVALID_NUMERIC,
            "trade px and sz must be strings",
        )
    try:
        price = parse_exact_decimal(px)
        size = parse_exact_decimal(sz)
    except NumericValidationError as exc:
        return _parse_error(
            frame,
            trade_index,
            TradeParseErrorCode.INVALID_NUMERIC,
            str(exc),
        )
    if price <= 0 or size <= 0:
        return _parse_error(
            frame,
            trade_index,
            TradeParseErrorCode.INVALID_NUMERIC,
            "trade px and sz must be positive",
        )

    time_value = trade["time"]
    if isinstance(time_value, bool) or not isinstance(time_value, int) or time_value < 0:
        return _parse_error(
            frame,
            trade_index,
            TradeParseErrorCode.INVALID_TIMESTAMP,
            "trade time must be a non-negative integer Unix millisecond value",
        )

    tid = trade["tid"]
    if isinstance(tid, bool) or not isinstance(tid, int) or tid < 0 or tid >= (1 << 50):
        return _parse_error(
            frame,
            trade_index,
            TradeParseErrorCode.INVALID_TID,
            "trade tid must be a non-negative integer fitting the documented 50-bit range",
        )

    transaction_hash = trade["hash"]
    if not isinstance(transaction_hash, str) or not transaction_hash.strip():
        return _parse_error(
            frame,
            trade_index,
            TradeParseErrorCode.INVALID_TRANSACTION_HASH,
            "trade hash must be a non-empty string",
        )

    users = trade["users"]
    if (
        not isinstance(users, list)
        or len(users) != 2
        or not all(isinstance(user, str) and user.strip() for user in users)
    ):
        return _parse_error(
            frame,
            trade_index,
            TradeParseErrorCode.INVALID_USERS,
            "trade users must contain exactly two non-empty strings [buyer, seller]",
        )

    trade_id = _stable_trade_id(time_value=time_value, coin=coin, tid=tid)
    envelope = EventEnvelope(
        schema_version=1,
        event_id=_event_id(
            frame=frame,
            trade_index=trade_index,
            trade_id=trade_id,
        ),
        event_type=EventType.TRADE,
        source=frame.metadata.source_id,
        instrument_id=instrument.instrument_id,
        native_symbol=instrument.native_symbol,
        exchange_ts_ns=time_value * _TIMESTAMP_RESOLUTION_NS,
        exchange_ts_resolution_ns=_TIMESTAMP_RESOLUTION_NS,
        exchange_ts_semantics=ExchangeTimestampSemantics.UNKNOWN,
        recv_wall_ns=frame.metadata.recv_wall_ns,
        recv_mono_ns=frame.metadata.recv_mono_ns,
        host_id=frame.metadata.host_id,
        boot_id=frame.metadata.boot_id,
        connection_id=frame.metadata.connection_id,
        ingest_seq=frame.metadata.ingest_seq,
        native_sequence=None,
        native_update_id=trade_id,
        raw_segment_id=frame.ref.segment_id,
        raw_offset=frame.ref.offset,
        raw_sha256=frame.ref.payload_sha256,
        parse_version=PARSE_VERSION,
        quality_flags=QualityFlag.NONE,
        availability_kind=availability,
    )
    return Trade(
        envelope=envelope,
        price=price,
        size=size,
        native_side=native_side,
        aggressor_side=TradeSide.UNKNOWN,
        trade_id=trade_id,
        transaction_hash=transaction_hash,
    )


def _stable_trade_id(*, time_value: int, coin: str, tid: int) -> str:
    return f"{time_value}:{coin}:{tid}"


def _event_id(
    *,
    frame: RawFrame,
    trade_index: int,
    trade_id: str,
) -> str:
    material = "\0".join(
        (
            PARSE_VERSION,
            EventType.TRADE.value,
            frame.ref.segment_id,
            str(frame.ref.offset),
            frame.ref.payload_sha256,
            str(trade_index),
            trade_id,
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
    trade_index: int | None,
    code: TradeParseErrorCode,
    detail: str,
) -> TradeNormalizationResult:
    return TradeNormalizationResult(
        status=TradeNormalizationStatus.ERROR,
        channel=channel,
        error=TradeParseError(
            code=code,
            channel=channel,
            trade_index=trade_index,
            raw_segment_id=frame.ref.segment_id,
            raw_offset=frame.ref.offset,
            raw_sha256=frame.ref.payload_sha256,
            detail=detail,
        ),
    )


def _parse_error(
    frame: RawFrame,
    trade_index: int,
    code: TradeParseErrorCode,
    detail: str,
) -> TradeParseError:
    return TradeParseError(
        code=code,
        channel=_TARGET_CHANNEL,
        trade_index=trade_index,
        raw_segment_id=frame.ref.segment_id,
        raw_offset=frame.ref.offset,
        raw_sha256=frame.ref.payload_sha256,
        detail=detail,
    )
