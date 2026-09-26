from __future__ import annotations

from decimal import Decimal

from cryptobot.data.numeric import parse_exact_decimal
from cryptobot.sim.contracts import (
    SIMULATOR_VERSION,
    CostEvidenceClass,
    CostInput,
    CostModel,
    DecisionContext,
    Policy,
    PolicyAction,
    QuoteObservation,
    SimulationOpportunity,
    SimulationReport,
    SimulationValidationError,
    TrialLedgerEntry,
    TrialStatus,
    bps_cost,
)


def run_simulation(
    opportunities: tuple[SimulationOpportunity, ...],
    *,
    policy: Policy,
    cost_model: CostModel,
    quantity: Decimal,
) -> SimulationReport:
    size = parse_exact_decimal(quantity)
    if size <= 0:
        raise SimulationValidationError("simulation quantity must be positive")
    _validate_opportunity_ids(opportunities)

    entries: list[TrialLedgerEntry] = []
    for opportunity in opportunities:
        invalid_reasons = opportunity.invalid_reasons()
        if invalid_reasons:
            entries.append(_invalid_entry(opportunity, policy.policy_id, invalid_reasons))
            continue

        context = DecisionContext(
            opportunity_id=opportunity.opportunity_id,
            current_quote=opportunity.entry_quote,
            history=opportunity.context_quotes,
        )
        decision = policy.decide(context)
        if decision.action is PolicyAction.ABSTAIN:
            entries.append(
                _no_trade_entry(
                    opportunity,
                    policy.policy_id,
                    decision.reason,
                )
            )
            continue

        entries.append(
            _trade_entry(
                opportunity,
                policy_id=policy.policy_id,
                action=decision.action,
                reason=decision.reason,
                quantity=size,
                cost_model=cost_model,
            )
        )

    return SimulationReport(
        simulator_version=SIMULATOR_VERSION,
        policy_id=policy.policy_id,
        policy_provenance=policy.provenance,
        quantity=size,
        cost_model=cost_model,
        entries=tuple(entries),
    )


def _trade_entry(
    opportunity: SimulationOpportunity,
    *,
    policy_id: str,
    action: PolicyAction,
    reason: str,
    quantity: Decimal,
    cost_model: CostModel,
) -> TrialLedgerEntry:
    exit_quote = opportunity.exit_quote
    if exit_quote is None:
        raise SimulationValidationError("trade path requires exit quote")
    entry_price, exit_price = _execution_prices(
        opportunity.entry_quote,
        exit_quote,
        action,
    )
    gross = _gross_pnl(
        action=action,
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
    )
    entry_notional = entry_price * quantity
    exit_notional = exit_price * quantity
    fee = _per_side_cost(cost_model.fee_per_side, entry_notional, exit_notional)
    latency = _per_side_cost(
        cost_model.latency_per_side,
        entry_notional,
        exit_notional,
    )
    impact = _per_side_cost(
        cost_model.impact_per_side,
        entry_notional,
        exit_notional,
    )
    funding = _round_trip_cost(cost_model.funding_round_trip, entry_notional)

    known_costs = tuple(item for item in (fee, latency, impact, funding) if item is not None)
    known_total = sum(known_costs, Decimal("0"))
    unknown = _unknown_components(cost_model)
    known_net = gross - known_total
    business_net = None if unknown else known_net

    return TrialLedgerEntry(
        opportunity_id=opportunity.opportunity_id,
        policy_id=policy_id,
        instrument_id=opportunity.entry_quote.instrument_id,
        role=opportunity.entry_quote.role,
        decision_event_id=opportunity.entry_quote.event_id,
        exit_event_id=exit_quote.event_id,
        action=action,
        status=TrialStatus.TRADED,
        reason=reason,
        decision_recv_mono_ns=opportunity.entry_quote.recv_mono_ns,
        exit_recv_mono_ns=exit_quote.recv_mono_ns,
        quantity=quantity,
        entry_price=entry_price,
        exit_price=exit_price,
        gross_pnl=gross,
        fee_cost=fee,
        latency_cost=latency,
        impact_cost=impact,
        funding_cost=funding,
        known_cost_total=known_total,
        known_net_pnl=known_net,
        business_net_pnl=business_net,
        unknown_cost_components=unknown,
    )


def _execution_prices(
    entry: QuoteObservation,
    exit_quote: QuoteObservation,
    action: PolicyAction,
) -> tuple[Decimal, Decimal]:
    if entry.bid_price is None or entry.ask_price is None:
        raise SimulationValidationError("entry quote is not executable")
    if exit_quote.bid_price is None or exit_quote.ask_price is None:
        raise SimulationValidationError("exit quote is not executable")
    if action is PolicyAction.LONG:
        return entry.ask_price, exit_quote.bid_price
    if action is PolicyAction.SHORT:
        return entry.bid_price, exit_quote.ask_price
    raise SimulationValidationError("trade execution requires LONG or SHORT action")


def _gross_pnl(
    *,
    action: PolicyAction,
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: Decimal,
) -> Decimal:
    if action is PolicyAction.LONG:
        return (exit_price - entry_price) * quantity
    if action is PolicyAction.SHORT:
        return (entry_price - exit_price) * quantity
    raise SimulationValidationError("gross PnL requires LONG or SHORT action")


def _per_side_cost(
    component: CostInput,
    entry_notional: Decimal,
    exit_notional: Decimal,
) -> Decimal | None:
    if component.evidence_class is CostEvidenceClass.UNKNOWN:
        return None
    if component.bps is None:
        raise SimulationValidationError("known/scenario cost is missing bps")
    return bps_cost(entry_notional + exit_notional, component.bps)


def _round_trip_cost(component: CostInput, entry_notional: Decimal) -> Decimal | None:
    if component.evidence_class is CostEvidenceClass.UNKNOWN:
        return None
    if component.bps is None:
        raise SimulationValidationError("known/scenario cost is missing bps")
    return bps_cost(entry_notional, component.bps)


def _unknown_components(cost_model: CostModel) -> tuple[str, ...]:
    fields = (
        ("fee", cost_model.fee_per_side),
        ("latency", cost_model.latency_per_side),
        ("impact", cost_model.impact_per_side),
        ("funding", cost_model.funding_round_trip),
    )
    return tuple(
        sorted(
            name
            for name, component in fields
            if component.evidence_class is CostEvidenceClass.UNKNOWN
        )
    )


def _invalid_entry(
    opportunity: SimulationOpportunity,
    policy_id: str,
    reasons: tuple[str, ...],
) -> TrialLedgerEntry:
    return TrialLedgerEntry(
        opportunity_id=opportunity.opportunity_id,
        policy_id=policy_id,
        instrument_id=opportunity.entry_quote.instrument_id,
        role=opportunity.entry_quote.role,
        decision_event_id=opportunity.entry_quote.event_id,
        exit_event_id=(None if opportunity.exit_quote is None else opportunity.exit_quote.event_id),
        action=None,
        status=TrialStatus.INVALID,
        reason="|".join(reasons),
        decision_recv_mono_ns=opportunity.entry_quote.recv_mono_ns,
        exit_recv_mono_ns=(
            None if opportunity.exit_quote is None else opportunity.exit_quote.recv_mono_ns
        ),
        quantity=None,
        entry_price=None,
        exit_price=None,
        gross_pnl=None,
        fee_cost=None,
        latency_cost=None,
        impact_cost=None,
        funding_cost=None,
        known_cost_total=None,
        known_net_pnl=None,
        business_net_pnl=None,
        unknown_cost_components=(),
    )


def _no_trade_entry(
    opportunity: SimulationOpportunity,
    policy_id: str,
    reason: str,
) -> TrialLedgerEntry:
    zero = Decimal("0")
    exit_quote = opportunity.exit_quote
    return TrialLedgerEntry(
        opportunity_id=opportunity.opportunity_id,
        policy_id=policy_id,
        instrument_id=opportunity.entry_quote.instrument_id,
        role=opportunity.entry_quote.role,
        decision_event_id=opportunity.entry_quote.event_id,
        exit_event_id=None if exit_quote is None else exit_quote.event_id,
        action=PolicyAction.ABSTAIN,
        status=TrialStatus.NO_TRADE,
        reason=reason,
        decision_recv_mono_ns=opportunity.entry_quote.recv_mono_ns,
        exit_recv_mono_ns=None if exit_quote is None else exit_quote.recv_mono_ns,
        quantity=zero,
        entry_price=None,
        exit_price=None,
        gross_pnl=zero,
        fee_cost=zero,
        latency_cost=zero,
        impact_cost=zero,
        funding_cost=zero,
        known_cost_total=zero,
        known_net_pnl=zero,
        business_net_pnl=zero,
        unknown_cost_components=(),
    )


def _validate_opportunity_ids(
    opportunities: tuple[SimulationOpportunity, ...],
) -> None:
    seen: set[str] = set()
    for opportunity in opportunities:
        if opportunity.opportunity_id in seen:
            raise SimulationValidationError(
                f"duplicate opportunity_id: {opportunity.opportunity_id}"
            )
        seen.add(opportunity.opportunity_id)
