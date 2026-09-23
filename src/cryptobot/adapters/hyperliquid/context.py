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
    FundingObservationKind,
    FundingRateObservation,
    MarkPrice,
    OraclePrice,
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

PARSE_VERSION = "hyperliquid-context-v1"
_TARGET_CHANNEL = "activeAssetCtx"
_FUNDING_PERIOD_SECONDS = 3600


class ContextParseErrorCode(StrEnum):
    INVALID_JSON = "INVALID_JSON"
    INVALID_ENVELOPE = "INVALID_ENVELOPE"
    INVALID_CONTEXT_OBJECT = "INVALID_CONTEXT_OBJECT"
    UNSUPPORTED_COIN = "UNSUPPORTED_COIN"
    INVALID_FUNDING = "INVALID_FUNDING"
    INVALID_MARK_PRICE = "INVALID_MARK_PRICE"
    INVALID_ORACLE_PRICE = "INVALID_ORACLE_PRICE"
    INVALID_PROVENANCE = "INVALID_PROVENANCE"


class ContextNormalizationStatus(StrEnum):
    EVENTS = "EVENTS"
    ERROR = "ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class ContextParseError:
    code: ContextParseErrorCode
    channel: str | None
    raw_segment_id: str
    raw_offset: int
    raw_sha256: str
    detail: str


type ContextEvent = FundingRateObservation | MarkPrice | OraclePrice


@dataclass(frozen=True, slots=True)
class ContextNormalizationResult:
    status: ContextNormalizationStatus
    channel: str | None
    events: tuple[ContextEvent, ...] = ()
    error: ContextParseError | None = None

    def __post_init__(self) -> None:
        if self.status is ContextNormalizationStatus.EVENTS:
            if self.error is not None:
                raise ValueError("EVENTS result cannot contain an error")
        elif self.status is ContextNormalizationStatus.ERROR:
            if self.error is None or self.events:
                raise ValueError("ERROR result requires exactly one error and no events")
        elif self.events or self.error is not None:
            raise ValueError("NOT_APPLICABLE result cannot contain events or error")


def normalize_context_frame(
    frame: RawFrame,
    registry: InstrumentRegistry,
) -> ContextNormalizationResult:
    provenance_error = _validate_raw_provenance(frame)
    if provenance_error is not None:
        return _error_result(
            frame,
            None,
            ContextParseErrorCode.INVALID_PROVENANCE,
            provenance_error,
        )

    try:
        decoded = json.loads(frame.payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error_result(
            frame,
            None,
            ContextParseErrorCode.INVALID_JSON,
            "payload is not valid UTF-8 JSON",
        )

    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        return _error_result(
            frame,
            None,
            ContextParseErrorCode.INVALID_ENVELOPE,
            "top-level message must be a string-keyed object",
        )
    message = cast(dict[str, object], decoded)

    channel = message.get("channel")
    if not isinstance(channel, str):
        return _error_result(
            frame,
            None,
            ContextParseErrorCode.INVALID_ENVELOPE,
            "top-level channel must be a string",
        )
    if channel != _TARGET_CHANNEL:
        return ContextNormalizationResult(
            status=ContextNormalizationStatus.NOT_APPLICABLE,
            channel=channel,
        )

    data = message.get("data")
    if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
        return _error_result(
            frame,
            channel,
            ContextParseErrorCode.INVALID_CONTEXT_OBJECT,
            "activeAssetCtx data must be a string-keyed object",
        )
    payload = cast(dict[str, object], data)

    coin = payload.get("coin")
    if not isinstance(coin, str) or not coin:
        return _error_result(
            frame,
            channel,
            ContextParseErrorCode.UNSUPPORTED_COIN,
            "data.coin must be a non-empty string",
        )
    instrument = _instrument_for_coin(registry, coin)
    if instrument is None:
        return _error_result(
            frame,
            channel,
            ContextParseErrorCode.UNSUPPORTED_COIN,
            f"coin is not a configured Hyperliquid mainnet perpetual: {coin}",
        )

    raw_ctx = payload.get("ctx")
    if not isinstance(raw_ctx, dict) or not all(
        isinstance(key, str) for key in raw_ctx
    ):
        return _error_result(
            frame,
            channel,
            ContextParseErrorCode.INVALID_CONTEXT_OBJECT,
            "data.ctx must be a string-keyed object",
        )
    ctx = cast(dict[str, object], raw_ctx)

    funding = _required_exact_decimal(
        frame=frame,
        channel=channel,
        ctx=ctx,
        field="funding",
        code=ContextParseErrorCode.INVALID_FUNDING,
        strictly_positive=False,
    )
    if isinstance(funding, ContextNormalizationResult):
        return funding

    mark = _required_exact_decimal(
        frame=frame,
        channel=channel,
        ctx=ctx,
        field="markPx",
        code=ContextParseErrorCode.INVALID_MARK_PRICE,
        strictly_positive=True,
    )
    if isinstance(mark, ContextNormalizationResult):
        return mark

    oracle = _required_exact_decimal(
        frame=frame,
        channel=channel,
        ctx=ctx,
        field="oraclePx",
        code=ContextParseErrorCode.INVALID_ORACLE_PRICE,
        strictly_positive=True,
    )
    if isinstance(oracle, ContextNormalizationResult):
        return oracle

    availability = _availability_kind(frame)
    if availability is None:
        return _error_result(
            frame,
            channel,
            ContextParseErrorCode.INVALID_PROVENANCE,
            "capture_flags do not identify a supported availability kind",
        )

    common = {
        "frame": frame,
        "instrument": instrument,
        "availability": availability,
    }
    funding_event = FundingRateObservation(
        envelope=_envelope(
            event_type=EventType.FUNDING_RATE_OBSERVATION,
            **common,
        ),
        rate=funding,
        rate_period_seconds=_FUNDING_PERIOD_SECONDS,
        kind=FundingObservationKind.CURRENT,
        effective_boundary_ns=None,
    )
    mark_event = MarkPrice(
        envelope=_envelope(
            event_type=EventType.MARK_PRICE,
            **common,
        ),
        price=mark,
        method=None,
    )
    oracle_event = OraclePrice(
        envelope=_envelope(
            event_type=EventType.ORACLE_PRICE,
            **common,
        ),
        price=oracle,
        oracle_id=None,
    )

    return ContextNormalizationResult(
        status=ContextNormalizationStatus.EVENTS,
        channel=channel,
        events=(funding_event, mark_event, oracle_event),
    )


def serialize_normalized_context(events: tuple[ContextEvent, ...]) -> bytes:
    payload: list[dict[str, object]] = []
    for event in events:
        item: dict[str, object] = {"envelope": event.envelope.as_dict()}
        if isinstance(event, FundingRateObservation):
            item.update(
                {
                    "rate": serialize_exact_decimal(event.rate),
                    "rate_period_seconds": event.rate_period_seconds,
                    "kind": event.kind.value,
                    "effective_boundary_ns": event.effective_boundary_ns,
                }
            )
        elif isinstance(event, MarkPrice):
            item.update(
                {
                    "price": serialize_exact_decimal(event.price),
                    "method": event.method,
                }
            )
        else:
            item.update(
                {
                    "price": serialize_exact_decimal(event.price),
                    "oracle_id": event.oracle_id,
                }
            )
        payload.append(item)

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def _required_exact_decimal(
    *,
    frame: RawFrame,
    channel: str,
    ctx: dict[str, object],
    field: str,
    code: ContextParseErrorCode,
    strictly_positive: bool,
):
    raw = ctx.get(field)
    if not isinstance(raw, str):
        return _error_result(
            frame,
            channel,
            code,
            f"ctx.{field} must be a string",
        )
    try:
        value = parse_exact_decimal(raw)
    except NumericValidationError as exc:
        return _error_result(
            frame,
            channel,
            code,
            str(exc),
        )
    if strictly_positive and value <= 0:
        return _error_result(
            frame,
            channel,
            code,
            f"ctx.{field} must be positive",
        )
    return value


def _envelope(
    *,
    frame: RawFrame,
    instrument: Instrument,
    availability: AvailabilityKind,
    event_type: EventType,
) -> EventEnvelope:
    return EventEnvelope(
        schema_version=1,
        event_id=_event_id(frame, event_type),
        event_type=event_type,
        source=frame.metadata.source_id,
        instrument_id=instrument.instrument_id,
        native_symbol=instrument.native_symbol,
        exchange_ts_ns=None,
        exchange_ts_resolution_ns=None,
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
        quality_flags=QualityFlag.MISSING_EXCHANGE_TIME,
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
    code: ContextParseErrorCode,
    detail: str,
) -> ContextNormalizationResult:
    return ContextNormalizationResult(
        status=ContextNormalizationStatus.ERROR,
        channel=channel,
        error=ContextParseError(
            code=code,
            channel=channel,
            raw_segment_id=frame.ref.segment_id,
            raw_offset=frame.ref.offset,
            raw_sha256=frame.ref.payload_sha256,
            detail=detail,
        ),
    )
