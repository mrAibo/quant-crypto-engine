from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from cryptobot.data.events import QualityFlag
from cryptobot.data.instruments import InstrumentRole
from cryptobot.data.numeric import parse_exact_decimal, serialize_exact_decimal

SIMULATOR_VERSION = "minimal-simulator-v1"
_BPS_DENOMINATOR = Decimal("10000")


class SimulationValidationError(ValueError):
    """Raised when a Stage-1 simulator contract is invalid."""


class PolicyAction(StrEnum):
    ABSTAIN = "ABSTAIN"
    LONG = "LONG"
    SHORT = "SHORT"


class TrialStatus(StrEnum):
    INVALID = "INVALID"
    NO_TRADE = "NO_TRADE"
    TRADED = "TRADED"


class CostEvidenceClass(StrEnum):
    OBSERVED = "OBSERVED"
    SCENARIO = "SCENARIO"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class CostInput:
    evidence_class: CostEvidenceClass
    bps: Decimal | None

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_class, CostEvidenceClass):
            raise SimulationValidationError("evidence_class must be CostEvidenceClass")
        if self.evidence_class is CostEvidenceClass.UNKNOWN:
            if self.bps is not None:
                raise SimulationValidationError("UNKNOWN cost must not fabricate a bps value")
            return
        if self.bps is None:
            raise SimulationValidationError("OBSERVED/SCENARIO cost requires a bps value")
        value = parse_exact_decimal(self.bps)
        if value < 0:
            raise SimulationValidationError("cost bps must be non-negative")

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence_class": self.evidence_class.value,
            "bps": None if self.bps is None else serialize_exact_decimal(self.bps),
        }


@dataclass(frozen=True, slots=True)
class CostModel:
    fee_per_side: CostInput
    latency_per_side: CostInput
    impact_per_side: CostInput
    funding_round_trip: CostInput

    def as_dict(self) -> dict[str, object]:
        return {
            "fee_per_side": self.fee_per_side.as_dict(),
            "latency_per_side": self.latency_per_side.as_dict(),
            "impact_per_side": self.impact_per_side.as_dict(),
            "funding_round_trip": self.funding_round_trip.as_dict(),
            "spread_semantics": "EMBEDDED_IN_EXECUTABLE_BID_ASK_NOT_ADDED_AS_COST",
        }


@dataclass(frozen=True, slots=True)
class QuoteObservation:
    event_id: str
    source_id: str
    instrument_id: str
    role: InstrumentRole
    host_id: str
    boot_id: str
    recv_mono_ns: int
    recv_wall_ns: int
    bid_price: Decimal | None
    ask_price: Decimal | None
    quality_flags: QualityFlag = QualityFlag.NONE

    def __post_init__(self) -> None:
        for field, value in (
            ("event_id", self.event_id),
            ("source_id", self.source_id),
            ("instrument_id", self.instrument_id),
            ("host_id", self.host_id),
            ("boot_id", self.boot_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise SimulationValidationError(f"{field} must be non-empty")
        if not isinstance(self.role, InstrumentRole):
            raise SimulationValidationError("role must be InstrumentRole")
        _require_nonnegative_int(self.recv_mono_ns, "recv_mono_ns")
        _require_nonnegative_int(self.recv_wall_ns, "recv_wall_ns")
        _require_optional_positive_decimal(self.bid_price, "bid_price")
        _require_optional_positive_decimal(self.ask_price, "ask_price")
        if not isinstance(self.quality_flags, QualityFlag):
            raise SimulationValidationError("quality_flags must be QualityFlag")

    @property
    def causal_domain(self) -> tuple[str, str]:
        return (self.host_id, self.boot_id)

    def invalid_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.bid_price is None or self.ask_price is None:
            reasons.append("MISSING_BBO_SIDE")
        elif self.ask_price <= self.bid_price:
            reasons.append("CROSSED_OR_LOCKED_BBO")
        forbidden = self.quality_flags & (QualityFlag.GAP | QualityFlag.STALE | QualityFlag.SUSPECT)
        if forbidden:
            reasons.append(f"QUALITY_FLAGS_{int(forbidden)}")
        return tuple(reasons)


@dataclass(frozen=True, slots=True)
class SimulationOpportunity:
    opportunity_id: str
    entry_quote: QuoteObservation
    exit_quote: QuoteObservation | None
    context_quotes: tuple[QuoteObservation, ...] = ()
    interval_invalid_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.opportunity_id.strip():
            raise SimulationValidationError("opportunity_id must be non-empty")
        if self.exit_quote is not None:
            _validate_exit_quote(self.entry_quote, self.exit_quote)
        previous_key: tuple[int, int, str] | None = None
        seen_ids: set[str] = set()
        for quote in self.context_quotes:
            if quote.causal_domain != self.entry_quote.causal_domain:
                raise SimulationValidationError(
                    "context quote must share the entry host/boot causal domain"
                )
            if quote.recv_mono_ns > self.entry_quote.recv_mono_ns:
                raise SimulationValidationError("context quote leaks future monotonic time")
            if quote.recv_wall_ns > self.entry_quote.recv_wall_ns:
                raise SimulationValidationError("context quote leaks future wall time")
            key = (quote.recv_mono_ns, quote.recv_wall_ns, quote.event_id)
            if previous_key is not None and key < previous_key:
                raise SimulationValidationError("context quotes must be causally ordered")
            previous_key = key
            if quote.event_id in seen_ids:
                raise SimulationValidationError("context quote event_id must be unique")
            seen_ids.add(quote.event_id)
        for reason in self.interval_invalid_reasons:
            if not reason.strip():
                raise SimulationValidationError(
                    "interval_invalid_reasons must contain non-empty strings"
                )

    def invalid_reasons(self) -> tuple[str, ...]:
        reasons = list(self.interval_invalid_reasons)
        reasons.extend(f"ENTRY_{item}" for item in self.entry_quote.invalid_reasons())
        if self.exit_quote is None:
            reasons.append("MISSING_EXIT_QUOTE")
        else:
            reasons.extend(f"EXIT_{item}" for item in self.exit_quote.invalid_reasons())
        return tuple(reasons)


@dataclass(frozen=True, slots=True)
class DecisionContext:
    opportunity_id: str
    current_quote: QuoteObservation
    history: tuple[QuoteObservation, ...]

    def __post_init__(self) -> None:
        for quote in self.history:
            if quote.causal_domain != self.current_quote.causal_domain:
                raise SimulationValidationError("history crosses host/boot causal domain")
            if quote.recv_mono_ns > self.current_quote.recv_mono_ns:
                raise SimulationValidationError("history contains future monotonic data")
            if quote.recv_wall_ns > self.current_quote.recv_wall_ns:
                raise SimulationValidationError("history contains future wall-time data")


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    action: PolicyAction
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.action, PolicyAction):
            raise SimulationValidationError("action must be PolicyAction")
        if not self.reason.strip():
            raise SimulationValidationError("decision reason must be non-empty")


class Policy(Protocol):
    @property
    def policy_id(self) -> str: ...

    @property
    def provenance(self) -> tuple[tuple[str, str], ...]: ...

    def decide(self, context: DecisionContext) -> PolicyDecision: ...


@dataclass(frozen=True, slots=True)
class TrialLedgerEntry:
    opportunity_id: str
    policy_id: str
    instrument_id: str
    role: InstrumentRole
    decision_event_id: str
    exit_event_id: str | None
    action: PolicyAction | None
    status: TrialStatus
    reason: str
    decision_recv_mono_ns: int
    exit_recv_mono_ns: int | None
    quantity: Decimal | None
    entry_price: Decimal | None
    exit_price: Decimal | None
    gross_pnl: Decimal | None
    fee_cost: Decimal | None
    latency_cost: Decimal | None
    impact_cost: Decimal | None
    funding_cost: Decimal | None
    known_cost_total: Decimal | None
    known_net_pnl: Decimal | None
    business_net_pnl: Decimal | None
    unknown_cost_components: tuple[str, ...]

    def __post_init__(self) -> None:
        for field, value in (
            ("opportunity_id", self.opportunity_id),
            ("policy_id", self.policy_id),
            ("instrument_id", self.instrument_id),
            ("decision_event_id", self.decision_event_id),
            ("reason", self.reason),
        ):
            if not value.strip():
                raise SimulationValidationError(f"{field} must be non-empty")
        if not isinstance(self.role, InstrumentRole):
            raise SimulationValidationError("ledger role must be InstrumentRole")
        _require_nonnegative_int(self.decision_recv_mono_ns, "decision_recv_mono_ns")
        if self.exit_recv_mono_ns is not None:
            _require_nonnegative_int(self.exit_recv_mono_ns, "exit_recv_mono_ns")
            if self.exit_recv_mono_ns <= self.decision_recv_mono_ns:
                raise SimulationValidationError("ledger exit time must follow decision time")
        if tuple(sorted(set(self.unknown_cost_components))) != self.unknown_cost_components:
            raise SimulationValidationError("unknown_cost_components must be unique and sorted")
        allowed_unknown = {"fee", "latency", "impact", "funding"}
        if not set(self.unknown_cost_components) <= allowed_unknown:
            raise SimulationValidationError("unknown_cost_components contains unknown label")

        if self.status is TrialStatus.INVALID:
            if self.action is not None:
                raise SimulationValidationError("INVALID ledger entry must not have an action")
            return
        if self.status is TrialStatus.NO_TRADE:
            if self.action is not PolicyAction.ABSTAIN:
                raise SimulationValidationError("NO_TRADE ledger entry requires ABSTAIN")
            _require_zero_trade_accounting(self)
            return
        if self.status is not TrialStatus.TRADED:
            raise SimulationValidationError("unsupported trial status")
        if self.action not in (PolicyAction.LONG, PolicyAction.SHORT):
            raise SimulationValidationError("TRADED ledger entry requires LONG or SHORT")
        if self.exit_event_id is None or self.exit_recv_mono_ns is None:
            raise SimulationValidationError("TRADED ledger entry requires exit evidence")
        for numeric_field, numeric_value in (
            ("quantity", self.quantity),
            ("entry_price", self.entry_price),
            ("exit_price", self.exit_price),
        ):
            if numeric_value is None or parse_exact_decimal(numeric_value) <= 0:
                raise SimulationValidationError(f"TRADED {numeric_field} must be positive")
        for cost_field, cost_value in (
            ("fee_cost", self.fee_cost),
            ("latency_cost", self.latency_cost),
            ("impact_cost", self.impact_cost),
            ("funding_cost", self.funding_cost),
        ):
            if cost_value is not None and parse_exact_decimal(cost_value) < 0:
                raise SimulationValidationError(f"{cost_field} must be non-negative")
        if self.gross_pnl is None or self.known_cost_total is None or self.known_net_pnl is None:
            raise SimulationValidationError("TRADED ledger entry requires known accounting")
        if self.unknown_cost_components:
            if self.business_net_pnl is not None:
                raise SimulationValidationError(
                    "business_net_pnl must remain null while costs are UNKNOWN"
                )
        elif self.business_net_pnl is None:
            raise SimulationValidationError(
                "business_net_pnl is required when all costs are known/scenario"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "opportunity_id": self.opportunity_id,
            "policy_id": self.policy_id,
            "instrument_id": self.instrument_id,
            "role": self.role.value,
            "decision_event_id": self.decision_event_id,
            "exit_event_id": self.exit_event_id,
            "action": None if self.action is None else self.action.value,
            "status": self.status.value,
            "reason": self.reason,
            "decision_recv_mono_ns": self.decision_recv_mono_ns,
            "exit_recv_mono_ns": self.exit_recv_mono_ns,
            "quantity": _decimal_or_none(self.quantity),
            "entry_price": _decimal_or_none(self.entry_price),
            "exit_price": _decimal_or_none(self.exit_price),
            "gross_pnl": _decimal_or_none(self.gross_pnl),
            "fee_cost": _decimal_or_none(self.fee_cost),
            "latency_cost": _decimal_or_none(self.latency_cost),
            "impact_cost": _decimal_or_none(self.impact_cost),
            "funding_cost": _decimal_or_none(self.funding_cost),
            "known_cost_total": _decimal_or_none(self.known_cost_total),
            "known_net_pnl": _decimal_or_none(self.known_net_pnl),
            "business_net_pnl": _decimal_or_none(self.business_net_pnl),
            "unknown_cost_components": list(self.unknown_cost_components),
        }


@dataclass(frozen=True, slots=True)
class SimulationReport:
    simulator_version: str
    policy_id: str
    policy_provenance: tuple[tuple[str, str], ...]
    quantity: Decimal
    cost_model: CostModel
    entries: tuple[TrialLedgerEntry, ...]

    @property
    def opportunity_count(self) -> int:
        return len(self.entries)

    @property
    def traded_count(self) -> int:
        return sum(item.status is TrialStatus.TRADED for item in self.entries)

    @property
    def no_trade_count(self) -> int:
        return sum(item.status is TrialStatus.NO_TRADE for item in self.entries)

    @property
    def invalid_count(self) -> int:
        return sum(item.status is TrialStatus.INVALID for item in self.entries)

    @property
    def gross_pnl(self) -> Decimal:
        return sum(
            (item.gross_pnl for item in self.entries if item.gross_pnl is not None),
            Decimal("0"),
        )

    @property
    def known_cost_total(self) -> Decimal:
        return sum(
            (item.known_cost_total for item in self.entries if item.known_cost_total is not None),
            Decimal("0"),
        )

    @property
    def business_net_pnl(self) -> Decimal | None:
        traded = tuple(item for item in self.entries if item.status is TrialStatus.TRADED)
        if any(item.business_net_pnl is None for item in traded):
            return None
        return sum(
            (item.business_net_pnl for item in traded if item.business_net_pnl is not None),
            Decimal("0"),
        )

    @property
    def unknown_cost_components(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {component for entry in self.entries for component in entry.unknown_cost_components}
            )
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "simulator_version": self.simulator_version,
            "policy_id": self.policy_id,
            "policy_provenance": dict(self.policy_provenance),
            "quantity": serialize_exact_decimal(self.quantity),
            "cost_model": self.cost_model.as_dict(),
            "opportunity_count": self.opportunity_count,
            "traded_count": self.traded_count,
            "no_trade_count": self.no_trade_count,
            "invalid_count": self.invalid_count,
            "gross_pnl": serialize_exact_decimal(self.gross_pnl),
            "known_cost_total": serialize_exact_decimal(self.known_cost_total),
            "business_net_pnl": _decimal_or_none(self.business_net_pnl),
            "unknown_cost_components": list(self.unknown_cost_components),
            "entries": [item.as_dict() for item in self.entries],
        }

    def to_json_bytes(self) -> bytes:
        return (
            json.dumps(
                self.as_dict(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_json_bytes()).hexdigest()


def bps_cost(notional: Decimal, bps: Decimal) -> Decimal:
    return notional * bps / _BPS_DENOMINATOR


def _validate_exit_quote(entry: QuoteObservation, exit_quote: QuoteObservation) -> None:
    if exit_quote.instrument_id != entry.instrument_id:
        raise SimulationValidationError("entry/exit instrument_id must match")
    if exit_quote.source_id != entry.source_id:
        raise SimulationValidationError("entry/exit source_id must match")
    if exit_quote.role is not entry.role:
        raise SimulationValidationError("entry/exit role must match")
    if exit_quote.causal_domain != entry.causal_domain:
        raise SimulationValidationError(
            "entry/exit must share a host/boot causal domain; "
            "cross-domain monotonic time is incomparable"
        )
    if exit_quote.recv_mono_ns <= entry.recv_mono_ns:
        raise SimulationValidationError("exit monotonic time must follow entry")
    if exit_quote.recv_wall_ns < entry.recv_wall_ns:
        raise SimulationValidationError("exit wall time must not precede entry")


def _require_nonnegative_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SimulationValidationError(f"{field} must be a non-negative integer")


def _require_optional_positive_decimal(value: Decimal | None, field: str) -> None:
    if value is None:
        return
    parsed = parse_exact_decimal(value)
    if parsed <= 0:
        raise SimulationValidationError(f"{field} must be positive when present")


def _decimal_or_none(value: Decimal | None) -> str | None:
    return None if value is None else serialize_exact_decimal(value)


def _require_zero_trade_accounting(entry: TrialLedgerEntry) -> None:
    zero_fields = (
        entry.quantity,
        entry.gross_pnl,
        entry.fee_cost,
        entry.latency_cost,
        entry.impact_cost,
        entry.funding_cost,
        entry.known_cost_total,
        entry.known_net_pnl,
        entry.business_net_pnl,
    )
    if any(value is None or parse_exact_decimal(value) != 0 for value in zero_fields):
        raise SimulationValidationError("NO_TRADE accounting fields must all be exact zero")
    if entry.entry_price is not None or entry.exit_price is not None:
        raise SimulationValidationError("NO_TRADE must not have execution prices")
    if entry.unknown_cost_components:
        raise SimulationValidationError("NO_TRADE cannot incur unknown cost components")
