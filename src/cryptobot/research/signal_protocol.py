from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum

from cryptobot.data.instruments import InstrumentRole
from cryptobot.data.numeric import parse_exact_decimal, serialize_exact_decimal
from cryptobot.sim import PolicyAction, SimulationOpportunity

PROTOCOL_VERSION = "stage2-signal-protocol-v1"
HORIZON_NS = 50_000_000_000
REFERENCE_LOOKBACK_NS = 5_000_000_000
MAX_FEATURE_AGE_NS = 2_000_000_000
MAX_EXECUTION_STEP_NS = 2_000_000_000
RANDOM_CONTROL_SEED = 2026092601

H1_ID = "S2-H1-BINANCE-REF-5S-SIGN-V1"
H2_ID = "S2-H2-HL-BBO-IMBALANCE-SIGN-V1"

_FAMILY_ALPHA = Decimal("0.05")
_HYPOTHESIS_COUNT = 2
_PER_HYPOTHESIS_ALPHA = Decimal("0.025")
_POWER = Decimal("0.80")
_SELECTION_ALT_ACCURACY = Decimal("0.55")
_CONFIRMATION_ALT_ACCURACY = Decimal("0.54")
_NULL_ACCURACY = Decimal("0.50")
_Z_975 = Decimal("1.959963984540054")
_Z_80 = Decimal("0.8416212335729143")


class SignalProtocolValidationError(ValueError):
    """Raised when a Stage-2 signal protocol contract is invalid."""


class DatasetPartition(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    SELECTION = "SELECTION"
    CONFIRMATION = "CONFIRMATION"


class RegistrationStatus(StrEnum):
    REGISTERED = "REGISTERED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class FeatureValue:
    value: Decimal | None
    source_event_ids: tuple[str, ...]
    asof_recv_mono_ns: int | None
    asof_recv_wall_ns: int | None
    missing_reason: str | None = None

    def __post_init__(self) -> None:
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise SignalProtocolValidationError("feature source_event_ids must be unique")
        if any(not item.strip() for item in self.source_event_ids):
            raise SignalProtocolValidationError("feature source_event_ids must be non-empty")
        _optional_nonnegative_int(self.asof_recv_mono_ns, "asof_recv_mono_ns")
        _optional_nonnegative_int(self.asof_recv_wall_ns, "asof_recv_wall_ns")
        if self.value is None:
            if self.missing_reason is None or not self.missing_reason.strip():
                raise SignalProtocolValidationError(
                    "missing feature value requires a missing_reason"
                )
            return
        parse_exact_decimal(self.value)
        if self.missing_reason is not None:
            raise SignalProtocolValidationError(
                "available feature value must not carry missing_reason"
            )
        if not self.source_event_ids:
            raise SignalProtocolValidationError("available feature value requires source_event_ids")
        if self.asof_recv_mono_ns is None or self.asof_recv_wall_ns is None:
            raise SignalProtocolValidationError(
                "available feature value requires availability timestamps"
            )

    @property
    def available(self) -> bool:
        return self.value is not None

    def as_dict(self) -> dict[str, object]:
        return {
            "value": None if self.value is None else serialize_exact_decimal(self.value),
            "source_event_ids": list(self.source_event_ids),
            "asof_recv_mono_ns": self.asof_recv_mono_ns,
            "asof_recv_wall_ns": self.asof_recv_wall_ns,
            "missing_reason": self.missing_reason,
        }


@dataclass(frozen=True, slots=True)
class OutcomeLabel:
    signed_mid_return_bps: Decimal | None
    direction: int | None
    exit_event_id: str | None
    exit_recv_mono_ns: int | None
    exit_recv_wall_ns: int | None
    invalid_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _optional_nonnegative_int(self.exit_recv_mono_ns, "exit_recv_mono_ns")
        _optional_nonnegative_int(self.exit_recv_wall_ns, "exit_recv_wall_ns")
        if tuple(sorted(set(self.invalid_reasons))) != self.invalid_reasons:
            raise SignalProtocolValidationError("outcome invalid_reasons must be unique and sorted")
        if any(not item.strip() for item in self.invalid_reasons):
            raise SignalProtocolValidationError("outcome invalid_reasons must be non-empty")
        if self.signed_mid_return_bps is None:
            if self.direction is not None:
                raise SignalProtocolValidationError(
                    "missing outcome return must have null direction"
                )
            if not self.invalid_reasons:
                raise SignalProtocolValidationError("missing outcome requires invalid_reasons")
            return
        parse_exact_decimal(self.signed_mid_return_bps)
        expected = _sign(self.signed_mid_return_bps)
        if self.direction != expected:
            raise SignalProtocolValidationError(
                "outcome direction must match signed_mid_return_bps"
            )
        if self.exit_event_id is None or not self.exit_event_id.strip():
            raise SignalProtocolValidationError("available outcome requires exit_event_id")
        if self.exit_recv_mono_ns is None or self.exit_recv_wall_ns is None:
            raise SignalProtocolValidationError("available outcome requires exit timestamps")
        if self.invalid_reasons:
            raise SignalProtocolValidationError("available outcome cannot carry invalid_reasons")

    @property
    def available(self) -> bool:
        return self.signed_mid_return_bps is not None

    def as_dict(self) -> dict[str, object]:
        return {
            "signed_mid_return_bps": (
                None
                if self.signed_mid_return_bps is None
                else serialize_exact_decimal(self.signed_mid_return_bps)
            ),
            "direction": self.direction,
            "exit_event_id": self.exit_event_id,
            "exit_recv_mono_ns": self.exit_recv_mono_ns,
            "exit_recv_wall_ns": self.exit_recv_wall_ns,
            "invalid_reasons": list(self.invalid_reasons),
        }


@dataclass(frozen=True, slots=True)
class SignalDecisionView:
    row_id: str
    opportunity_id: str
    instrument_id: str
    role: InstrumentRole
    decision_recv_mono_ns: int
    decision_recv_wall_ns: int
    decision_invalid_reasons: tuple[str, ...]
    hl_spread_bps: FeatureValue
    hl_bbo_imbalance: FeatureValue
    binance_mid_return_5s_bps: FeatureValue

    def feature_ready(self, hypothesis_id: str) -> bool:
        if self.decision_invalid_reasons:
            return False
        if hypothesis_id == H1_ID:
            return self.binance_mid_return_5s_bps.available
        if hypothesis_id == H2_ID:
            return self.hl_bbo_imbalance.available
        raise SignalProtocolValidationError(f"unknown registered hypothesis_id: {hypothesis_id}")


@dataclass(frozen=True, slots=True)
class SignalFeatureRow:
    row_id: str
    source_segment_id: str
    opportunity: SimulationOpportunity
    decision_invalid_reasons: tuple[str, ...]
    hl_spread_bps: FeatureValue
    hl_bbo_imbalance: FeatureValue
    binance_mid_return_5s_bps: FeatureValue
    outcome: OutcomeLabel

    def __post_init__(self) -> None:
        if not self.row_id.strip() or not self.source_segment_id.strip():
            raise SignalProtocolValidationError("row_id and source_segment_id must be non-empty")
        if tuple(sorted(set(self.decision_invalid_reasons))) != self.decision_invalid_reasons:
            raise SignalProtocolValidationError(
                "decision_invalid_reasons must be unique and sorted"
            )
        entry = self.opportunity.entry_quote
        for feature in (
            self.hl_spread_bps,
            self.hl_bbo_imbalance,
            self.binance_mid_return_5s_bps,
        ):
            if (
                feature.asof_recv_mono_ns is not None
                and feature.asof_recv_mono_ns > entry.recv_mono_ns
            ):
                raise SignalProtocolValidationError("feature leaks future monotonic availability")
            if (
                feature.asof_recv_wall_ns is not None
                and feature.asof_recv_wall_ns > entry.recv_wall_ns
            ):
                raise SignalProtocolValidationError("feature leaks future wall-time availability")

    @property
    def decision_recv_mono_ns(self) -> int:
        return self.opportunity.entry_quote.recv_mono_ns

    @property
    def decision_recv_wall_ns(self) -> int:
        return self.opportunity.entry_quote.recv_wall_ns

    @property
    def role(self) -> InstrumentRole:
        return self.opportunity.entry_quote.role

    @property
    def instrument_id(self) -> str:
        return self.opportunity.entry_quote.instrument_id

    def decision_view(self) -> SignalDecisionView:
        return SignalDecisionView(
            row_id=self.row_id,
            opportunity_id=self.opportunity.opportunity_id,
            instrument_id=self.instrument_id,
            role=self.role,
            decision_recv_mono_ns=self.decision_recv_mono_ns,
            decision_recv_wall_ns=self.decision_recv_wall_ns,
            decision_invalid_reasons=self.decision_invalid_reasons,
            hl_spread_bps=self.hl_spread_bps,
            hl_bbo_imbalance=self.hl_bbo_imbalance,
            binance_mid_return_5s_bps=self.binance_mid_return_5s_bps,
        )

    def as_dict(self) -> dict[str, object]:
        entry = self.opportunity.entry_quote
        exit_quote = self.opportunity.exit_quote
        return {
            "schema_version": 1,
            "protocol_version": PROTOCOL_VERSION,
            "row_id": self.row_id,
            "source_segment_id": self.source_segment_id,
            "opportunity_id": self.opportunity.opportunity_id,
            "opportunity_digest": _opportunity_digest(self.opportunity),
            "instrument_id": entry.instrument_id,
            "role": entry.role.value,
            "host_id": entry.host_id,
            "boot_id": entry.boot_id,
            "decision_event_id": entry.event_id,
            "decision_recv_mono_ns": entry.recv_mono_ns,
            "decision_recv_wall_ns": entry.recv_wall_ns,
            "exit_event_id": None if exit_quote is None else exit_quote.event_id,
            "decision_invalid_reasons": list(self.decision_invalid_reasons),
            "features": {
                "hl_spread_bps": self.hl_spread_bps.as_dict(),
                "hl_bbo_imbalance": self.hl_bbo_imbalance.as_dict(),
                "binance_mid_return_5s_bps": self.binance_mid_return_5s_bps.as_dict(),
            },
            "outcome": self.outcome.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class Stage2FeatureDataset:
    source_gate_report_sha256: str
    source_campaign_manifest_sha256: str
    source_segment_digests: tuple[tuple[str, str], ...]
    rows: tuple[SignalFeatureRow, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.source_gate_report_sha256, "source_gate_report_sha256")
        _require_sha256(
            self.source_campaign_manifest_sha256,
            "source_campaign_manifest_sha256",
        )
        if len(set(segment_id for segment_id, _ in self.source_segment_digests)) != len(
            self.source_segment_digests
        ):
            raise SignalProtocolValidationError("source segment IDs must be unique")
        for segment_id, digest in self.source_segment_digests:
            if not segment_id.strip():
                raise SignalProtocolValidationError("source segment_id must be non-empty")
            _require_sha256(digest, "source segment digest")
        expected = tuple(sorted(self.rows, key=_row_sort_key))
        if expected != self.rows:
            raise SignalProtocolValidationError(
                "feature dataset rows must be in deterministic chronological order"
            )
        row_ids = [row.row_id for row in self.rows]
        if len(set(row_ids)) != len(row_ids):
            raise SignalProtocolValidationError("feature row_id must be unique")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "protocol_version": PROTOCOL_VERSION,
            "source_gate_report_sha256": self.source_gate_report_sha256,
            "source_campaign_manifest_sha256": self.source_campaign_manifest_sha256,
            "source_segment_digests": [
                {"segment_id": segment_id, "dataset_bundle_sha256": digest}
                for segment_id, digest in self.source_segment_digests
            ],
            "row_count": len(self.rows),
            "rows": [row.as_dict() for row in self.rows],
        }

    def to_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self.as_dict())

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_json_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class PowerPlan:
    family_alpha: Decimal = _FAMILY_ALPHA
    hypothesis_count: int = _HYPOTHESIS_COUNT
    per_hypothesis_alpha: Decimal = _PER_HYPOTHESIS_ALPHA
    power: Decimal = _POWER
    selection_alternative_accuracy: Decimal = _SELECTION_ALT_ACCURACY
    confirmation_alternative_accuracy: Decimal = _CONFIRMATION_ALT_ACCURACY

    def __post_init__(self) -> None:
        if self.hypothesis_count != 2:
            raise SignalProtocolValidationError(
                "first Stage-2 protocol is frozen to exactly two hypotheses"
            )
        if self.family_alpha != Decimal("0.05"):
            raise SignalProtocolValidationError("family_alpha is frozen to 0.05")
        if self.per_hypothesis_alpha != Decimal("0.025"):
            raise SignalProtocolValidationError(
                "per_hypothesis_alpha is frozen to Bonferroni 0.025"
            )
        if self.power != Decimal("0.80"):
            raise SignalProtocolValidationError("planning power is frozen to 0.80")

    @property
    def selection_min_evaluable(self) -> int:
        return directional_accuracy_planning_count(self.selection_alternative_accuracy)

    @property
    def confirmation_min_evaluable(self) -> int:
        return directional_accuracy_planning_count(self.confirmation_alternative_accuracy)

    def as_dict(self) -> dict[str, object]:
        return {
            "family_alpha": serialize_exact_decimal(self.family_alpha),
            "hypothesis_count": self.hypothesis_count,
            "per_hypothesis_alpha": serialize_exact_decimal(self.per_hypothesis_alpha),
            "power": serialize_exact_decimal(self.power),
            "planning_null_directional_accuracy": "0.50",
            "selection_alternative_accuracy": serialize_exact_decimal(
                self.selection_alternative_accuracy
            ),
            "selection_min_evaluable": self.selection_min_evaluable,
            "confirmation_alternative_accuracy": serialize_exact_decimal(
                self.confirmation_alternative_accuracy
            ),
            "confirmation_min_evaluable": self.confirmation_min_evaluable,
            "planning_note": (
                "Normal-approximation directional-accuracy support is a planning floor; "
                "directional hit rate is not the optimization target."
            ),
        }


@dataclass(frozen=True, slots=True)
class PartitionPlan:
    selection_start_wall_ns: int
    confirmation_start_wall_ns: int
    development_row_count: int
    selection_row_count: int
    confirmation_row_count: int
    selection_h1_ready: int
    selection_h2_ready: int
    confirmation_h1_ready: int
    confirmation_h2_ready: int
    power_plan: PowerPlan

    def __post_init__(self) -> None:
        _nonnegative_int(self.selection_start_wall_ns, "selection_start_wall_ns")
        _nonnegative_int(
            self.confirmation_start_wall_ns,
            "confirmation_start_wall_ns",
        )
        if self.selection_start_wall_ns >= self.confirmation_start_wall_ns:
            raise SignalProtocolValidationError(
                "selection boundary must precede confirmation boundary"
            )
        if self.development_row_count <= 0:
            raise SignalProtocolValidationError(
                "development partition must contain at least one row"
            )
        if self.selection_h1_ready < self.power_plan.selection_min_evaluable:
            raise SignalProtocolValidationError("selection H1 support is insufficient")
        if self.selection_h2_ready < self.power_plan.selection_min_evaluable:
            raise SignalProtocolValidationError("selection H2 support is insufficient")
        if self.confirmation_h1_ready < self.power_plan.confirmation_min_evaluable:
            raise SignalProtocolValidationError("confirmation H1 support is insufficient")
        if self.confirmation_h2_ready < self.power_plan.confirmation_min_evaluable:
            raise SignalProtocolValidationError("confirmation H2 support is insufficient")

    def partition_for(self, decision_recv_wall_ns: int) -> DatasetPartition:
        if decision_recv_wall_ns < self.selection_start_wall_ns:
            return DatasetPartition.DEVELOPMENT
        if decision_recv_wall_ns < self.confirmation_start_wall_ns:
            return DatasetPartition.SELECTION
        return DatasetPartition.CONFIRMATION

    def as_dict(self) -> dict[str, object]:
        return {
            "selection_start_wall_ns": self.selection_start_wall_ns,
            "confirmation_start_wall_ns": self.confirmation_start_wall_ns,
            "development_row_count": self.development_row_count,
            "selection_row_count": self.selection_row_count,
            "confirmation_row_count": self.confirmation_row_count,
            "selection_h1_ready": self.selection_h1_ready,
            "selection_h2_ready": self.selection_h2_ready,
            "confirmation_h1_ready": self.confirmation_h1_ready,
            "confirmation_h2_ready": self.confirmation_h2_ready,
            "power_plan": self.power_plan.as_dict(),
            "boundary_semantics": (
                "Derived from PRIMARY decision-time feature availability only; "
                "future outcomes are not consulted. Equal wall timestamps stay in "
                "the later partition."
            ),
        }


@dataclass(frozen=True, slots=True)
class HypothesisDefinition:
    hypothesis_id: str
    feature_name: str
    action_rule: str
    lookback_ns: int | None

    def __post_init__(self) -> None:
        if not self.hypothesis_id.strip() or not self.feature_name.strip():
            raise SignalProtocolValidationError("hypothesis_id and feature_name must be non-empty")
        if not self.action_rule.strip():
            raise SignalProtocolValidationError("action_rule must be non-empty")
        if self.lookback_ns is not None and (
            isinstance(self.lookback_ns, bool)
            or not isinstance(self.lookback_ns, int)
            or self.lookback_ns < 0
        ):
            raise SignalProtocolValidationError(
                "lookback_ns must be null or a non-negative integer"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "feature_name": self.feature_name,
            "action_rule": self.action_rule,
            "lookback_ns": self.lookback_ns,
        }


@dataclass(frozen=True, slots=True)
class TrialRegistration:
    trial_id: str
    hypothesis_id: str
    stage: str
    status: RegistrationStatus = RegistrationStatus.REGISTERED

    def __post_init__(self) -> None:
        if not self.trial_id.strip() or not self.hypothesis_id.strip():
            raise SignalProtocolValidationError("trial_id and hypothesis_id must be non-empty")
        if self.stage not in {"SELECTION", "CONFIRMATION"}:
            raise SignalProtocolValidationError("trial stage must be SELECTION or CONFIRMATION")
        if not isinstance(self.status, RegistrationStatus):
            raise SignalProtocolValidationError("registration status must be RegistrationStatus")

    def as_dict(self) -> dict[str, object]:
        return {
            "trial_id": self.trial_id,
            "hypothesis_id": self.hypothesis_id,
            "stage": self.stage,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class TrialRegistry:
    registrations: tuple[TrialRegistration, ...]

    def __post_init__(self) -> None:
        ids = [item.trial_id for item in self.registrations]
        if len(ids) != len(set(ids)):
            raise SignalProtocolValidationError("trial_id must be unique")
        allowed = {H1_ID, H2_ID, "SELECTION_CHAMPION_ONLY"}
        if not {item.hypothesis_id for item in self.registrations} <= allowed:
            raise SignalProtocolValidationError("registry contains an unregistered hypothesis")

    def as_dict(self) -> dict[str, object]:
        return {
            "registrations": [item.as_dict() for item in self.registrations],
            "runner_up_confirmation_rule": (
                "If the selection champion fails untouched confirmation, no runner-up "
                "may be tested on that same confirmation partition."
            ),
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json_bytes(self.as_dict())).hexdigest()


HYPOTHESES = (
    HypothesisDefinition(
        hypothesis_id=H1_ID,
        feature_name="binance_mid_return_5s_bps",
        action_rule="value > 0 => LONG; value < 0 => SHORT; zero/missing => ABSTAIN",
        lookback_ns=REFERENCE_LOOKBACK_NS,
    ),
    HypothesisDefinition(
        hypothesis_id=H2_ID,
        feature_name="hl_bbo_imbalance",
        action_rule="value > 0 => LONG; value < 0 => SHORT; zero/missing => ABSTAIN",
        lookback_ns=None,
    ),
)

TRIAL_REGISTRY = TrialRegistry(
    registrations=(
        TrialRegistration("S2-SEL-H1-V1", H1_ID, "SELECTION"),
        TrialRegistration("S2-SEL-H2-V1", H2_ID, "SELECTION"),
        TrialRegistration(
            "S2-CONFIRM-CHAMPION-V1",
            "SELECTION_CHAMPION_ONLY",
            "CONFIRMATION",
        ),
    )
)


def directional_accuracy_planning_count(
    alternative_accuracy: Decimal,
) -> int:
    p1 = parse_exact_decimal(alternative_accuracy)
    if p1 <= _NULL_ACCURACY or p1 >= 1:
        raise SignalProtocolValidationError(
            "alternative_accuracy must be strictly between 0.50 and 1"
        )
    null_var = (_NULL_ACCURACY * (Decimal(1) - _NULL_ACCURACY)).sqrt()
    alt_var = (p1 * (Decimal(1) - p1)).sqrt()
    numerator = (_Z_975 * null_var + _Z_80 * alt_var) ** 2
    denominator = (p1 - _NULL_ACCURACY) ** 2
    return int((numerator / denominator).to_integral_value(rounding=ROUND_CEILING))


def derive_partition_plan(
    primary_rows: tuple[SignalFeatureRow, ...],
    *,
    power_plan: PowerPlan | None = None,
) -> PartitionPlan:
    plan = power_plan or PowerPlan()
    rows = tuple(sorted(primary_rows, key=_row_sort_key))
    if not rows:
        raise SignalProtocolValidationError("partition derivation requires PRIMARY rows")
    if any(row.role is not InstrumentRole.PRIMARY for row in rows):
        raise SignalProtocolValidationError("partition derivation must use PRIMARY rows only")

    confirmation_start = _suffix_start_for_support(
        rows,
        end=len(rows),
        minimum=plan.confirmation_min_evaluable,
    )
    confirmation_start = _first_equal_wall_index(rows, confirmation_start)

    selection_start = _suffix_start_for_support(
        rows,
        end=confirmation_start,
        minimum=plan.selection_min_evaluable,
    )
    selection_start = _first_equal_wall_index(rows, selection_start)

    if selection_start <= 0:
        raise SignalProtocolValidationError("dataset leaves no untouched development partition")
    if (
        rows[selection_start].decision_recv_wall_ns
        >= rows[confirmation_start].decision_recv_wall_ns
    ):
        raise SignalProtocolValidationError("chronological partition wall boundaries collapse")

    selection_rows = rows[selection_start:confirmation_start]
    confirmation_rows = rows[confirmation_start:]
    return PartitionPlan(
        selection_start_wall_ns=rows[selection_start].decision_recv_wall_ns,
        confirmation_start_wall_ns=rows[confirmation_start].decision_recv_wall_ns,
        development_row_count=selection_start,
        selection_row_count=len(selection_rows),
        confirmation_row_count=len(confirmation_rows),
        selection_h1_ready=_ready_count(selection_rows, H1_ID),
        selection_h2_ready=_ready_count(selection_rows, H2_ID),
        confirmation_h1_ready=_ready_count(confirmation_rows, H1_ID),
        confirmation_h2_ready=_ready_count(confirmation_rows, H2_ID),
        power_plan=plan,
    )


def partition_rows(
    rows: tuple[SignalFeatureRow, ...],
    *,
    plan: PartitionPlan,
    partition: DatasetPartition,
    role: InstrumentRole | None = None,
) -> tuple[SignalFeatureRow, ...]:
    selected = tuple(
        row
        for row in sorted(rows, key=_row_sort_key)
        if plan.partition_for(row.decision_recv_wall_ns) is partition
        and (role is None or row.role is role)
    )
    return selected


def hypothesis_action(
    decision: SignalDecisionView,
    *,
    hypothesis_id: str,
) -> PolicyAction:
    if not decision.feature_ready(hypothesis_id):
        return PolicyAction.ABSTAIN
    if hypothesis_id == H1_ID:
        value = decision.binance_mid_return_5s_bps.value
    elif hypothesis_id == H2_ID:
        value = decision.hl_bbo_imbalance.value
    else:
        raise SignalProtocolValidationError(f"unknown registered hypothesis_id: {hypothesis_id}")
    if value is None or value == 0:
        return PolicyAction.ABSTAIN
    return PolicyAction.LONG if value > 0 else PolicyAction.SHORT


def _suffix_start_for_support(
    rows: tuple[SignalFeatureRow, ...],
    *,
    end: int,
    minimum: int,
) -> int:
    h1 = 0
    h2 = 0
    for index in range(end - 1, -1, -1):
        view = rows[index].decision_view()
        h1 += int(view.feature_ready(H1_ID))
        h2 += int(view.feature_ready(H2_ID))
        if h1 >= minimum and h2 >= minimum:
            return index
    raise SignalProtocolValidationError(
        "insufficient decision-time feature support for frozen partition plan"
    )


def _first_equal_wall_index(
    rows: tuple[SignalFeatureRow, ...],
    index: int,
) -> int:
    wall = rows[index].decision_recv_wall_ns
    while index > 0 and rows[index - 1].decision_recv_wall_ns == wall:
        index -= 1
    return index


def _ready_count(
    rows: tuple[SignalFeatureRow, ...],
    hypothesis_id: str,
) -> int:
    return sum(row.decision_view().feature_ready(hypothesis_id) for row in rows)


def _row_sort_key(row: SignalFeatureRow) -> tuple[int, int, str]:
    return (
        row.decision_recv_wall_ns,
        row.decision_recv_mono_ns,
        row.row_id,
    )


def _opportunity_digest(opportunity: SimulationOpportunity) -> str:
    entry = opportunity.entry_quote
    exit_quote = opportunity.exit_quote
    payload = {
        "opportunity_id": opportunity.opportunity_id,
        "entry": {
            "event_id": entry.event_id,
            "source_id": entry.source_id,
            "instrument_id": entry.instrument_id,
            "role": entry.role.value,
            "host_id": entry.host_id,
            "boot_id": entry.boot_id,
            "recv_mono_ns": entry.recv_mono_ns,
            "recv_wall_ns": entry.recv_wall_ns,
            "bid_price": (
                None if entry.bid_price is None else serialize_exact_decimal(entry.bid_price)
            ),
            "ask_price": (
                None if entry.ask_price is None else serialize_exact_decimal(entry.ask_price)
            ),
            "quality_flags": int(entry.quality_flags),
        },
        "exit": (
            None
            if exit_quote is None
            else {
                "event_id": exit_quote.event_id,
                "recv_mono_ns": exit_quote.recv_mono_ns,
                "recv_wall_ns": exit_quote.recv_wall_ns,
                "bid_price": (
                    None
                    if exit_quote.bid_price is None
                    else serialize_exact_decimal(exit_quote.bid_price)
                ),
                "ask_price": (
                    None
                    if exit_quote.ask_price is None
                    else serialize_exact_decimal(exit_quote.ask_price)
                ),
                "quality_flags": int(exit_quote.quality_flags),
            }
        ),
        "context_event_ids": [item.event_id for item in opportunity.context_quotes],
        "interval_invalid_reasons": list(opportunity.interval_invalid_reasons),
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode()


def _sign(value: Decimal) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _require_sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise SignalProtocolValidationError(f"{field} must be 64 lowercase hex characters")


def _nonnegative_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SignalProtocolValidationError(f"{field} must be a non-negative integer")


def _optional_nonnegative_int(value: int | None, field: str) -> None:
    if value is not None:
        _nonnegative_int(value, field)
