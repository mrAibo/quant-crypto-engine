from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cryptobot.sim.contracts import (
    DecisionContext,
    PolicyAction,
    PolicyDecision,
    SimulationValidationError,
)


@dataclass(frozen=True, slots=True)
class NoTradePolicy:
    policy_id: str = "control.no_trade.v1"

    @property
    def provenance(self) -> tuple[tuple[str, str], ...]:
        return (("control", "NO_TRADE"), ("version", "1"))

    def decide(self, context: DecisionContext) -> PolicyDecision:
        del context
        return PolicyDecision(
            action=PolicyAction.ABSTAIN,
            reason="NO_TRADE_CONTROL",
        )


@dataclass(frozen=True, slots=True)
class RandomizedDirectionPolicy:
    seed: int
    policy_id: str = "control.randomized_direction.v1"

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise SimulationValidationError("randomized control seed must be an integer")

    @property
    def provenance(self) -> tuple[tuple[str, str], ...]:
        return (
            ("control", "RANDOMIZED_DIRECTION"),
            ("seed", str(self.seed)),
            ("version", "1"),
        )

    def decide(self, context: DecisionContext) -> PolicyDecision:
        payload = (
            f"{self.seed}|{context.opportunity_id}|"
            f"{context.current_quote.instrument_id}|{context.current_quote.event_id}"
        ).encode()
        digest = hashlib.sha256(payload).digest()
        action = PolicyAction.LONG if digest[0] & 1 == 0 else PolicyAction.SHORT
        return PolicyDecision(
            action=action,
            reason="DETERMINISTIC_SHA256_DIRECTION_CONTROL",
        )
