from __future__ import annotations

from decimal import Decimal

from cryptobot.data.events import (
    BBO,
    AvailabilityKind,
    EventEnvelope,
    EventType,
    ExchangeTimestampSemantics,
    QualityFlag,
)
from cryptobot.data.instruments import InstrumentRole
from cryptobot.sim import (
    CostEvidenceClass,
    CostInput,
    CostModel,
    NoTradePolicy,
    build_fixed_horizon_opportunities,
    quote_from_bbo,
    run_simulation,
)


def _bbo(event_id: str, mono: int, bid: str, ask: str) -> BBO:
    envelope = EventEnvelope(
        schema_version=1,
        event_id=event_id,
        event_type=EventType.BBO,
        source="hyperliquid-mainnet-public",
        instrument_id="hyperliquid.mainnet.perpetual.btc",
        native_symbol="BTC",
        exchange_ts_ns=None,
        exchange_ts_resolution_ns=None,
        exchange_ts_semantics=ExchangeTimestampSemantics.UNKNOWN,
        recv_wall_ns=1_000_000 + mono,
        recv_mono_ns=mono,
        host_id="host-sim",
        boot_id="boot-sim",
        connection_id="connection-sim",
        ingest_seq=mono,
        native_sequence=None,
        native_update_id=None,
        raw_segment_id="segment-sim",
        raw_offset=mono,
        raw_sha256="b" * 64,
        parse_version="integration",
        quality_flags=QualityFlag.NONE,
        availability_kind=AvailabilityKind.LIVE_CAPTURE,
    )
    return BBO(
        envelope=envelope,
        bid_price=Decimal(bid),
        bid_size=Decimal("1"),
        ask_price=Decimal(ask),
        ask_size=Decimal("1"),
    )


def test_normalized_bbo_replays_through_shared_simulator_deterministically() -> None:
    normalized = (
        _bbo("bbo-0", 0, "100", "101"),
        _bbo("bbo-20", 20, "100.5", "101.5"),
        _bbo("bbo-50", 50, "103", "104"),
        _bbo("bbo-100", 100, "104", "105"),
    )
    quotes = tuple(quote_from_bbo(item, role=InstrumentRole.PRIMARY) for item in normalized)
    opportunities = build_fixed_horizon_opportunities(quotes, horizon_ns=50)
    unknown = CostInput(CostEvidenceClass.UNKNOWN, None)
    costs = CostModel(
        fee_per_side=CostInput(CostEvidenceClass.SCENARIO, Decimal("4.5")),
        latency_per_side=unknown,
        impact_per_side=unknown,
        funding_round_trip=unknown,
    )

    first = run_simulation(
        opportunities,
        policy=NoTradePolicy(),
        cost_model=costs,
        quantity=Decimal("0.001"),
    )
    second = run_simulation(
        opportunities,
        policy=NoTradePolicy(),
        cost_model=costs,
        quantity=Decimal("0.001"),
    )

    assert first.to_json_bytes() == second.to_json_bytes()
    assert first.sha256 == second.sha256
    assert first.opportunity_count == 2
    assert first.no_trade_count == 1
    assert first.invalid_count == 1
    assert first.traded_count == 0
