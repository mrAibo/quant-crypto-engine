"""Deterministic Stage-1 simulation contracts and controls."""

from cryptobot.sim.contracts import (
    SIMULATOR_VERSION,
    CostEvidenceClass,
    CostInput,
    CostModel,
    DecisionContext,
    Policy,
    PolicyAction,
    PolicyDecision,
    QuoteObservation,
    SimulationOpportunity,
    SimulationReport,
    SimulationValidationError,
    TrialLedgerEntry,
    TrialStatus,
)
from cryptobot.sim.engine import run_simulation
from cryptobot.sim.evidence import build_fixed_horizon_opportunities, quote_from_bbo
from cryptobot.sim.policies import NoTradePolicy, RandomizedDirectionPolicy

__all__ = [
    "SIMULATOR_VERSION",
    "CostEvidenceClass",
    "CostInput",
    "CostModel",
    "DecisionContext",
    "NoTradePolicy",
    "Policy",
    "PolicyAction",
    "PolicyDecision",
    "QuoteObservation",
    "RandomizedDirectionPolicy",
    "SimulationOpportunity",
    "SimulationReport",
    "SimulationValidationError",
    "TrialLedgerEntry",
    "TrialStatus",
    "build_fixed_horizon_opportunities",
    "quote_from_bbo",
    "run_simulation",
]
