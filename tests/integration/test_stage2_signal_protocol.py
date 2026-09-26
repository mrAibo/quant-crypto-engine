from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from cryptobot.data.events import QualityFlag
from cryptobot.data.instruments import InstrumentRole
from cryptobot.research.signal_protocol import (
    DatasetPartition,
    FeatureValue,
    OutcomeLabel,
    SignalFeatureRow,
    derive_partition_plan,
    partition_rows,
)
from cryptobot.sim import (
    CostEvidenceClass,
    CostInput,
    CostModel,
    NoTradePolicy,
    QuoteObservation,
    RandomizedDirectionPolicy,
    SimulationOpportunity,
    run_simulation,
)


def _row(index: int) -> SignalFeatureRow:
    entry = QuoteObservation(
        event_id=f"entry-{index}",
        source_id="hyperliquid-mainnet-public",
        instrument_id="hyperliquid.mainnet.perpetual.btc",
        role=InstrumentRole.PRIMARY,
        host_id="host-a",
        boot_id="boot-a",
        recv_mono_ns=index * 100,
        recv_wall_ns=1_000_000 + index,
        bid_price=Decimal("100"),
        ask_price=Decimal("101"),
        quality_flags=QualityFlag.NONE,
    )
    exit_quote = replace(
        entry,
        event_id=f"exit-{index}",
        recv_mono_ns=entry.recv_mono_ns + 50,
        recv_wall_ns=entry.recv_wall_ns + 50,
        bid_price=Decimal("101"),
        ask_price=Decimal("102"),
    )
    opportunity = SimulationOpportunity(
        opportunity_id=f"opp-{index}",
        entry_quote=entry,
        exit_quote=exit_quote,
    )
    feature = FeatureValue(
        Decimal("1"),
        (entry.event_id,),
        entry.recv_mono_ns,
        entry.recv_wall_ns,
    )
    return SignalFeatureRow(
        row_id=f"row-{index}",
        source_segment_id=f"segment-{index // 17}",
        opportunity=opportunity,
        decision_invalid_reasons=(),
        hl_spread_bps=feature,
        hl_bbo_imbalance=feature,
        binance_mid_return_5s_bps=feature,
        outcome=OutcomeLabel(
            Decimal("1"),
            1,
            exit_quote.event_id,
            exit_quote.recv_mono_ns,
            exit_quote.recv_wall_ns,
            (),
        ),
    )


def _cost_model() -> CostModel:
    unknown = CostInput(CostEvidenceClass.UNKNOWN, None)
    return CostModel(
        fee_per_side=CostInput(CostEvidenceClass.SCENARIO, Decimal("4.5")),
        latency_per_side=unknown,
        impact_per_side=unknown,
        funding_round_trip=unknown,
    )


def test_selection_controls_use_identical_frozen_opportunity_rows() -> None:
    rows = tuple(_row(index) for index in range(2500))
    plan = derive_partition_plan(rows)
    selection = partition_rows(
        rows,
        plan=plan,
        partition=DatasetPartition.SELECTION,
        role=InstrumentRole.PRIMARY,
    )
    opportunities = tuple(row.opportunity for row in selection)

    no_trade = run_simulation(
        opportunities,
        policy=NoTradePolicy(),
        cost_model=_cost_model(),
        quantity=Decimal("0.001"),
    )
    randomized = run_simulation(
        opportunities,
        policy=RandomizedDirectionPolicy(seed=2026092601),
        cost_model=_cost_model(),
        quantity=Decimal("0.001"),
    )

    assert no_trade.opportunity_count == randomized.opportunity_count == len(selection)
    assert [item.opportunity_id for item in no_trade.entries] == [
        item.opportunity_id for item in randomized.entries
    ]
    assert [item.opportunity_id for item in no_trade.entries] == [
        row.opportunity.opportunity_id for row in selection
    ]
