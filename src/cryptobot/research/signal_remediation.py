from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, localcontext
from enum import StrEnum
from pathlib import Path
from typing import cast

from cryptobot.data.numeric import serialize_exact_decimal

SELECTION_RESULT_SHA256 = "e3403ef3eb6016040344dd8c17f4174b9190ca1a3aa5f5a59f54e1af7f7fb5a0"
H1_TRIAL_ID = "S2-SEL-H1-V1"
H2_TRIAL_ID = "S2-SEL-H2-V1"
SELECTION_EFFECTIVE_TARGET = 783
CONFIRMATION_EFFECTIVE_TARGET = 1225

# One-sided normal quantile for alpha = 0.025 / 4. The four attrition-stage
# lower bounds are Bonferroni-buffered to keep planning conservative.
_ATTRITION_Z = Decimal("2.4977054744123737")
_ZERO = Decimal(0)
_ONE = Decimal(1)


class RemediationValidationError(ValueError):
    """Raised when frozen TASK-021 evidence violates the remediation contract."""


class RemediationDecision(StrEnum):
    REGISTER_FRESH_H1_REPLICATION = "REGISTER_FRESH_H1_REPLICATION"
    STOP_REGISTERED_H1_H2_FAMILY = "STOP_REGISTERED_H1_H2_FAMILY"
    INCONCLUSIVE_REMEDIATION = "INCONCLUSIVE_REMEDIATION"


@dataclass(frozen=True, slots=True)
class AttritionStage:
    name: str
    numerator: int
    denominator: int
    observed_rate: Decimal
    planning_lower_bound: Decimal

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "observed_rate": serialize_exact_decimal(self.observed_rate),
            "planning_lower_bound": serialize_exact_decimal(self.planning_lower_bound),
        }


@dataclass(frozen=True, slots=True)
class CounterfactualH1Plan:
    registered: bool
    selection_effective_target: int
    confirmation_effective_target: int
    observed_design_effect: Decimal
    attrition_stages: tuple[AttritionStage, ...]
    conservative_directional_yield: Decimal
    selection_directional_rows_after_dependence: int
    confirmation_directional_rows_after_dependence: int
    selection_fresh_rows: int
    confirmation_fresh_rows: int
    total_fresh_rows: int
    caveat: str

    def as_dict(self) -> dict[str, object]:
        return {
            "registered": self.registered,
            "selection_effective_target": self.selection_effective_target,
            "confirmation_effective_target": self.confirmation_effective_target,
            "observed_design_effect": serialize_exact_decimal(self.observed_design_effect),
            "attrition_stages": [item.as_dict() for item in self.attrition_stages],
            "conservative_directional_yield": serialize_exact_decimal(
                self.conservative_directional_yield
            ),
            "selection_directional_rows_after_dependence": (
                self.selection_directional_rows_after_dependence
            ),
            "confirmation_directional_rows_after_dependence": (
                self.confirmation_directional_rows_after_dependence
            ),
            "selection_fresh_rows": self.selection_fresh_rows,
            "confirmation_fresh_rows": self.confirmation_fresh_rows,
            "total_fresh_rows": self.total_fresh_rows,
            "caveat": self.caveat,
        }


@dataclass(frozen=True, slots=True)
class RemediationReport:
    source_selection_sha256: str
    decision: RemediationDecision
    h1_mean_partial_known_cost_pnl: Decimal
    h2_mean_partial_known_cost_pnl: Decimal
    h1_gap_to_partial_known_cost_breakeven: Decimal
    h2_gap_to_partial_known_cost_breakeven: Decimal
    h1_counterfactual_plan: CounterfactualH1Plan
    historical_data_role: str
    fresh_data_rule: str
    old_confirmation_status: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "report_version": "stage2-selection-remediation-v1",
            "source_selection_sha256": self.source_selection_sha256,
            "decision": self.decision.value,
            "h1_mean_partial_known_cost_pnl": serialize_exact_decimal(
                self.h1_mean_partial_known_cost_pnl
            ),
            "h2_mean_partial_known_cost_pnl": serialize_exact_decimal(
                self.h2_mean_partial_known_cost_pnl
            ),
            "h1_gap_to_partial_known_cost_breakeven": serialize_exact_decimal(
                self.h1_gap_to_partial_known_cost_breakeven
            ),
            "h2_gap_to_partial_known_cost_breakeven": serialize_exact_decimal(
                self.h2_gap_to_partial_known_cost_breakeven
            ),
            "h1_counterfactual_plan": self.h1_counterfactual_plan.as_dict(),
            "historical_data_role": self.historical_data_role,
            "fresh_data_rule": self.fresh_data_rule,
            "old_confirmation_status": self.old_confirmation_status,
            "reasons": list(self.reasons),
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


def load_selection_result(path: str | Path) -> dict[str, object]:
    target = Path(path)
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise RemediationValidationError(
            f"cannot read TASK-021 selection result: {target}"
        ) from exc
    actual = hashlib.sha256(raw).hexdigest()
    if actual != SELECTION_RESULT_SHA256:
        raise RemediationValidationError(
            "TASK-021 selection result SHA-256 does not match frozen value"
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RemediationValidationError("TASK-021 selection result is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RemediationValidationError("TASK-021 selection result must be a JSON object")
    return cast(dict[str, object], payload)


def build_remediation_report(
    selection: dict[str, object],
) -> RemediationReport:
    _validate_selection_header(selection)
    trials = _trials_by_id(selection)
    h1 = trials[H1_TRIAL_ID]
    h2 = trials[H2_TRIAL_ID]

    h1_mean = _decimal_field(h1, "mean_partial_known_cost_pnl")
    h2_mean = _decimal_field(h2, "mean_partial_known_cost_pnl")
    h1_failures = _string_tuple_field(h1, "failure_reasons")
    h2_failures = _string_tuple_field(h2, "failure_reasons")

    plan = _counterfactual_h1_plan(h1)

    both_economic_failures = (
        "NONPOSITIVE_MEAN_PARTIAL_KNOWN_COST_PNL" in h1_failures
        and "NONPOSITIVE_MEAN_PARTIAL_KNOWN_COST_PNL" in h2_failures
        and h1_mean <= 0
        and h2_mean <= 0
    )
    reasons: tuple[str, ...]
    if both_economic_failures:
        decision = RemediationDecision.STOP_REGISTERED_H1_H2_FAMILY
        reasons = (
            "H1_FAILED_FROZEN_PARTIAL_KNOWN_COST_ECONOMIC_FILTER",
            "H2_FAILED_FROZEN_PARTIAL_KNOWN_COST_ECONOMIC_FILTER",
            "FRESH_H1_REPLICATION_NOT_JUSTIFIED_UNDER_REGISTERED_TAKER_ECONOMICS",
            "NEW_FAMILY_REQUIRES_NEW_PRE_REGISTRATION_AND_FRESH_TEST_EVIDENCE",
        )
    elif (
        "INSUFFICIENT_DIRECTIONAL_EVALUABLE_SUPPORT" in h1_failures
        and h1_mean > 0
        and "NONPOSITIVE_MEAN_PARTIAL_KNOWN_COST_PNL" in h2_failures
    ):
        decision = RemediationDecision.REGISTER_FRESH_H1_REPLICATION
        reasons = (
            "H1_ECONOMIC_FILTER_POSITIVE_BUT_REGISTERED_SUPPORT_INSUFFICIENT",
            "H2_FAILED_FROZEN_PARTIAL_KNOWN_COST_ECONOMIC_FILTER",
            "H1_REPLICATION_MUST_USE_FRESH_EVIDENCE",
        )
    else:
        decision = RemediationDecision.INCONCLUSIVE_REMEDIATION
        reasons = ("FROZEN_SELECTION_EVIDENCE_DOES_NOT_MATCH_A_REGISTERED_REMEDIATION_PATH",)

    registered_plan = CounterfactualH1Plan(
        registered=decision is RemediationDecision.REGISTER_FRESH_H1_REPLICATION,
        selection_effective_target=plan.selection_effective_target,
        confirmation_effective_target=plan.confirmation_effective_target,
        observed_design_effect=plan.observed_design_effect,
        attrition_stages=plan.attrition_stages,
        conservative_directional_yield=plan.conservative_directional_yield,
        selection_directional_rows_after_dependence=(
            plan.selection_directional_rows_after_dependence
        ),
        confirmation_directional_rows_after_dependence=(
            plan.confirmation_directional_rows_after_dependence
        ),
        selection_fresh_rows=plan.selection_fresh_rows,
        confirmation_fresh_rows=plan.confirmation_fresh_rows,
        total_fresh_rows=plan.total_fresh_rows,
        caveat=plan.caveat,
    )

    return RemediationReport(
        source_selection_sha256=SELECTION_RESULT_SHA256,
        decision=decision,
        h1_mean_partial_known_cost_pnl=h1_mean,
        h2_mean_partial_known_cost_pnl=h2_mean,
        h1_gap_to_partial_known_cost_breakeven=(h1_mean.copy_negate() if h1_mean < 0 else _ZERO),
        h2_gap_to_partial_known_cost_breakeven=(h2_mean.copy_negate() if h2_mean < 0 else _ZERO),
        h1_counterfactual_plan=registered_plan,
        historical_data_role=("DIAGNOSTIC_AND_NEW_FAMILY_DEVELOPMENT_ONLY_NOT_CONFIRMATORY"),
        fresh_data_rule=(
            "ANY_NEW_REGISTERED_FAMILY_MUST_FREEZE_ITS_PROTOCOL_BEFORE_FRESH_"
            "CHRONOLOGICALLY_SEPARATE_SELECTION_AND_CONFIRMATION_EVIDENCE"
        ),
        old_confirmation_status="UNOPENED_AND_EXCLUDED",
        reasons=reasons,
    )


def write_remediation_report(
    report: RemediationReport,
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
            raise RemediationValidationError(
                "existing remediation report differs from deterministic output"
            ) from None
    return target


def wilson_lower_bound(
    *,
    numerator: int,
    denominator: int,
    z: Decimal = _ATTRITION_Z,
) -> Decimal:
    if numerator < 0 or denominator <= 0 or numerator > denominator:
        raise RemediationValidationError("invalid Wilson count inputs")
    if z <= 0:
        raise RemediationValidationError("Wilson z must be positive")
    with localcontext() as ctx:
        ctx.prec = 60
        n = Decimal(denominator)
        p_hat = Decimal(numerator) / n
        z2 = z * z
        denominator_term = _ONE + z2 / n
        center = p_hat + z2 / (Decimal(2) * n)
        variance = p_hat * (_ONE - p_hat) / n + z2 / (Decimal(4) * n * n)
        return max(_ZERO, (center - z * variance.sqrt()) / denominator_term)


def _counterfactual_h1_plan(
    h1: dict[str, object],
) -> CounterfactualH1Plan:
    total = _int_field(h1, "selection_row_count")
    feature_ready = _int_field(h1, "feature_ready_count")
    abstain = _int_field(h1, "abstain_count")
    traded = _int_field(h1, "simulation_traded_count")
    directional = _int_field(h1, "directional_evaluable_count")
    design_effect = _decimal_field(h1, "design_effect")

    actionable = total - abstain
    if not (
        0 < feature_ready <= total
        and 0 < actionable <= feature_ready
        and 0 < traded <= actionable
        and 0 < directional <= traded
        and design_effect >= 1
    ):
        raise RemediationValidationError("invalid H1 attrition counts")

    stage_counts = (
        ("FEATURE_READY", feature_ready, total),
        ("NONZERO_ACTION_GIVEN_FEATURE_READY", actionable, feature_ready),
        ("VALID_EXECUTABLE_GIVEN_ACTION", traded, actionable),
        ("NONZERO_OUTCOME_GIVEN_TRADED", directional, traded),
    )
    stages = tuple(
        AttritionStage(
            name=name,
            numerator=numerator,
            denominator=denominator,
            observed_rate=_ratio(numerator, denominator),
            planning_lower_bound=wilson_lower_bound(
                numerator=numerator,
                denominator=denominator,
            ),
        )
        for name, numerator, denominator in stage_counts
    )
    with localcontext() as ctx:
        ctx.prec = 60
        conservative_yield = _ONE
        for stage in stages:
            conservative_yield *= stage.planning_lower_bound

        selection_directional = _ceil_decimal(Decimal(SELECTION_EFFECTIVE_TARGET) * design_effect)
        confirmation_directional = _ceil_decimal(
            Decimal(CONFIRMATION_EFFECTIVE_TARGET) * design_effect
        )
        selection_rows = _ceil_decimal(Decimal(selection_directional) / conservative_yield)
        confirmation_rows = _ceil_decimal(Decimal(confirmation_directional) / conservative_yield)

    return CounterfactualH1Plan(
        registered=False,
        selection_effective_target=SELECTION_EFFECTIVE_TARGET,
        confirmation_effective_target=CONFIRMATION_EFFECTIVE_TARGET,
        observed_design_effect=design_effect,
        attrition_stages=stages,
        conservative_directional_yield=conservative_yield,
        selection_directional_rows_after_dependence=selection_directional,
        confirmation_directional_rows_after_dependence=confirmation_directional,
        selection_fresh_rows=selection_rows,
        confirmation_fresh_rows=confirmation_rows,
        total_fresh_rows=selection_rows + confirmation_rows,
        caveat=(
            "COUNTERFACTUAL_ONLY: uses TASK-021 attrition and observed H1 design "
            "effect as planning inputs; future dependence can differ. The plan is "
            "not registered when frozen taker partial-known-cost economics are "
            "nonpositive."
        ),
    )


def _validate_selection_header(selection: dict[str, object]) -> None:
    if selection.get("decision") != "INCONCLUSIVE_SELECTION":
        raise RemediationValidationError(
            "TASK-022 expects the frozen INCONCLUSIVE_SELECTION result"
        )
    if selection.get("champion_hypothesis_id") is not None:
        raise RemediationValidationError("TASK-022 expects no selection champion")
    if selection.get("confirmation_opened") is not False:
        raise RemediationValidationError("old confirmation must remain unopened")


def _trials_by_id(
    selection: dict[str, object],
) -> dict[str, dict[str, object]]:
    raw = selection.get("trials")
    if not isinstance(raw, list):
        raise RemediationValidationError("selection trials must be a list")
    output: dict[str, dict[str, object]] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise RemediationValidationError("selection trial must be an object")
        normalized = cast(dict[str, object], item)
        trial_id = normalized.get("trial_id")
        if not isinstance(trial_id, str) or not trial_id:
            raise RemediationValidationError("selection trial_id is missing")
        if trial_id in output:
            raise RemediationValidationError("selection trial_id must be unique")
        output[trial_id] = normalized
    if set(output) != {H1_TRIAL_ID, H2_TRIAL_ID}:
        raise RemediationValidationError(
            "TASK-022 accepts exactly the registered H1/H2 selection trials"
        )
    return output


def _int_field(payload: dict[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RemediationValidationError(f"{field} must be an integer")
    return value


def _decimal_field(payload: dict[str, object], field: str) -> Decimal:
    value = payload.get(field)
    if not isinstance(value, str):
        raise RemediationValidationError(f"{field} must be an exact decimal string")
    try:
        return Decimal(value)
    except Exception as exc:
        raise RemediationValidationError(f"{field} must be an exact decimal string") from exc


def _string_tuple_field(
    payload: dict[str, object],
    field: str,
) -> tuple[str, ...]:
    value = payload.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise RemediationValidationError(f"{field} must be a string list")
    return tuple(cast(list[str], value))


def _ratio(numerator: int, denominator: int) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 60
        return Decimal(numerator) / Decimal(denominator)


def _ceil_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))
