from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

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
    QuoteObservation,
    SimulationValidationError,
    build_fixed_horizon_opportunities,
    quote_from_bbo,
)


def _quote(event_id: str, mono: int) -> QuoteObservation:
    return QuoteObservation(
        event_id=event_id,
        source_id="hyperliquid-mainnet-public",
        instrument_id="hyperliquid.mainnet.perpetual.btc",
        role=InstrumentRole.PRIMARY,
        host_id="host-a",
        boot_id="boot-a",
        recv_mono_ns=mono,
        recv_wall_ns=10_000 + mono,
        bid_price=Decimal("100"),
        ask_price=Decimal("101"),
    )


def _envelope(event_id: str, mono: int) -> EventEnvelope:
    return EventEnvelope(
        schema_version=1,
        event_id=event_id,
        event_type=EventType.BBO,
        source="hyperliquid-mainnet-public",
        instrument_id="hyperliquid.mainnet.perpetual.btc",
        native_symbol="BTC",
        exchange_ts_ns=None,
        exchange_ts_resolution_ns=None,
        exchange_ts_semantics=ExchangeTimestampSemantics.UNKNOWN,
        recv_wall_ns=20_000 + mono,
        recv_mono_ns=mono,
        host_id="host-a",
        boot_id="boot-a",
        connection_id="connection-a",
        ingest_seq=mono,
        native_sequence=None,
        native_update_id=None,
        raw_segment_id="segment-a",
        raw_offset=mono,
        raw_sha256="a" * 64,
        parse_version="test",
        quality_flags=QualityFlag.NONE,
        availability_kind=AvailabilityKind.LIVE_CAPTURE,
    )


def test_quote_from_bbo_preserves_causal_and_executable_fields() -> None:
    event = BBO(
        envelope=_envelope("bbo-1", 123),
        bid_price=Decimal("100"),
        bid_size=Decimal("2"),
        ask_price=Decimal("101"),
        ask_size=Decimal("3"),
    )
    quote = quote_from_bbo(event, role=InstrumentRole.PRIMARY)

    assert quote.event_id == "bbo-1"
    assert quote.recv_mono_ns == 123
    assert quote.causal_domain == ("host-a", "boot-a")
    assert quote.bid_price == Decimal("100")
    assert quote.ask_price == Decimal("101")
    assert quote.role is InstrumentRole.PRIMARY


def test_fixed_horizon_builder_is_non_overlapping_and_deterministic() -> None:
    quotes = tuple(_quote(f"q-{value}", value) for value in (0, 10, 50, 60, 100, 110))
    first = build_fixed_horizon_opportunities(quotes, horizon_ns=50)
    second = build_fixed_horizon_opportunities(tuple(reversed(quotes)), horizon_ns=50)

    assert first == second
    assert len(first) == 2
    assert first[0].entry_quote.event_id == "q-0"
    assert first[0].exit_quote is not None
    assert first[0].exit_quote.event_id == "q-50"
    assert first[1].entry_quote.event_id == "q-60"
    assert first[1].exit_quote is not None
    assert first[1].exit_quote.event_id == "q-110"


def test_fixed_horizon_builder_preserves_missing_exit_as_invalid_opportunity() -> None:
    result = build_fixed_horizon_opportunities(
        (_quote("q-0", 0), _quote("q-10", 10)),
        horizon_ns=50,
    )
    assert len(result) == 1
    assert result[0].exit_quote is None
    assert "HORIZON_EXIT_UNAVAILABLE" in result[0].invalid_reasons()


def test_fixed_horizon_builder_marks_large_gap_explicitly() -> None:
    result = build_fixed_horizon_opportunities(
        (_quote("q-0", 0), _quote("q-5", 5), _quote("q-50", 50)),
        horizon_ns=50,
        max_step_ns=20,
    )
    assert len(result) == 1
    assert result[0].interval_invalid_reasons == ("GAP_EXCEEDS_MAX_STEP_NS",)


def test_fixed_horizon_builder_rejects_cross_boot_stream() -> None:
    other = replace(_quote("q-50", 50), boot_id="boot-b")
    with pytest.raises(SimulationValidationError, match="one source/instrument/role"):
        build_fixed_horizon_opportunities(
            (_quote("q-0", 0), other),
            horizon_ns=50,
        )
