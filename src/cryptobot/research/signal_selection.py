from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal, localcontext
from enum import StrEnum
from pathlib import Path

from cryptobot.data.instruments import InstrumentRole
from cryptobot.data.numeric import serialize_exact_decimal
from cryptobot.research.signal_protocol import (
    H1_ID,
    H2_ID,
    RANDOM_CONTROL_SEED,
    TRIAL_REGISTRY,
    PowerPlan,
    SignalFeatureRow,
    hypothesis_action,
)
from cryptobot.sim import (
    CostEvidenceClass,
    CostInput,
    CostModel,
    DecisionContext,
    NoTradePolicy,
    PolicyAction,
    PolicyDecision,
    RandomizedDirectionPolicy,
    SimulationReport,
    TrialStatus,
    run_simulation,
)

EXPECTED_PROTOCOL_SHA256 = "2e2404b93e82ad8ac6ff27b10b5f4d22cd7ac624be69a277c6aed75a3b9c9843"
EXPECTED_DATASET_SHA256 = "3eeb0b405a9db439b7711b453ec9820707068bbfba855bf120124b79aa32b237"
SELECTION_START_WALL_NS = 1790235572690884130
CONFIRMATION_START_WALL_NS = 1790302269067780894
EXPECTED_SELECTION_ROW_COUNT = 1123
SELECTION_SIM_QUANTITY = Decimal("1")
_SELECTION_ALPHA = Decimal("0.025")
_HALF = Decimal("0.5")
_Z_975 = Decimal("1.959963984540054")
_MAX_AUTOCORRELATION_LAG = 10
_H1_TRIAL_ID = "S2-SEL-H1-V1"
_H2_TRIAL_ID = "S2-SEL-H2-V1"


class SignalSelectionValidationError(ValueError):
    """Raised when a registered Stage-2 selection run violates its frozen contract."""


class SelectionDecision(StrEnum):
    SELECTION_CHAMPION_H1 = "SELECTION_CHAMPION_H1"
    SELECTION_CHAMPION_H2 = "SELECTION_CHAMPION_H2"
    STOP_FAIL_SIGNAL_SELECTION = "STOP_FAIL_SIGNAL_SELECTION"
    INCONCLUSIVE_SELECTION = "INCONCLUSIVE_SELECTION"


@dataclass(frozen=True, slots=True)
class SelectionTrialResult:
    trial_id: str
    hypothesis_id: str
    selection_row_count: int
    feature_ready_count: int
    abstain_count: int
    outcome_valid_count: int
    directional_evaluable_count: int
    correct_direction_count: int
    directional_accuracy: Decimal | None
    iid_reference_p_value: Decimal | None
    autocorrelations: tuple[Decimal | None, ...]
    design_effect: Decimal | None
    effective_sample_size: int
    wilson_lower_bound: Decimal | None
    simulation_sha256: str
    simulation_opportunity_count: int
    simulation_traded_count: int
    simulation_no_trade_count: int
    simulation_invalid_count: int
    mean_partial_known_cost_pnl: Decimal | None
    passed: bool
    failure_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.trial_id.strip() or not self.hypothesis_id.strip():
            raise SignalSelectionValidationError("trial_id and hypothesis_id must be non-empty")
        if len(self.autocorrelations) != _MAX_AUTOCORRELATION_LAG:
            raise SignalSelectionValidationError("autocorrelation vector must contain lags 1..10")
        if self.effective_sample_size > self.directional_evaluable_count:
            raise SignalSelectionValidationError(
                "effective sample size cannot exceed directional-evaluable count"
            )
        if tuple(sorted(set(self.failure_reasons))) != self.failure_reasons:
            raise SignalSelectionValidationError("failure_reasons must be unique and sorted")
        if self.passed and self.failure_reasons:
            raise SignalSelectionValidationError("passed trial cannot contain failure reasons")

    def as_dict(self) -> dict[str, object]:
        return {
            "trial_id": self.trial_id,
            "hypothesis_id": self.hypothesis_id,
            "selection_row_count": self.selection_row_count,
            "feature_ready_count": self.feature_ready_count,
            "abstain_count": self.abstain_count,
            "outcome_valid_count": self.outcome_valid_count,
            "directional_evaluable_count": self.directional_evaluable_count,
            "correct_direction_count": self.correct_direction_count,
            "directional_accuracy": _decimal_or_none(self.directional_accuracy),
            "iid_reference_p_value": _decimal_or_none(self.iid_reference_p_value),
            "autocorrelations": [_decimal_or_none(value) for value in self.autocorrelations],
            "design_effect": _decimal_or_none(self.design_effect),
            "effective_sample_size": self.effective_sample_size,
            "wilson_lower_bound": _decimal_or_none(self.wilson_lower_bound),
            "simulation_sha256": self.simulation_sha256,
            "simulation_opportunity_count": self.simulation_opportunity_count,
            "simulation_traded_count": self.simulation_traded_count,
            "simulation_no_trade_count": self.simulation_no_trade_count,
            "simulation_invalid_count": self.simulation_invalid_count,
            "mean_partial_known_cost_pnl": _decimal_or_none(self.mean_partial_known_cost_pnl),
            "passed": self.passed,
            "failure_reasons": list(self.failure_reasons),
        }


@dataclass(frozen=True, slots=True)
class SelectionControlResult:
    policy_id: str
    policy_provenance: tuple[tuple[str, str], ...]
    simulation_sha256: str
    opportunity_count: int
    traded_count: int
    no_trade_count: int
    invalid_count: int
    opportunity_ids_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_provenance": dict(self.policy_provenance),
            "simulation_sha256": self.simulation_sha256,
            "opportunity_count": self.opportunity_count,
            "traded_count": self.traded_count,
            "no_trade_count": self.no_trade_count,
            "invalid_count": self.invalid_count,
            "opportunity_ids_sha256": self.opportunity_ids_sha256,
        }


@dataclass(frozen=True, slots=True)
class SelectionReport:
    protocol_sha256: str
    dataset_sha256: str
    trial_registry_sha256: str
    selection_start_wall_ns: int
    confirmation_start_wall_ns: int
    selection_row_count: int
    selection_row_ids_sha256: str
    selection_opportunity_ids_sha256: str
    quantity: Decimal
    cost_model: CostModel
    trials: tuple[SelectionTrialResult, ...]
    controls: tuple[SelectionControlResult, ...]
    decision: SelectionDecision
    champion_hypothesis_id: str | None

    def __post_init__(self) -> None:
        _require_sha256(self.protocol_sha256, "protocol_sha256")
        _require_sha256(self.dataset_sha256, "dataset_sha256")
        _require_sha256(self.trial_registry_sha256, "trial_registry_sha256")
        _require_sha256(self.selection_row_ids_sha256, "selection_row_ids_sha256")
        _require_sha256(
            self.selection_opportunity_ids_sha256,
            "selection_opportunity_ids_sha256",
        )
        if tuple(item.hypothesis_id for item in self.trials) != (H1_ID, H2_ID):
            raise SignalSelectionValidationError(
                "selection report must contain only registered H1/H2 in frozen order"
            )
        if self.decision is SelectionDecision.SELECTION_CHAMPION_H1:
            if self.champion_hypothesis_id != H1_ID:
                raise SignalSelectionValidationError("H1 champion decision requires H1 champion")
        elif self.decision is SelectionDecision.SELECTION_CHAMPION_H2:
            if self.champion_hypothesis_id != H2_ID:
                raise SignalSelectionValidationError("H2 champion decision requires H2 champion")
        elif self.champion_hypothesis_id is not None:
            raise SignalSelectionValidationError(
                "non-champion selection decision must not carry champion_hypothesis_id"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "report_version": "stage2-selection-v1",
            "protocol_sha256": self.protocol_sha256,
            "dataset_sha256": self.dataset_sha256,
            "trial_registry_sha256": self.trial_registry_sha256,
            "selection_start_wall_ns": self.selection_start_wall_ns,
            "confirmation_start_wall_ns": self.confirmation_start_wall_ns,
            "selection_row_count": self.selection_row_count,
            "selection_row_ids_sha256": self.selection_row_ids_sha256,
            "selection_opportunity_ids_sha256": self.selection_opportunity_ids_sha256,
            "quantity": serialize_exact_decimal(self.quantity),
            "cost_model": self.cost_model.as_dict(),
            "trials": [trial.as_dict() for trial in self.trials],
            "controls": [control.as_dict() for control in self.controls],
            "decision": self.decision.value,
            "champion_hypothesis_id": self.champion_hypothesis_id,
            "confirmation_opened": False,
            "business_net_evaluable": False,
        }

    def to_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self.as_dict())

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_json_bytes()).hexdigest()


@dataclass(slots=True)
class _RegisteredHypothesisPolicy:
    hypothesis_id: str
    actions: dict[str, PolicyAction]

    @property
    def policy_id(self) -> str:
        return f"registered.{self.hypothesis_id}"

    @property
    def provenance(self) -> tuple[tuple[str, str], ...]:
        return (
            ("hypothesis_id", self.hypothesis_id),
            ("policy_rule", "FROZEN_SIGN_V1"),
        )

    def decide(self, context: DecisionContext) -> PolicyDecision:
        action = self.actions.get(context.opportunity_id)
        if action is None:
            raise SignalSelectionValidationError(
                f"missing frozen action for opportunity_id: {context.opportunity_id}"
            )
        return PolicyDecision(
            action=action,
            reason=f"REGISTERED_{self.hypothesis_id}",
        )


def frozen_selection_cost_model() -> CostModel:
    unknown = CostInput(CostEvidenceClass.UNKNOWN, None)
    return CostModel(
        fee_per_side=CostInput(CostEvidenceClass.SCENARIO, Decimal("4.5")),
        latency_per_side=unknown,
        impact_per_side=unknown,
        funding_round_trip=unknown,
    )


def evaluate_registered_selection(
    rows: tuple[SignalFeatureRow, ...],
    *,
    protocol_sha256: str = EXPECTED_PROTOCOL_SHA256,
    dataset_sha256: str = EXPECTED_DATASET_SHA256,
) -> SelectionReport:
    _validate_frozen_hash(protocol_sha256, EXPECTED_PROTOCOL_SHA256, "protocol")
    _validate_frozen_hash(dataset_sha256, EXPECTED_DATASET_SHA256, "dataset")
    ordered = _validate_selection_rows(rows)
    cost_model = frozen_selection_cost_model()
    trials = tuple(
        _evaluate_trial(
            ordered,
            hypothesis_id=hypothesis_id,
            trial_id=trial_id,
            cost_model=cost_model,
        )
        for hypothesis_id, trial_id in (
            (H1_ID, _H1_TRIAL_ID),
            (H2_ID, _H2_TRIAL_ID),
        )
    )
    controls = _run_controls(ordered, cost_model=cost_model)
    decision, champion = _selection_decision(trials)

    opportunity_ids = tuple(row.opportunity.opportunity_id for row in ordered)
    row_ids = tuple(row.row_id for row in ordered)
    return SelectionReport(
        protocol_sha256=protocol_sha256,
        dataset_sha256=dataset_sha256,
        trial_registry_sha256=TRIAL_REGISTRY.sha256,
        selection_start_wall_ns=SELECTION_START_WALL_NS,
        confirmation_start_wall_ns=CONFIRMATION_START_WALL_NS,
        selection_row_count=len(ordered),
        selection_row_ids_sha256=_string_sequence_sha256(row_ids),
        selection_opportunity_ids_sha256=_string_sequence_sha256(opportunity_ids),
        quantity=SELECTION_SIM_QUANTITY,
        cost_model=cost_model,
        trials=trials,
        controls=controls,
        decision=decision,
        champion_hypothesis_id=champion,
    )


def write_selection_report(
    report: SelectionReport,
    path: str | Path,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_json_bytes()
    try:
        with target.open("xb") as stream:
            stream.write(payload)
            stream.flush()
    except FileExistsError:
        if target.read_bytes() != payload:
            raise SignalSelectionValidationError(
                "existing selection report differs from deterministic output"
            ) from None
    return target


def exact_binomial_upper_tail(*, correct: int, total: int) -> Decimal:
    if total < 0 or correct < 0 or correct > total:
        raise SignalSelectionValidationError("invalid binomial counts")
    if total == 0:
        return Decimal(1)
    numerator = sum(math.comb(total, value) for value in range(correct, total + 1))
    denominator = 1 << total
    with localcontext() as ctx:
        ctx.prec = 80
        return Decimal(numerator) / Decimal(denominator)


def correctness_autocorrelations(
    correctness: tuple[int, ...],
    *,
    max_lag: int = _MAX_AUTOCORRELATION_LAG,
) -> tuple[Decimal | None, ...]:
    if max_lag <= 0:
        raise SignalSelectionValidationError("max_lag must be positive")
    if any(value not in (0, 1) for value in correctness):
        raise SignalSelectionValidationError("correctness series must contain only 0/1")

    n = len(correctness)
    if n == 0:
        return tuple(None for _ in range(max_lag))

    with localcontext() as ctx:
        ctx.prec = 60
        mean = Decimal(sum(correctness)) / Decimal(n)
        centered = tuple(Decimal(value) - mean for value in correctness)
        denominator = sum((value * value for value in centered), Decimal(0))
        output: list[Decimal | None] = []
        for lag in range(1, max_lag + 1):
            if lag >= n:
                output.append(None)
                continue
            if denominator == 0:
                output.append(Decimal(0))
                continue
            numerator = sum(
                (centered[index] * centered[index + lag] for index in range(n - lag)),
                Decimal(0),
            )
            output.append(numerator / denominator)
        return tuple(output)


def dependence_design_effect(
    autocorrelations: tuple[Decimal | None, ...],
) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 60
        positive_sum = sum(
            (value for value in autocorrelations if value is not None and value > 0),
            Decimal(0),
        )
        raw = Decimal(1) + Decimal(2) * positive_sum
        return max(Decimal(1), raw)


def effective_sample_size(*, evaluable_count: int, design_effect: Decimal) -> int:
    if evaluable_count < 0:
        raise SignalSelectionValidationError("evaluable_count must be non-negative")
    if design_effect < 1:
        raise SignalSelectionValidationError("design_effect must be >= 1")
    if evaluable_count == 0:
        return 0
    with localcontext() as ctx:
        ctx.prec = 60
        result = int(
            (Decimal(evaluable_count) / design_effect).to_integral_value(rounding=ROUND_FLOOR)
        )
    return max(1, min(evaluable_count, result))


def wilson_lower_bound(
    *,
    correct: int,
    total: int,
    effective_n: int,
) -> Decimal | None:
    if total <= 0 or correct < 0 or correct > total:
        return None
    if effective_n <= 0 or effective_n > total:
        return None

    with localcontext() as ctx:
        ctx.prec = 60
        p_hat = Decimal(correct) / Decimal(total)
        n_eff = Decimal(effective_n)
        z2 = _Z_975 * _Z_975
        denominator = Decimal(1) + z2 / n_eff
        center = p_hat + z2 / (Decimal(2) * n_eff)
        variance_term = p_hat * (Decimal(1) - p_hat) / n_eff + z2 / (Decimal(4) * n_eff * n_eff)
        lower = (center - _Z_975 * variance_term.sqrt()) / denominator
        return max(Decimal(0), lower)


def _evaluate_trial(
    rows: tuple[SignalFeatureRow, ...],
    *,
    hypothesis_id: str,
    trial_id: str,
    cost_model: CostModel,
) -> SelectionTrialResult:
    actions: dict[str, PolicyAction] = {}
    feature_ready_count = 0
    abstain_count = 0
    outcome_valid_count = 0
    correctness: list[int] = []

    for row in rows:
        view = row.decision_view()
        feature_ready_count += int(view.feature_ready(hypothesis_id))
        action = hypothesis_action(view, hypothesis_id=hypothesis_id)
        actions[row.opportunity.opportunity_id] = action
        abstain_count += int(action is PolicyAction.ABSTAIN)
        outcome_valid_count += int(row.outcome.available)
        direction = row.outcome.direction
        if (
            action in (PolicyAction.LONG, PolicyAction.SHORT)
            and row.outcome.available
            and direction in (-1, 1)
        ):
            correct = (action is PolicyAction.LONG and direction == 1) or (
                action is PolicyAction.SHORT and direction == -1
            )
            correctness.append(int(correct))

    policy = _RegisteredHypothesisPolicy(
        hypothesis_id=hypothesis_id,
        actions=actions,
    )
    simulation = run_simulation(
        tuple(row.opportunity for row in rows),
        policy=policy,
        cost_model=cost_model,
        quantity=SELECTION_SIM_QUANTITY,
    )

    evaluable = len(correctness)
    correct_count = sum(correctness)
    accuracy = _ratio(correct_count, evaluable)
    p_value = (
        None
        if evaluable == 0
        else exact_binomial_upper_tail(correct=correct_count, total=evaluable)
    )
    autocorrelations = correctness_autocorrelations(tuple(correctness))
    design_effect = None if evaluable == 0 else dependence_design_effect(autocorrelations)
    effective_n = (
        0
        if design_effect is None
        else effective_sample_size(
            evaluable_count=evaluable,
            design_effect=design_effect,
        )
    )
    lower = wilson_lower_bound(
        correct=correct_count,
        total=evaluable,
        effective_n=effective_n,
    )
    mean_partial = _mean_partial_known_cost_pnl(simulation)

    power = PowerPlan()
    failures: list[str] = []
    if evaluable < power.selection_min_evaluable:
        failures.append("INSUFFICIENT_DIRECTIONAL_EVALUABLE_SUPPORT")
    if p_value is None or p_value > _SELECTION_ALPHA:
        failures.append("IID_REFERENCE_P_VALUE_ABOVE_ALPHA")
    if lower is None or lower <= _HALF:
        failures.append("DEPENDENCE_ADJUSTED_LOWER_BOUND_NOT_ABOVE_HALF")
    if mean_partial is None or mean_partial <= 0:
        failures.append("NONPOSITIVE_MEAN_PARTIAL_KNOWN_COST_PNL")

    failure_reasons = tuple(sorted(failures))
    return SelectionTrialResult(
        trial_id=trial_id,
        hypothesis_id=hypothesis_id,
        selection_row_count=len(rows),
        feature_ready_count=feature_ready_count,
        abstain_count=abstain_count,
        outcome_valid_count=outcome_valid_count,
        directional_evaluable_count=evaluable,
        correct_direction_count=correct_count,
        directional_accuracy=accuracy,
        iid_reference_p_value=p_value,
        autocorrelations=autocorrelations,
        design_effect=design_effect,
        effective_sample_size=effective_n,
        wilson_lower_bound=lower,
        simulation_sha256=simulation.sha256,
        simulation_opportunity_count=simulation.opportunity_count,
        simulation_traded_count=simulation.traded_count,
        simulation_no_trade_count=simulation.no_trade_count,
        simulation_invalid_count=simulation.invalid_count,
        mean_partial_known_cost_pnl=mean_partial,
        passed=not failure_reasons,
        failure_reasons=failure_reasons,
    )


def _run_controls(
    rows: tuple[SignalFeatureRow, ...],
    *,
    cost_model: CostModel,
) -> tuple[SelectionControlResult, ...]:
    opportunities = tuple(row.opportunity for row in rows)
    expected_ids = tuple(item.opportunity_id for item in opportunities)
    expected_digest = _string_sequence_sha256(expected_ids)

    controls = (
        NoTradePolicy(),
        RandomizedDirectionPolicy(seed=RANDOM_CONTROL_SEED),
    )
    output: list[SelectionControlResult] = []
    for policy in controls:
        simulation = run_simulation(
            opportunities,
            policy=policy,
            cost_model=cost_model,
            quantity=SELECTION_SIM_QUANTITY,
        )
        actual_ids = tuple(item.opportunity_id for item in simulation.entries)
        actual_digest = _string_sequence_sha256(actual_ids)
        if actual_digest != expected_digest:
            raise SignalSelectionValidationError(
                "control simulation opportunity IDs differ from frozen selection rows"
            )
        output.append(
            SelectionControlResult(
                policy_id=policy.policy_id,
                policy_provenance=policy.provenance,
                simulation_sha256=simulation.sha256,
                opportunity_count=simulation.opportunity_count,
                traded_count=simulation.traded_count,
                no_trade_count=simulation.no_trade_count,
                invalid_count=simulation.invalid_count,
                opportunity_ids_sha256=actual_digest,
            )
        )
    return tuple(output)


def _selection_decision(
    trials: tuple[SelectionTrialResult, ...],
) -> tuple[SelectionDecision, str | None]:
    power = PowerPlan()
    if any(trial.directional_evaluable_count < power.selection_min_evaluable for trial in trials):
        return SelectionDecision.INCONCLUSIVE_SELECTION, None

    passing = tuple(trial for trial in trials if trial.passed)
    if not passing:
        return SelectionDecision.STOP_FAIL_SIGNAL_SELECTION, None

    champion = sorted(
        passing,
        key=lambda item: (
            -_lower_bound_sort_value(item.wilson_lower_bound),
            item.hypothesis_id,
        ),
    )[0]
    if champion.hypothesis_id == H1_ID:
        return SelectionDecision.SELECTION_CHAMPION_H1, H1_ID
    if champion.hypothesis_id == H2_ID:
        return SelectionDecision.SELECTION_CHAMPION_H2, H2_ID
    raise SignalSelectionValidationError("unexpected selection champion hypothesis")


def _validate_selection_rows(
    rows: tuple[SignalFeatureRow, ...],
) -> tuple[SignalFeatureRow, ...]:
    ordered = tuple(
        sorted(
            rows,
            key=lambda row: (
                row.decision_recv_wall_ns,
                row.decision_recv_mono_ns,
                row.row_id,
            ),
        )
    )
    if len(ordered) != EXPECTED_SELECTION_ROW_COUNT:
        raise SignalSelectionValidationError(
            f"selection requires exactly {EXPECTED_SELECTION_ROW_COUNT} rows"
        )
    if len({row.row_id for row in ordered}) != len(ordered):
        raise SignalSelectionValidationError("selection row_id must be unique")
    if len({row.opportunity.opportunity_id for row in ordered}) != len(ordered):
        raise SignalSelectionValidationError("selection opportunity_id must be unique")
    for row in ordered:
        if row.role is not InstrumentRole.PRIMARY:
            raise SignalSelectionValidationError("selection accepts PRIMARY rows only")
        if row.decision_recv_wall_ns < SELECTION_START_WALL_NS:
            raise SignalSelectionValidationError("development row passed to selection")
        if row.decision_recv_wall_ns >= CONFIRMATION_START_WALL_NS:
            raise SignalSelectionValidationError("confirmation row passed to selection evaluator")
        exit_wall = row.outcome.exit_recv_wall_ns
        if exit_wall is not None and exit_wall >= CONFIRMATION_START_WALL_NS:
            raise SignalSelectionValidationError("selection outcome crosses confirmation boundary")
    return ordered


def _mean_partial_known_cost_pnl(report: SimulationReport) -> Decimal | None:
    values = tuple(
        item.known_net_pnl
        for item in report.entries
        if item.status is TrialStatus.TRADED and item.known_net_pnl is not None
    )
    if not values:
        return None
    with localcontext() as ctx:
        ctx.prec = 60
        return sum(values, Decimal(0)) / Decimal(len(values))


def _ratio(numerator: int, denominator: int) -> Decimal | None:
    if denominator <= 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 60
        return Decimal(numerator) / Decimal(denominator)


def _lower_bound_sort_value(value: Decimal | None) -> Decimal:
    return Decimal("-1") if value is None else value


def _string_sequence_sha256(values: tuple[str, ...]) -> str:
    return hashlib.sha256(_canonical_json_bytes(list(values))).hexdigest()


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


def _decimal_or_none(value: Decimal | None) -> str | None:
    return None if value is None else serialize_exact_decimal(value)


def _validate_frozen_hash(actual: str, expected: str, label: str) -> None:
    _require_sha256(actual, f"{label}_sha256")
    if actual != expected:
        raise SignalSelectionValidationError(
            f"{label} SHA-256 does not match frozen registered value"
        )


def _require_sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise SignalSelectionValidationError(f"{field} must be 64 lowercase hex characters")
