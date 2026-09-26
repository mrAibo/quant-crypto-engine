from __future__ import annotations

import ast
import inspect
from dataclasses import replace
from decimal import Decimal

import pytest

import cryptobot.sim.policies as policies_module
from cryptobot.data.events import QualityFlag
from cryptobot.data.instruments import InstrumentRole
from cryptobot.sim import (
    CostEvidenceClass,
    CostInput,
    CostModel,
    DecisionContext,
    NoTradePolicy,
    PolicyAction,
    PolicyDecision,
    QuoteObservation,
    RandomizedDirectionPolicy,
    SimulationOpportunity,
    SimulationValidationError,
    TrialStatus,
    run_simulation,
)


class _FixedPolicy:
    def __init__(self, action: PolicyAction) -> None:
        self._action = action

    @property
    def policy_id(self) -> str:
        return f"test.fixed.{self._action.value.lower()}"

    @property
    def provenance(self) -> tuple[tuple[str, str], ...]:
        return (("test_policy", self._action.value),)

    def decide(self, context: DecisionContext) -> PolicyDecision:
        del context
        return PolicyDecision(action=self._action, reason="TEST_FIXED_ACTION")


def _quote(
    event_id: str,
    mono: int,
    *,
    bid: str | None = "100",
    ask: str | None = "101",
    role: InstrumentRole = InstrumentRole.PRIMARY,
    instrument_id: str = "hyperliquid.mainnet.perpetual.btc",
    source_id: str = "hyperliquid-mainnet-public",
    host_id: str = "host-a",
    boot_id: str = "boot-a",
    flags: QualityFlag = QualityFlag.NONE,
) -> QuoteObservation:
    return QuoteObservation(
        event_id=event_id,
        source_id=source_id,
        instrument_id=instrument_id,
        role=role,
        host_id=host_id,
        boot_id=boot_id,
        recv_mono_ns=mono,
        recv_wall_ns=1_000_000 + mono,
        bid_price=None if bid is None else Decimal(bid),
        ask_price=None if ask is None else Decimal(ask),
        quality_flags=flags,
    )


def _opportunity(
    name: str,
    start: int,
    *,
    entry_bid: str = "100",
    entry_ask: str = "101",
    exit_bid: str = "103",
    exit_ask: str = "104",
    role: InstrumentRole = InstrumentRole.PRIMARY,
    instrument_id: str = "hyperliquid.mainnet.perpetual.btc",
) -> SimulationOpportunity:
    return SimulationOpportunity(
        opportunity_id=name,
        entry_quote=_quote(
            f"{name}-entry",
            start,
            bid=entry_bid,
            ask=entry_ask,
            role=role,
            instrument_id=instrument_id,
        ),
        exit_quote=_quote(
            f"{name}-exit",
            start + 50,
            bid=exit_bid,
            ask=exit_ask,
            role=role,
            instrument_id=instrument_id,
        ),
    )


def _costs(
    *,
    fee: CostInput | None = None,
    latency: CostInput | None = None,
    impact: CostInput | None = None,
    funding: CostInput | None = None,
) -> CostModel:
    zero = CostInput(CostEvidenceClass.SCENARIO, Decimal("0"))
    return CostModel(
        fee_per_side=fee or zero,
        latency_per_side=latency or zero,
        impact_per_side=impact or zero,
        funding_round_trip=funding or zero,
    )


def test_unknown_cost_cannot_fabricate_zero_and_known_cost_requires_value() -> None:
    with pytest.raises(SimulationValidationError, match="must not fabricate"):
        CostInput(CostEvidenceClass.UNKNOWN, Decimal("0"))
    with pytest.raises(SimulationValidationError, match="requires a bps"):
        CostInput(CostEvidenceClass.SCENARIO, None)


def test_decision_context_rejects_future_and_cross_domain_history() -> None:
    current = _quote("current", 100)
    with pytest.raises(SimulationValidationError, match="future monotonic"):
        DecisionContext(
            opportunity_id="future",
            current_quote=current,
            history=(_quote("future", 101),),
        )
    with pytest.raises(SimulationValidationError, match="crosses host/boot"):
        DecisionContext(
            opportunity_id="domain",
            current_quote=current,
            history=(_quote("other", 99, boot_id="boot-b"),),
        )


def test_opportunity_rejects_cross_boot_exit_before_monotonic_comparison() -> None:
    with pytest.raises(SimulationValidationError, match="host/boot"):
        SimulationOpportunity(
            opportunity_id="cross-boot",
            entry_quote=_quote("entry", 10, boot_id="boot-a"),
            exit_quote=_quote("exit", 20, boot_id="boot-b"),
        )


def test_no_trade_control_counts_every_opportunity_and_has_zero_economics() -> None:
    unknown = CostInput(CostEvidenceClass.UNKNOWN, None)
    report = run_simulation(
        (_opportunity("a", 0), _opportunity("b", 100)),
        policy=NoTradePolicy(),
        cost_model=_costs(latency=unknown, impact=unknown, funding=unknown),
        quantity=Decimal("0.01"),
    )

    assert report.opportunity_count == 2
    assert report.traded_count == 0
    assert report.no_trade_count == 2
    assert report.invalid_count == 0
    assert report.gross_pnl == 0
    assert report.known_cost_total == 0
    assert report.business_net_pnl == 0
    assert report.unknown_cost_components == ()


def test_long_uses_ask_to_enter_bid_to_exit_and_does_not_add_spread_again() -> None:
    fee = CostInput(CostEvidenceClass.SCENARIO, Decimal("10"))
    report = run_simulation(
        (_opportunity("long", 0),),
        policy=_FixedPolicy(PolicyAction.LONG),
        cost_model=_costs(fee=fee),
        quantity=Decimal("2"),
    )

    entry = report.entries[0]
    assert entry.status is TrialStatus.TRADED
    assert entry.entry_price == Decimal("101")
    assert entry.exit_price == Decimal("103")
    assert entry.gross_pnl == Decimal("4")
    assert entry.fee_cost == Decimal("0.408")
    assert entry.known_cost_total == Decimal("0.408")
    assert entry.known_net_pnl == Decimal("3.592")
    assert entry.business_net_pnl == Decimal("3.592")
    assert "spread_cost" not in report.cost_model.as_dict()
    assert report.cost_model.as_dict()["spread_semantics"] == (
        "EMBEDDED_IN_EXECUTABLE_BID_ASK_NOT_ADDED_AS_COST"
    )


def test_short_uses_bid_to_enter_ask_to_exit() -> None:
    report = run_simulation(
        (_opportunity("short", 0),),
        policy=_FixedPolicy(PolicyAction.SHORT),
        cost_model=_costs(),
        quantity=Decimal("2"),
    )
    entry = report.entries[0]
    assert entry.entry_price == Decimal("100")
    assert entry.exit_price == Decimal("104")
    assert entry.gross_pnl == Decimal("-8")
    assert entry.business_net_pnl == Decimal("-8")


def test_unknown_latency_impact_and_funding_are_not_silently_zero() -> None:
    unknown = CostInput(CostEvidenceClass.UNKNOWN, None)
    fee = CostInput(CostEvidenceClass.SCENARIO, Decimal("4.5"))
    report = run_simulation(
        (_opportunity("unknown", 0),),
        policy=_FixedPolicy(PolicyAction.LONG),
        cost_model=_costs(
            fee=fee,
            latency=unknown,
            impact=unknown,
            funding=unknown,
        ),
        quantity=Decimal("1"),
    )

    entry = report.entries[0]
    assert entry.fee_cost is not None
    assert entry.latency_cost is None
    assert entry.impact_cost is None
    assert entry.funding_cost is None
    assert entry.known_net_pnl is not None
    assert entry.business_net_pnl is None
    assert entry.unknown_cost_components == ("funding", "impact", "latency")
    assert report.business_net_pnl is None


def test_stale_or_missing_interval_is_counted_as_invalid_without_trade() -> None:
    opportunity = SimulationOpportunity(
        opportunity_id="stale",
        entry_quote=_quote("entry", 0, flags=QualityFlag.STALE),
        exit_quote=_quote("exit", 50),
    )
    report = run_simulation(
        (opportunity,),
        policy=_FixedPolicy(PolicyAction.LONG),
        cost_model=_costs(),
        quantity=Decimal("1"),
    )

    entry = report.entries[0]
    assert entry.status is TrialStatus.INVALID
    assert entry.action is None
    assert "ENTRY_QUALITY_FLAGS" in entry.reason
    assert report.invalid_count == 1
    assert report.traded_count == 0


def test_randomized_direction_control_is_seed_deterministic() -> None:
    opportunities = tuple(_opportunity(f"opp-{index}", index * 100) for index in range(12))
    first = run_simulation(
        opportunities,
        policy=RandomizedDirectionPolicy(seed=42),
        cost_model=_costs(),
        quantity=Decimal("1"),
    )
    second = run_simulation(
        opportunities,
        policy=RandomizedDirectionPolicy(seed=42),
        cost_model=_costs(),
        quantity=Decimal("1"),
    )
    third = run_simulation(
        opportunities,
        policy=RandomizedDirectionPolicy(seed=43),
        cost_model=_costs(),
        quantity=Decimal("1"),
    )

    assert first.to_json_bytes() == second.to_json_bytes()
    assert first.sha256 == second.sha256
    assert [item.action for item in first.entries] != [item.action for item in third.entries]
    assert dict(first.policy_provenance)["seed"] == "42"


def test_policy_module_has_no_network_filesystem_or_wall_clock_imports() -> None:
    tree = ast.parse(inspect.getsource(policies_module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported <= {"__future__", "hashlib", "dataclasses", "cryptobot"}


def test_primary_and_replication_trials_remain_separable() -> None:
    btc = _opportunity("btc", 0)
    eth = _opportunity(
        "eth",
        100,
        role=InstrumentRole.REPLICATION,
        instrument_id="hyperliquid.mainnet.perpetual.eth",
    )
    report = run_simulation(
        (btc, eth),
        policy=_FixedPolicy(PolicyAction.LONG),
        cost_model=_costs(),
        quantity=Decimal("1"),
    )

    assert [item.role for item in report.entries] == [
        InstrumentRole.PRIMARY,
        InstrumentRole.REPLICATION,
    ]
    assert [item.instrument_id for item in report.entries] == [
        "hyperliquid.mainnet.perpetual.btc",
        "hyperliquid.mainnet.perpetual.eth",
    ]


def test_duplicate_opportunity_id_is_rejected() -> None:
    one = _opportunity("same", 0)
    two = replace(_opportunity("other", 100), opportunity_id="same")
    with pytest.raises(SimulationValidationError, match="duplicate opportunity_id"):
        run_simulation(
            (one, two),
            policy=NoTradePolicy(),
            cost_model=_costs(),
            quantity=Decimal("1"),
        )
