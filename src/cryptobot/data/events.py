from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import IntFlag, StrEnum

from cryptobot.data.numeric import NumericValidationError, parse_exact_decimal


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EventValidationError(ValueError):
    """Raised when a normalized event violates the v1 event contract."""


class EventType(StrEnum):
    L2_SNAPSHOT = "L2_SNAPSHOT"
    BBO = "BBO"
    TRADE = "TRADE"
    FUNDING_RATE_OBSERVATION = "FUNDING_RATE_OBSERVATION"
    FUNDING_PAYMENT = "FUNDING_PAYMENT"
    MARK_PRICE = "MARK_PRICE"
    ORACLE_PRICE = "ORACLE_PRICE"
    REFERENCE_BBO = "REFERENCE_BBO"
    REFERENCE_TRADE = "REFERENCE_TRADE"
    FEED_STATUS = "FEED_STATUS"
    GAP = "GAP"
    CLOCK_HEALTH = "CLOCK_HEALTH"


class ExchangeTimestampSemantics(StrEnum):
    UNKNOWN = "UNKNOWN"
    TRADE_TIME = "TRADE_TIME"
    BOOK_PUBLICATION_TIME = "BOOK_PUBLICATION_TIME"
    EVENT_TIME = "EVENT_TIME"
    FUNDING_BOUNDARY = "FUNDING_BOUNDARY"
    ACCOUNT_EVENT_TIME = "ACCOUNT_EVENT_TIME"


class AvailabilityKind(StrEnum):
    LIVE_CAPTURE = "LIVE_CAPTURE"
    LATE_BACKFILL = "LATE_BACKFILL"
    HISTORICAL_IMPORT = "HISTORICAL_IMPORT"


class QualityFlag(IntFlag):
    NONE = 0
    MISSING_EXCHANGE_TIME = 1 << 0
    GAP = 1 << 1
    STALE = 1 << 2
    DUPLICATE_CANDIDATE = 1 << 3
    BACKFILL = 1 << 4
    SUSPECT = 1 << 5


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


class FundingObservationKind(StrEnum):
    PREDICTED = "PREDICTED"
    REALIZED = "REALIZED"


class FeedState(StrEnum):
    CONNECTING = "CONNECTING"
    SUBSCRIBED = "SUBSCRIBED"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    RESYNCING = "RESYNCING"
    RECOVERED = "RECOVERED"


class GapDetectability(StrEnum):
    EXACT = "EXACT"
    INTERVAL_ONLY = "INTERVAL_ONLY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    schema_version: int
    event_id: str
    event_type: EventType
    source: str
    instrument_id: str
    native_symbol: str
    exchange_ts_ns: int | None
    exchange_ts_resolution_ns: int | None
    exchange_ts_semantics: ExchangeTimestampSemantics
    recv_wall_ns: int
    recv_mono_ns: int
    host_id: str
    boot_id: str
    connection_id: str
    ingest_seq: int
    native_sequence: int | None
    native_update_id: str | None
    raw_segment_id: str
    raw_offset: int
    raw_sha256: str
    parse_version: str
    quality_flags: QualityFlag
    availability_kind: AvailabilityKind

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != 1
        ):
            raise EventValidationError("schema_version must be integer 1")

        if not isinstance(self.event_type, EventType):
            raise EventValidationError("event_type must be EventType")
        if not isinstance(self.exchange_ts_semantics, ExchangeTimestampSemantics):
            raise EventValidationError(
                "exchange_ts_semantics must be ExchangeTimestampSemantics"
            )
        if not isinstance(self.availability_kind, AvailabilityKind):
            raise EventValidationError("availability_kind must be AvailabilityKind")

        for field_name, value in (
            ("event_id", self.event_id),
            ("source", self.source),
            ("instrument_id", self.instrument_id),
            ("native_symbol", self.native_symbol),
            ("host_id", self.host_id),
            ("boot_id", self.boot_id),
            ("connection_id", self.connection_id),
            ("raw_segment_id", self.raw_segment_id),
            ("parse_version", self.parse_version),
        ):
            if not value.strip():
                raise EventValidationError(f"{field_name} must be non-empty")

        _require_optional_nonnegative_int(self.exchange_ts_ns, "exchange_ts_ns")
        _require_optional_positive_int(
            self.exchange_ts_resolution_ns, "exchange_ts_resolution_ns"
        )
        _require_nonnegative_int(self.recv_wall_ns, "recv_wall_ns")
        _require_nonnegative_int(self.recv_mono_ns, "recv_mono_ns")
        _require_nonnegative_int(self.ingest_seq, "ingest_seq")
        _require_optional_nonnegative_int(self.native_sequence, "native_sequence")
        _require_nonnegative_int(self.raw_offset, "raw_offset")

        if self.exchange_ts_ns is None and self.exchange_ts_resolution_ns is not None:
            raise EventValidationError(
                "exchange_ts_resolution_ns requires exchange_ts_ns"
            )
        if self.exchange_ts_ns is not None and self.exchange_ts_resolution_ns is None:
            raise EventValidationError(
                "exchange_ts_ns requires exchange_ts_resolution_ns"
            )
        if (
            self.exchange_ts_ns is None
            and self.exchange_ts_semantics is not ExchangeTimestampSemantics.UNKNOWN
        ):
            raise EventValidationError(
                "exchange timestamp semantics must be UNKNOWN when exchange time is absent"
            )

        if self.native_update_id is not None and not self.native_update_id.strip():
            raise EventValidationError("native_update_id must be null or non-empty")
        if not _SHA256_RE.fullmatch(self.raw_sha256):
            raise EventValidationError("raw_sha256 must contain 64 lowercase hex characters")
        if not isinstance(self.quality_flags, QualityFlag):
            raise EventValidationError("quality_flags must be QualityFlag")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source": self.source,
            "instrument_id": self.instrument_id,
            "native_symbol": self.native_symbol,
            "exchange_ts_ns": self.exchange_ts_ns,
            "exchange_ts_resolution_ns": self.exchange_ts_resolution_ns,
            "exchange_ts_semantics": self.exchange_ts_semantics.value,
            "recv_wall_ns": self.recv_wall_ns,
            "recv_mono_ns": self.recv_mono_ns,
            "host_id": self.host_id,
            "boot_id": self.boot_id,
            "connection_id": self.connection_id,
            "ingest_seq": self.ingest_seq,
            "native_sequence": self.native_sequence,
            "native_update_id": self.native_update_id,
            "raw_segment_id": self.raw_segment_id,
            "raw_offset": self.raw_offset,
            "raw_sha256": self.raw_sha256,
            "parse_version": self.parse_version,
            "quality_flags": int(self.quality_flags),
            "availability_kind": self.availability_kind.value,
        }


@dataclass(frozen=True, slots=True)
class BookLevel:
    price: Decimal
    size: Decimal
    order_count: int | None = None

    def __post_init__(self) -> None:
        _require_decimal(self.price, "price", strictly_positive=True)
        _require_decimal(self.size, "size", strictly_positive=True)
        _require_optional_nonnegative_int(self.order_count, "order_count")


@dataclass(frozen=True, slots=True)
class L2Snapshot:
    envelope: EventEnvelope
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    depth_limit: int | None
    aggregation: str | None
    full_snapshot: bool

    def __post_init__(self) -> None:
        _require_event_type(self.envelope, EventType.L2_SNAPSHOT)
        _require_optional_positive_int(self.depth_limit, "depth_limit")
        if self.aggregation is not None and not self.aggregation.strip():
            raise EventValidationError("aggregation must be null or non-empty")


@dataclass(frozen=True, slots=True)
class BBO:
    envelope: EventEnvelope
    bid_price: Decimal | None
    bid_size: Decimal | None
    ask_price: Decimal | None
    ask_size: Decimal | None

    def __post_init__(self) -> None:
        _require_event_type(self.envelope, EventType.BBO)
        _validate_bbo_side(self.bid_price, self.bid_size, "bid")
        _validate_bbo_side(self.ask_price, self.ask_size, "ask")


@dataclass(frozen=True, slots=True)
class Trade:
    envelope: EventEnvelope
    price: Decimal
    size: Decimal
    native_side: str | None
    aggressor_side: TradeSide
    trade_id: str | None
    transaction_hash: str | None

    def __post_init__(self) -> None:
        _require_event_type(self.envelope, EventType.TRADE)
        _require_decimal(self.price, "price", strictly_positive=True)
        _require_decimal(self.size, "size", strictly_positive=True)
        _require_optional_nonempty(self.native_side, "native_side")
        _require_optional_nonempty(self.trade_id, "trade_id")
        _require_optional_nonempty(self.transaction_hash, "transaction_hash")


@dataclass(frozen=True, slots=True)
class FundingRateObservation:
    envelope: EventEnvelope
    rate: Decimal
    rate_period_seconds: int
    kind: FundingObservationKind
    effective_boundary_ns: int | None

    def __post_init__(self) -> None:
        _require_event_type(self.envelope, EventType.FUNDING_RATE_OBSERVATION)
        _require_decimal(self.rate, "rate")
        _require_positive_int(self.rate_period_seconds, "rate_period_seconds")
        _require_optional_nonnegative_int(
            self.effective_boundary_ns, "effective_boundary_ns"
        )


@dataclass(frozen=True, slots=True)
class FundingPayment:
    envelope: EventEnvelope
    account_id: str
    position_size: Decimal
    rate: Decimal
    oracle_price: Decimal
    cash_flow: Decimal
    payment_id: str | None

    def __post_init__(self) -> None:
        _require_event_type(self.envelope, EventType.FUNDING_PAYMENT)
        if not self.account_id.strip():
            raise EventValidationError("account_id must be non-empty")
        _require_decimal(self.position_size, "position_size")
        _require_decimal(self.rate, "rate")
        _require_decimal(self.oracle_price, "oracle_price", strictly_positive=True)
        _require_decimal(self.cash_flow, "cash_flow")
        _require_optional_nonempty(self.payment_id, "payment_id")


@dataclass(frozen=True, slots=True)
class MarkPrice:
    envelope: EventEnvelope
    price: Decimal
    method: str | None = None

    def __post_init__(self) -> None:
        _require_event_type(self.envelope, EventType.MARK_PRICE)
        _require_decimal(self.price, "price", strictly_positive=True)
        _require_optional_nonempty(self.method, "method")


@dataclass(frozen=True, slots=True)
class OraclePrice:
    envelope: EventEnvelope
    price: Decimal
    oracle_id: str | None = None

    def __post_init__(self) -> None:
        _require_event_type(self.envelope, EventType.ORACLE_PRICE)
        _require_decimal(self.price, "price", strictly_positive=True)
        _require_optional_nonempty(self.oracle_id, "oracle_id")


@dataclass(frozen=True, slots=True)
class ReferenceBBO:
    envelope: EventEnvelope
    bid_price: Decimal | None
    bid_size: Decimal | None
    ask_price: Decimal | None
    ask_size: Decimal | None
    sampling_mode: str

    def __post_init__(self) -> None:
        _require_event_type(self.envelope, EventType.REFERENCE_BBO)
        _validate_bbo_side(self.bid_price, self.bid_size, "bid")
        _validate_bbo_side(self.ask_price, self.ask_size, "ask")
        if not self.sampling_mode.strip():
            raise EventValidationError("sampling_mode must be non-empty")


@dataclass(frozen=True, slots=True)
class ReferenceTrade:
    envelope: EventEnvelope
    price: Decimal
    size: Decimal
    native_side: str | None
    aggressor_side: TradeSide
    trade_id: str | None

    def __post_init__(self) -> None:
        _require_event_type(self.envelope, EventType.REFERENCE_TRADE)
        _require_decimal(self.price, "price", strictly_positive=True)
        _require_decimal(self.size, "size", strictly_positive=True)
        _require_optional_nonempty(self.native_side, "native_side")
        _require_optional_nonempty(self.trade_id, "trade_id")


@dataclass(frozen=True, slots=True)
class FeedStatus:
    envelope: EventEnvelope
    state: FeedState
    detail: str | None = None

    def __post_init__(self) -> None:
        _require_event_type(self.envelope, EventType.FEED_STATUS)
        _require_optional_nonempty(self.detail, "detail")


@dataclass(frozen=True, slots=True)
class Gap:
    envelope: EventEnvelope
    start_recv_wall_ns: int
    end_recv_wall_ns: int
    reason: str
    detectability: GapDetectability
    backfill_status: str | None = None

    def __post_init__(self) -> None:
        _require_event_type(self.envelope, EventType.GAP)
        _require_nonnegative_int(self.start_recv_wall_ns, "start_recv_wall_ns")
        _require_nonnegative_int(self.end_recv_wall_ns, "end_recv_wall_ns")
        if self.end_recv_wall_ns < self.start_recv_wall_ns:
            raise EventValidationError("gap end must not precede gap start")
        if not self.reason.strip():
            raise EventValidationError("gap reason must be non-empty")
        _require_optional_nonempty(self.backfill_status, "backfill_status")


@dataclass(frozen=True, slots=True)
class ClockHealth:
    envelope: EventEnvelope
    offset_ns: int | None
    uncertainty_ns: int | None
    synchronized: bool
    clock_step_detected: bool

    def __post_init__(self) -> None:
        _require_event_type(self.envelope, EventType.CLOCK_HEALTH)
        _require_optional_int(self.offset_ns, "offset_ns")
        _require_optional_nonnegative_int(self.uncertainty_ns, "uncertainty_ns")


def _require_event_type(envelope: EventEnvelope, expected: EventType) -> None:
    if envelope.event_type is not expected:
        raise EventValidationError(
            f"payload requires event_type {expected.value}, got {envelope.event_type.value}"
        )


def _require_decimal(value: Decimal, field: str, *, strictly_positive: bool = False) -> None:
    if not isinstance(value, Decimal):
        raise EventValidationError(f"{field} must be Decimal")
    try:
        parsed = parse_exact_decimal(value)
    except NumericValidationError as exc:
        raise EventValidationError(str(exc)) from exc
    if strictly_positive and parsed <= 0:
        raise EventValidationError(f"{field} must be positive")


def _validate_bbo_side(
    price: Decimal | None,
    size: Decimal | None,
    side: str,
) -> None:
    if (price is None) != (size is None):
        raise EventValidationError(f"{side} price and size must be null together")
    if price is not None:
        _require_decimal(price, f"{side}_price", strictly_positive=True)
        if size is None:
            raise EventValidationError(f"{side} size must be present with price")
        _require_decimal(size, f"{side}_size", strictly_positive=True)


def _require_nonnegative_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EventValidationError(f"{field} must be a non-negative integer")


def _require_positive_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EventValidationError(f"{field} must be a positive integer")


def _require_optional_nonnegative_int(value: int | None, field: str) -> None:
    if value is not None:
        _require_nonnegative_int(value, field)


def _require_optional_positive_int(value: int | None, field: str) -> None:
    if value is not None:
        _require_positive_int(value, field)


def _require_optional_int(value: int | None, field: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise EventValidationError(f"{field} must be null or an integer")


def _require_optional_nonempty(value: str | None, field: str) -> None:
    if value is not None and not value.strip():
        raise EventValidationError(f"{field} must be null or non-empty")
