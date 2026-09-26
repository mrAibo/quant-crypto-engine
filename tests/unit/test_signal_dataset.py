from __future__ import annotations

from decimal import Decimal

from cryptobot.data.events import QualityFlag
from cryptobot.data.instruments import InstrumentRole
from cryptobot.research.signal_dataset import (
    TopOfBookFeatureObservation,
    build_signal_feature_rows,
)
from cryptobot.research.signal_protocol import H1_ID, H2_ID, hypothesis_action
from cryptobot.sim import PolicyAction, QuoteObservation, SimulationOpportunity

_NS = 1_000_000_000
_BTC = "hyperliquid.mainnet.perpetual.btc"
_REF = "binance_usdm.reference.perpetual.btcusdt"


def _quote(
    event_id: str,
    mono: int,
    wall: int,
    bid: str,
    ask: str,
) -> QuoteObservation:
    return QuoteObservation(
        event_id=event_id,
        source_id="hyperliquid-mainnet-public",
        instrument_id=_BTC,
        role=InstrumentRole.PRIMARY,
        host_id="host-a",
        boot_id="boot-a",
        recv_mono_ns=mono,
        recv_wall_ns=wall,
        bid_price=Decimal(bid),
        ask_price=Decimal(ask),
        quality_flags=QualityFlag.NONE,
    )


def _book(
    event_id: str,
    mono: int,
    wall: int,
    *,
    source: str,
    instrument: str,
    bid: str,
    ask: str,
    bid_size: str = "1",
    ask_size: str = "1",
    boot: str = "boot-a",
    flags: QualityFlag = QualityFlag.NONE,
) -> TopOfBookFeatureObservation:
    return TopOfBookFeatureObservation(
        event_id=event_id,
        source_id=source,
        instrument_id=instrument,
        host_id="host-a",
        boot_id=boot,
        recv_mono_ns=mono,
        recv_wall_ns=wall,
        bid_price=Decimal(bid),
        bid_size=Decimal(bid_size),
        ask_price=Decimal(ask),
        ask_size=Decimal(ask_size),
        quality_flags=flags,
    )


def _opportunity() -> SimulationOpportunity:
    return SimulationOpportunity(
        opportunity_id="opp-1",
        entry_quote=_quote(
            "hl-entry",
            10 * _NS,
            100 * _NS,
            "100",
            "101",
        ),
        exit_quote=_quote(
            "hl-exit",
            60 * _NS,
            150 * _NS,
            "103",
            "104",
        ),
    )


def test_h1_h2_features_are_causal_exact_and_future_reference_is_ignored() -> None:
    opp = _opportunity()
    primary = (
        _book(
            "hl-entry",
            10 * _NS,
            100 * _NS,
            source="hyperliquid-mainnet-public",
            instrument=_BTC,
            bid="100",
            ask="101",
            bid_size="2",
            ask_size="1",
        ),
    )
    reference = (
        _book(
            "ref-anchor",
            5 * _NS,
            95 * _NS,
            source="binance-usdm-reference-public",
            instrument=_REF,
            bid="99",
            ask="101",
        ),
        _book(
            "ref-current",
            10 * _NS,
            99 * _NS,
            source="binance-usdm-reference-public",
            instrument=_REF,
            bid="100",
            ask="102",
        ),
        _book(
            "ref-same-mono-future-wall",
            10 * _NS,
            101 * _NS,
            source="binance-usdm-reference-public",
            instrument=_REF,
            bid="150",
            ask="152",
        ),
        _book(
            "ref-future",
            11 * _NS,
            102 * _NS,
            source="binance-usdm-reference-public",
            instrument=_REF,
            bid="200",
            ask="202",
        ),
    )

    row = build_signal_feature_rows(
        segment_id="segment-a",
        opportunities=(opp,),
        primary_books=primary,
        reference_books=reference,
        reference_instrument_id=_REF,
    )[0]

    assert row.hl_bbo_imbalance.value == Decimal("1") / Decimal("3")
    assert row.binance_mid_return_5s_bps.source_event_ids == (
        "ref-anchor",
        "ref-current",
    )
    assert row.binance_mid_return_5s_bps.asof_recv_wall_ns == 99 * _NS
    assert row.binance_mid_return_5s_bps.value == Decimal("100")
    assert row.outcome.available
    assert row.outcome.exit_event_id == "hl-exit"
    assert hypothesis_action(row.decision_view(), hypothesis_id=H1_ID) is PolicyAction.LONG
    assert hypothesis_action(row.decision_view(), hypothesis_id=H2_ID) is PolicyAction.LONG


def test_reference_other_boot_is_explicitly_missing() -> None:
    opp = _opportunity()
    primary = (
        _book(
            "hl-entry",
            10 * _NS,
            100 * _NS,
            source="hyperliquid-mainnet-public",
            instrument=_BTC,
            bid="100",
            ask="101",
        ),
    )
    reference = (
        _book(
            "other-boot",
            10 * _NS,
            99 * _NS,
            source="binance-usdm-reference-public",
            instrument=_REF,
            bid="100",
            ask="101",
            boot="boot-b",
        ),
    )

    row = build_signal_feature_rows(
        segment_id="segment-a",
        opportunities=(opp,),
        primary_books=primary,
        reference_books=reference,
        reference_instrument_id=_REF,
    )[0]

    assert row.binance_mid_return_5s_bps.value is None
    assert row.binance_mid_return_5s_bps.missing_reason == "REFERENCE_BBO_UNAVAILABLE"
    assert hypothesis_action(row.decision_view(), hypothesis_id=H1_ID) is PolicyAction.ABSTAIN


def test_reference_staleness_is_explicit_not_backfilled_from_future() -> None:
    opp = _opportunity()
    primary = (
        _book(
            "hl-entry",
            10 * _NS,
            100 * _NS,
            source="hyperliquid-mainnet-public",
            instrument=_BTC,
            bid="100",
            ask="101",
        ),
    )
    reference = (
        _book(
            "anchor",
            5 * _NS,
            95 * _NS,
            source="binance-usdm-reference-public",
            instrument=_REF,
            bid="99",
            ask="100",
        ),
        _book(
            "old-current",
            7 * _NS,
            97 * _NS,
            source="binance-usdm-reference-public",
            instrument=_REF,
            bid="100",
            ask="101",
        ),
        _book(
            "future",
            10 * _NS + 1,
            99 * _NS,
            source="binance-usdm-reference-public",
            instrument=_REF,
            bid="101",
            ask="102",
        ),
    )

    row = build_signal_feature_rows(
        segment_id="segment-a",
        opportunities=(opp,),
        primary_books=primary,
        reference_books=reference,
        reference_instrument_id=_REF,
    )[0]

    assert row.binance_mid_return_5s_bps.value is None
    assert row.binance_mid_return_5s_bps.missing_reason == "REFERENCE_CURRENT_STALE"


def test_invalid_future_interval_is_outcome_only_not_decision_feature() -> None:
    opp = SimulationOpportunity(
        opportunity_id="gap",
        entry_quote=_opportunity().entry_quote,
        exit_quote=_opportunity().exit_quote,
        interval_invalid_reasons=("GAP_EXCEEDS_MAX_STEP_NS",),
    )
    primary = (
        _book(
            "hl-entry",
            10 * _NS,
            100 * _NS,
            source="hyperliquid-mainnet-public",
            instrument=_BTC,
            bid="100",
            ask="101",
            bid_size="2",
            ask_size="1",
        ),
    )
    reference = (
        _book(
            "ref-anchor",
            5 * _NS,
            95 * _NS,
            source="binance-usdm-reference-public",
            instrument=_REF,
            bid="99",
            ask="101",
        ),
        _book(
            "ref-current",
            10 * _NS,
            99 * _NS,
            source="binance-usdm-reference-public",
            instrument=_REF,
            bid="100",
            ask="102",
        ),
    )

    row = build_signal_feature_rows(
        segment_id="segment-a",
        opportunities=(opp,),
        primary_books=primary,
        reference_books=reference,
        reference_instrument_id=_REF,
    )[0]

    assert row.decision_invalid_reasons == ()
    assert row.decision_view().feature_ready(H1_ID)
    assert row.outcome.signed_mid_return_bps is None
    assert row.outcome.invalid_reasons == ("GAP_EXCEEDS_MAX_STEP_NS",)


def test_feature_row_build_is_deterministic_under_input_order() -> None:
    opp = _opportunity()
    primary = (
        _book(
            "hl-entry",
            10 * _NS,
            100 * _NS,
            source="hyperliquid-mainnet-public",
            instrument=_BTC,
            bid="100",
            ask="101",
            bid_size="2",
            ask_size="1",
        ),
    )
    reference = (
        _book(
            "ref-anchor",
            5 * _NS,
            95 * _NS,
            source="binance-usdm-reference-public",
            instrument=_REF,
            bid="99",
            ask="101",
        ),
        _book(
            "ref-current",
            10 * _NS,
            99 * _NS,
            source="binance-usdm-reference-public",
            instrument=_REF,
            bid="100",
            ask="102",
        ),
    )

    first = build_signal_feature_rows(
        segment_id="segment-a",
        opportunities=(opp,),
        primary_books=primary,
        reference_books=reference,
        reference_instrument_id=_REF,
    )
    second = build_signal_feature_rows(
        segment_id="segment-a",
        opportunities=(opp,),
        primary_books=tuple(reversed(primary)),
        reference_books=tuple(reversed(reference)),
        reference_instrument_id=_REF,
    )

    assert first == second
