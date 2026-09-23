from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from cryptobot.data.events import (
    BBO,
    AvailabilityKind,
    BookLevel,
    ClockHealth,
    EventEnvelope,
    EventType,
    EventValidationError,
    ExchangeTimestampSemantics,
    FeedState,
    FeedStatus,
    FundingObservationKind,
    FundingRateObservation,
    Gap,
    GapDetectability,
    L2Snapshot,
    MarkPrice,
    OraclePrice,
    QualityFlag,
    ReferenceBBO,
    ReferenceTrade,
    Trade,
    TradeSide,
)


def _envelope(
    event_type: EventType,
    *,
    exchange_ts_ns: int | None = 1_000_000_000,
    exchange_ts_resolution_ns: int | None = 1_000_000,
    exchange_ts_semantics: ExchangeTimestampSemantics = (
        ExchangeTimestampSemantics.EVENT_TIME
    ),
    quality_flags: QualityFlag = QualityFlag.NONE,
) -> EventEnvelope:
    if exchange_ts_ns is None:
        exchange_ts_resolution_ns = None
        exchange_ts_semantics = ExchangeTimestampSemantics.UNKNOWN
    return EventEnvelope(
        schema_version=1,
        event_id=f"event-{event_type.value.lower()}",
        event_type=event_type,
        source="hyperliquid-mainnet-public",
        instrument_id="hyperliquid.mainnet.perpetual.btc",
        native_symbol="BTC",
        exchange_ts_ns=exchange_ts_ns,
        exchange_ts_resolution_ns=exchange_ts_resolution_ns,
        exchange_ts_semantics=exchange_ts_semantics,
        recv_wall_ns=1_000_100_000,
        recv_mono_ns=500_000,
        host_id="recorder-a",
        boot_id="boot-a",
        connection_id="conn-a",
        ingest_seq=7,
        native_sequence=None,
        native_update_id=None,
        raw_segment_id="segment-a",
        raw_offset=42,
        raw_sha256="a" * 64,
        parse_version="1",
        quality_flags=quality_flags,
        availability_kind=AvailabilityKind.LIVE_CAPTURE,
    )


def test_event_envelope_is_immutable() -> None:
    envelope = _envelope(EventType.TRADE)

    with pytest.raises(FrozenInstanceError):
        envelope.ingest_seq = 8  # type: ignore[misc]


def test_missing_exchange_timestamp_remains_explicitly_nullable() -> None:
    envelope = _envelope(
        EventType.CLOCK_HEALTH,
        exchange_ts_ns=None,
        quality_flags=QualityFlag.MISSING_EXCHANGE_TIME,
    )

    assert envelope.exchange_ts_ns is None
    assert envelope.exchange_ts_resolution_ns is None
    assert envelope.exchange_ts_semantics is ExchangeTimestampSemantics.UNKNOWN


def test_exchange_timestamp_requires_resolution() -> None:
    with pytest.raises(EventValidationError, match="requires exchange_ts_resolution_ns"):
        _envelope(
            EventType.TRADE,
            exchange_ts_ns=1_000,
            exchange_ts_resolution_ns=None,
        )


def test_absent_exchange_timestamp_cannot_claim_known_semantics() -> None:
    with pytest.raises(EventValidationError, match="semantics must be UNKNOWN"):
        EventEnvelope(
            schema_version=1,
            event_id="event",
            event_type=EventType.TRADE,
            source="source",
            instrument_id="hyperliquid.mainnet.perpetual.btc",
            native_symbol="BTC",
            exchange_ts_ns=None,
            exchange_ts_resolution_ns=None,
            exchange_ts_semantics=ExchangeTimestampSemantics.TRADE_TIME,
            recv_wall_ns=10,
            recv_mono_ns=20,
            host_id="host",
            boot_id="boot",
            connection_id="conn",
            ingest_seq=0,
            native_sequence=None,
            native_update_id=None,
            raw_segment_id="segment",
            raw_offset=0,
            raw_sha256="b" * 64,
            parse_version="1",
            quality_flags=QualityFlag.MISSING_EXCHANGE_TIME,
            availability_kind=AvailabilityKind.LIVE_CAPTURE,
        )


def test_envelope_serialization_is_deterministic() -> None:
    envelope = _envelope(
        EventType.BBO,
        quality_flags=QualityFlag.GAP | QualityFlag.STALE,
    )

    first = envelope.as_dict()
    second = envelope.as_dict()

    assert first == second
    assert first["quality_flags"] == int(QualityFlag.GAP | QualityFlag.STALE)


def test_raw_sha256_is_strict() -> None:
    data = _envelope(EventType.TRADE).as_dict()
    data["raw_sha256"] = "not-a-hash"

    with pytest.raises(EventValidationError, match="raw_sha256"):
        EventEnvelope(
            schema_version=1,
            event_id="event",
            event_type=EventType.TRADE,
            source="source",
            instrument_id="hyperliquid.mainnet.perpetual.btc",
            native_symbol="BTC",
            exchange_ts_ns=1,
            exchange_ts_resolution_ns=1,
            exchange_ts_semantics=ExchangeTimestampSemantics.TRADE_TIME,
            recv_wall_ns=1,
            recv_mono_ns=1,
            host_id="host",
            boot_id="boot",
            connection_id="conn",
            ingest_seq=0,
            native_sequence=None,
            native_update_id=None,
            raw_segment_id="segment",
            raw_offset=0,
            raw_sha256=str(data["raw_sha256"]),
            parse_version="1",
            quality_flags=QualityFlag.NONE,
            availability_kind=AvailabilityKind.LIVE_CAPTURE,
        )


def test_payload_type_must_match_envelope_event_type() -> None:
    with pytest.raises(EventValidationError, match="payload requires event_type BBO"):
        BBO(
            envelope=_envelope(EventType.TRADE),
            bid_price=Decimal("100"),
            bid_size=Decimal("1"),
            ask_price=Decimal("101"),
            ask_size=Decimal("1"),
        )


def test_bbo_side_fields_are_nullable_only_as_a_pair() -> None:
    with pytest.raises(EventValidationError, match="bid price and size must be null together"):
        BBO(
            envelope=_envelope(EventType.BBO),
            bid_price=Decimal("100"),
            bid_size=None,
            ask_price=Decimal("101"),
            ask_size=Decimal("1"),
        )


def test_book_level_rejects_binary_float() -> None:
    with pytest.raises(EventValidationError, match="price must be Decimal"):
        BookLevel(price=100.0, size=Decimal("1"))  # type: ignore[arg-type]


def test_l2_snapshot_accepts_empty_side_without_inventing_liquidity() -> None:
    event = L2Snapshot(
        envelope=_envelope(EventType.L2_SNAPSHOT),
        bids=(BookLevel(Decimal("100"), Decimal("1")),),
        asks=(),
        depth_limit=20,
        aggregation=None,
        full_snapshot=True,
    )

    assert event.asks == ()


def test_trade_and_reference_trade_preserve_side_semantics() -> None:
    trade = Trade(
        envelope=_envelope(EventType.TRADE),
        price=Decimal("100"),
        size=Decimal("0.5"),
        native_side="A",
        aggressor_side=TradeSide.UNKNOWN,
        trade_id="tid-1",
        transaction_hash=None,
    )
    reference = ReferenceTrade(
        envelope=_envelope(EventType.REFERENCE_TRADE),
        price=Decimal("100.1"),
        size=Decimal("0.4"),
        native_side="sell",
        aggressor_side=TradeSide.SELL,
        trade_id="ref-1",
    )

    assert trade.native_side == "A"
    assert trade.aggressor_side is TradeSide.UNKNOWN
    assert reference.aggressor_side is TradeSide.SELL


def test_funding_rate_observation_keeps_predicted_vs_realized_kind() -> None:
    observation = FundingRateObservation(
        envelope=_envelope(EventType.FUNDING_RATE_OBSERVATION),
        rate=Decimal("-0.0001"),
        rate_period_seconds=3600,
        kind=FundingObservationKind.PREDICTED,
        effective_boundary_ns=None,
    )

    assert observation.kind is FundingObservationKind.PREDICTED


def test_price_event_types_smoke() -> None:
    mark = MarkPrice(
        envelope=_envelope(EventType.MARK_PRICE),
        price=Decimal("100"),
        method=None,
    )
    oracle = OraclePrice(
        envelope=_envelope(EventType.ORACLE_PRICE),
        price=Decimal("99.9"),
        oracle_id=None,
    )
    reference = ReferenceBBO(
        envelope=_envelope(EventType.REFERENCE_BBO),
        bid_price=Decimal("99"),
        bid_size=Decimal("2"),
        ask_price=Decimal("100"),
        ask_size=Decimal("2"),
        sampling_mode="MATCH_SAMPLED",
    )

    assert mark.price == Decimal("100")
    assert oracle.price == Decimal("99.9")
    assert reference.sampling_mode == "MATCH_SAMPLED"


def test_control_event_types_smoke() -> None:
    status = FeedStatus(
        envelope=_envelope(EventType.FEED_STATUS, exchange_ts_ns=None),
        state=FeedState.STALE,
        detail="no recent book",
    )
    gap = Gap(
        envelope=_envelope(
            EventType.GAP,
            exchange_ts_ns=None,
            quality_flags=QualityFlag.GAP,
        ),
        start_recv_wall_ns=100,
        end_recv_wall_ns=200,
        reason="reconnect",
        detectability=GapDetectability.INTERVAL_ONLY,
        backfill_status=None,
    )
    health = ClockHealth(
        envelope=_envelope(EventType.CLOCK_HEALTH, exchange_ts_ns=None),
        offset_ns=-100,
        uncertainty_ns=50,
        synchronized=True,
        clock_step_detected=False,
    )

    assert status.state is FeedState.STALE
    assert gap.end_recv_wall_ns == 200
    assert health.offset_ns == -100
