from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from cryptobot.data.events import QualityFlag
from cryptobot.data.instruments import InstrumentRole
from cryptobot.research.signal_protocol import (
    H1_ID,
    H2_ID,
    DatasetPartition,
    FeatureValue,
    OutcomeLabel,
    PowerPlan,
    RegistrationStatus,
    SignalFeatureRow,
    SignalProtocolValidationError,
    Stage2FeatureDataset,
    TrialRegistration,
    TrialRegistry,
    derive_partition_plan,
    directional_accuracy_planning_count,
    hypothesis_action,
    partition_rows,
)
from cryptobot.sim import PolicyAction, QuoteObservation, SimulationOpportunity


def _quote(
    event_id: str,
    mono: int,
    wall: int,
    *,
    role: InstrumentRole = InstrumentRole.PRIMARY,
    instrument_id: str = "hyperliquid.mainnet.perpetual.btc",
) -> QuoteObservation:
    return QuoteObservation(
        event_id=event_id,
        source_id="hyperliquid-mainnet-public",
        instrument_id=instrument_id,
        role=role,
        host_id="host-a",
        boot_id="boot-a",
        recv_mono_ns=mono,
        recv_wall_ns=wall,
        bid_price=Decimal("100"),
        ask_price=Decimal("101"),
        quality_flags=QualityFlag.NONE,
    )


def _feature(value: str, event_id: str, mono: int, wall: int) -> FeatureValue:
    return FeatureValue(
        value=Decimal(value),
        source_event_ids=(event_id,),
        asof_recv_mono_ns=mono,
        asof_recv_wall_ns=wall,
    )


def _row(
    index: int,
    *,
    wall: int | None = None,
    role: InstrumentRole = InstrumentRole.PRIMARY,
    outcome_sign: int = 1,
    h1_ready: bool = True,
    h2_ready: bool = True,
) -> SignalFeatureRow:
    decision_wall = 1_000_000 + index if wall is None else wall
    entry = _quote(
        f"entry-{index}",
        index * 100,
        decision_wall,
        role=role,
        instrument_id=(
            "hyperliquid.mainnet.perpetual.btc"
            if role is InstrumentRole.PRIMARY
            else "hyperliquid.mainnet.perpetual.eth"
        ),
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
    h1 = (
        _feature("1", f"ref-{index}", entry.recv_mono_ns, entry.recv_wall_ns)
        if h1_ready
        else FeatureValue(None, (), None, None, "H1_MISSING")
    )
    h2 = (
        _feature("0.2", entry.event_id, entry.recv_mono_ns, entry.recv_wall_ns)
        if h2_ready
        else FeatureValue(None, (), None, None, "H2_MISSING")
    )
    return SignalFeatureRow(
        row_id=f"row-{index}",
        source_segment_id=f"seg-{index // 17}",
        opportunity=opportunity,
        decision_invalid_reasons=(),
        hl_spread_bps=_feature(
            "10",
            entry.event_id,
            entry.recv_mono_ns,
            entry.recv_wall_ns,
        ),
        hl_bbo_imbalance=h2,
        binance_mid_return_5s_bps=h1,
        outcome=OutcomeLabel(
            signed_mid_return_bps=Decimal(outcome_sign),
            direction=outcome_sign,
            exit_event_id=exit_quote.event_id,
            exit_recv_mono_ns=exit_quote.recv_mono_ns,
            exit_recv_wall_ns=exit_quote.recv_wall_ns,
            invalid_reasons=(),
        ),
    )


def test_directional_planning_counts_are_frozen_and_derived() -> None:
    assert directional_accuracy_planning_count(Decimal("0.55")) == 783
    assert directional_accuracy_planning_count(Decimal("0.54")) == 1225

    plan = PowerPlan()
    assert plan.selection_min_evaluable == 783
    assert plan.confirmation_min_evaluable == 1225
    assert plan.per_hypothesis_alpha == Decimal("0.025")


def test_feature_value_requires_explicit_missingness_or_provenance() -> None:
    with pytest.raises(SignalProtocolValidationError, match="missing_reason"):
        FeatureValue(None, (), None, None, None)

    with pytest.raises(SignalProtocolValidationError, match="source_event_ids"):
        FeatureValue(Decimal("1"), (), 1, 1)


def test_feature_row_rejects_future_availability() -> None:
    row = _row(1)
    with pytest.raises(SignalProtocolValidationError, match="future monotonic"):
        replace(
            row,
            binance_mid_return_5s_bps=FeatureValue(
                Decimal("1"),
                ("future",),
                row.decision_recv_mono_ns + 1,
                row.decision_recv_wall_ns,
            ),
        )


def test_hypothesis_action_does_not_depend_on_future_outcome() -> None:
    positive = _row(1, outcome_sign=1)
    negative_outcome = replace(
        positive,
        outcome=OutcomeLabel(
            signed_mid_return_bps=Decimal("-1"),
            direction=-1,
            exit_event_id=positive.outcome.exit_event_id,
            exit_recv_mono_ns=positive.outcome.exit_recv_mono_ns,
            exit_recv_wall_ns=positive.outcome.exit_recv_wall_ns,
            invalid_reasons=(),
        ),
    )

    assert hypothesis_action(positive.decision_view(), hypothesis_id=H1_ID) is PolicyAction.LONG
    assert (
        hypothesis_action(negative_outcome.decision_view(), hypothesis_id=H1_ID)
        is PolicyAction.LONG
    )
    assert hypothesis_action(positive.decision_view(), hypothesis_id=H2_ID) is PolicyAction.LONG


def test_partition_plan_uses_feature_availability_not_outcomes() -> None:
    rows = tuple(_row(index, outcome_sign=1) for index in range(2500))
    inverted = tuple(
        replace(
            row,
            outcome=replace(
                row.outcome,
                signed_mid_return_bps=Decimal("-1"),
                direction=-1,
            ),
        )
        for row in rows
    )

    first = derive_partition_plan(rows)
    second = derive_partition_plan(inverted)

    assert first == second
    assert first.development_row_count == 492
    assert first.selection_row_count == 783
    assert first.confirmation_row_count == 1225
    assert first.selection_h1_ready == 783
    assert first.confirmation_h2_ready == 1225


def test_equal_wall_timestamps_stay_in_later_partition() -> None:
    rows = list(_row(index) for index in range(2500))
    base = derive_partition_plan(tuple(rows))
    boundary_wall = rows[base.confirmation_start_wall_ns - 1_000_000].decision_recv_wall_ns
    # Make the immediately preceding row share the confirmation boundary wall.
    index = base.confirmation_start_wall_ns - 1_000_000
    rows[index - 1] = _row(index - 1, wall=boundary_wall)

    shifted = derive_partition_plan(tuple(rows))

    assert shifted.confirmation_start_wall_ns == boundary_wall
    assert shifted.confirmation_row_count == 1226


def test_partition_rows_preserves_identical_row_objects_for_controls() -> None:
    rows = tuple(_row(index) for index in range(2500))
    plan = derive_partition_plan(rows)

    selection = partition_rows(
        rows,
        plan=plan,
        partition=DatasetPartition.SELECTION,
        role=InstrumentRole.PRIMARY,
    )

    assert tuple(row.row_id for row in selection) == tuple(
        row.row_id
        for row in rows
        if plan.partition_for(row.decision_recv_wall_ns) is DatasetPartition.SELECTION
    )
    assert all(row.role is InstrumentRole.PRIMARY for row in selection)


def test_trial_registry_rejects_duplicate_trials_and_has_stable_digest() -> None:
    registry = TrialRegistry(
        (
            TrialRegistration("trial-1", H1_ID, "SELECTION"),
            TrialRegistration("trial-2", H2_ID, "SELECTION"),
        )
    )
    assert registry.sha256 == registry.sha256
    assert all(item.status is RegistrationStatus.REGISTERED for item in registry.registrations)

    with pytest.raises(SignalProtocolValidationError, match="trial_id"):
        TrialRegistry(
            (
                TrialRegistration("same", H1_ID, "SELECTION"),
                TrialRegistration("same", H2_ID, "SELECTION"),
            )
        )


def test_feature_dataset_digest_binds_executable_quote_prices() -> None:
    row = _row(1)
    dataset = Stage2FeatureDataset(
        source_gate_report_sha256="a" * 64,
        source_campaign_manifest_sha256="b" * 64,
        source_segment_digests=(("seg-0", "c" * 64),),
        rows=(row,),
    )
    changed_entry = replace(
        row.opportunity.entry_quote,
        bid_price=Decimal("99"),
    )
    changed = replace(
        row,
        opportunity=replace(row.opportunity, entry_quote=changed_entry),
    )
    changed_dataset = replace(dataset, rows=(changed,))

    assert dataset.sha256 != changed_dataset.sha256


def test_replication_rows_use_primary_partition_wall_boundaries() -> None:
    primary = tuple(_row(index) for index in range(2500))
    plan = derive_partition_plan(primary)
    eth = _row(
        9999,
        wall=plan.confirmation_start_wall_ns,
        role=InstrumentRole.REPLICATION,
    )

    assert plan.partition_for(eth.decision_recv_wall_ns) is DatasetPartition.CONFIRMATION
