from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum
from pathlib import Path
from typing import cast

from cryptobot.data.numeric import serialize_exact_decimal

SELECTION_RESULT_SHA256 = "e3403ef3eb6016040344dd8c17f4174b9190ca1a3aa5f5a59f54e1af7f7fb5a0"
REMEDIATION_SHA256 = "fec7cbb77fe67c672a2319fadee7e6a94f79fef013c16c6033b55fbb07f574d5"
ECONOMIC_50S_SHA256 = "ae62dff1172ca7666b1119c4c8a0f1ca61757f428c30b66b73a208b34c2a3b67"
LOGISTIC_50S_SHA256 = "285775b8febb226414bd838121f99b15b72d5b46edb13383b12398b8c80ccaf8"
DETERMINISTIC_300S_SHA256 = "b7555046b013a6564560095d36c4cd2a7638fc4b5b880e8359acd08919920201"
DECISION_300S_SHA256 = "b36027ab6436258b4970e974280ee3669813c585d7deb96a29f00079aca12eb6"
MICROSTRUCTURE_DECISION_SHA256 = "6355dd1295ab156757e091191ee686f6f9e63708a3bb556e03611b25285f7172"
SIGNAL_PROTOCOL_SHA256 = "2e2404b93e82ad8ac6ff27b10b5f4d22cd7ac624be69a277c6aed75a3b9c9843"

FEE_SCENARIO_BPS_PER_SIDE = Decimal("4.5")
DOCUMENTED_TIER6_DIAMOND_TAKER_BPS_PER_SIDE = Decimal("1.44")
FEE_DOC_URL = "https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees"
FEE_DOC_RETRIEVED_AT = "2026-09-27"
CAMPAIGN_DURATION_HOURS = 72
PRIMARY_HORIZON_SECONDS = 50


class BottleneckValidationError(ValueError):
    """Raised when frozen Stage-2 evidence violates TASK-026 expectations."""


class PrimaryPath(StrEnum):
    PROSPECTIVE_DEVELOPMENT_EVIDENCE_EXPANSION = "PROSPECTIVE_DEVELOPMENT_EVIDENCE_EXPANSION"


@dataclass(frozen=True, slots=True)
class FeeSensitivity:
    candidate_id: str
    scenario_bps_per_side: Decimal
    mean_gross_quote: Decimal
    mean_fee_quote: Decimal
    mean_known_net_quote: Decimal
    break_even_fee_bps_per_side: Decimal
    documented_tier6_diamond_taker_bps_per_side: Decimal
    mean_net_at_documented_tier6_diamond_quote: Decimal

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "scenario_bps_per_side": serialize_exact_decimal(self.scenario_bps_per_side),
            "mean_gross_quote": serialize_exact_decimal(self.mean_gross_quote),
            "mean_fee_quote": serialize_exact_decimal(self.mean_fee_quote),
            "mean_known_net_quote": serialize_exact_decimal(self.mean_known_net_quote),
            "break_even_fee_bps_per_side": serialize_exact_decimal(
                self.break_even_fee_bps_per_side
            ),
            "documented_tier6_diamond_taker_bps_per_side": serialize_exact_decimal(
                self.documented_tier6_diamond_taker_bps_per_side
            ),
            "mean_net_at_documented_tier6_diamond_quote": serialize_exact_decimal(
                self.mean_net_at_documented_tier6_diamond_quote
            ),
        }


@dataclass(frozen=True, slots=True)
class EvidenceExpansionPlan:
    fixed_duration_hours: int
    horizon_seconds: int
    source_row_count: int
    source_valid_target_count: int
    source_positive_target_count: int
    source_exposure_hours: Decimal
    nominal_decision_intervals: int
    projected_rows_at_observed_rate: Decimal
    projected_valid_targets_at_observed_rate: Decimal
    projected_positive_targets_at_observed_rate: Decimal

    def as_dict(self) -> dict[str, object]:
        return {
            "fixed_duration_hours": self.fixed_duration_hours,
            "horizon_seconds": self.horizon_seconds,
            "source_row_count": self.source_row_count,
            "source_valid_target_count": self.source_valid_target_count,
            "source_positive_target_count": self.source_positive_target_count,
            "source_exposure_hours": serialize_exact_decimal(self.source_exposure_hours),
            "nominal_decision_intervals": self.nominal_decision_intervals,
            "projected_rows_at_observed_rate": serialize_exact_decimal(
                self.projected_rows_at_observed_rate
            ),
            "projected_valid_targets_at_observed_rate": serialize_exact_decimal(
                self.projected_valid_targets_at_observed_rate
            ),
            "projected_positive_targets_at_observed_rate": serialize_exact_decimal(
                self.projected_positive_targets_at_observed_rate
            ),
            "projection_role": "PLANNING_ONLY_NOT_A_GATE_OR_EXPECTANCY_CLAIM",
            "stopping_rule": "FIXED_DURATION_NO_OUTCOME_DEPENDENT_EXTENSION",
            "evidence_role": "DEVELOPMENT_ONLY",
            "private_account_access_required": False,
            "aws_requester_pays_required": False,
        }


@dataclass(frozen=True, slots=True)
class EconomicBottleneckReport:
    source_sha256: dict[str, str]
    h1_gap_to_partial_known_cost_breakeven: Decimal
    h2_gap_to_partial_known_cost_breakeven: Decimal
    fee_sensitivity: FeeSensitivity
    best_300s_candidate_id: str
    best_300s_dev_b_valid_trade_count: int
    best_300s_dev_b_mean_partial_known_cost_pnl: Decimal
    microstructure_50s_positive_target_count: int
    microstructure_50s_nonpositive_target_count: int
    microstructure_300s_positive_target_count: int
    microstructure_300s_nonpositive_target_count: int
    evidence_expansion: EvidenceExpansionPlan
    selected_primary_path: PrimaryPath
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "report_version": "stage2-task026-economic-bottleneck-v1",
            "source_sha256": dict(sorted(self.source_sha256.items())),
            "completed_family_decisions": [
                "STOP_REGISTERED_H1_H2_FAMILY",
                "STOP_LOGISTIC_DEVELOPMENT",
                "STOP_300S_FAMILY",
                "STOP_MICROSTRUCTURE_FAMILY",
            ],
            "h1_gap_to_partial_known_cost_breakeven": serialize_exact_decimal(
                self.h1_gap_to_partial_known_cost_breakeven
            ),
            "h2_gap_to_partial_known_cost_breakeven": serialize_exact_decimal(
                self.h2_gap_to_partial_known_cost_breakeven
            ),
            "best_50s_fee_sensitivity": self.fee_sensitivity.as_dict(),
            "best_300s_candidate": {
                "candidate_id": self.best_300s_candidate_id,
                "dev_b_valid_trade_count": self.best_300s_dev_b_valid_trade_count,
                "dev_b_mean_partial_known_cost_pnl": serialize_exact_decimal(
                    self.best_300s_dev_b_mean_partial_known_cost_pnl
                ),
            },
            "microstructure_support": {
                "50s_positive_target_count": self.microstructure_50s_positive_target_count,
                "50s_nonpositive_target_count": self.microstructure_50s_nonpositive_target_count,
                "300s_positive_target_count": self.microstructure_300s_positive_target_count,
                "300s_nonpositive_target_count": self.microstructure_300s_nonpositive_target_count,
            },
            "selected_primary_path": self.selected_primary_path.value,
            "path_adjudication": {
                "development_evidence_expansion": "SELECTED",
                "actual_account_cost_resolution": "DEFERRED_NOT_PRIMARY",
                "maker_execution_research_gate": "DEFERRED_NOT_PRIMARY",
            },
            "evidence_expansion_plan": self.evidence_expansion.as_dict(),
            "fee_schedule_context": {
                "source_url": FEE_DOC_URL,
                "retrieved_at": FEE_DOC_RETRIEVED_AT,
                "documented_tier6_diamond_taker_bps_per_side": (
                    serialize_exact_decimal(DOCUMENTED_TIER6_DIAMOND_TAKER_BPS_PER_SIDE)
                ),
                "evidence_class": "DOCUMENTED",
                "actual_project_account_fee_tier": "UNKNOWN",
            },
            "unknown_costs_preserved": [
                "actual_project_account_fee_tier",
                "latency",
                "realized_own_order_slippage_impact",
                "funding_boundaries",
                "maker_economics",
            ],
            "old_confirmation_status": "UNOPENED_AND_EXCLUDED",
            "new_model_or_test_evidence_consumed": False,
            "fresh_registered_test_started": False,
            "user_action_required_now": False,
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


def break_even_fee_bps_per_side(
    *,
    mean_gross_quote: Decimal,
    mean_fee_quote: Decimal,
    scenario_bps_per_side: Decimal = FEE_SCENARIO_BPS_PER_SIDE,
) -> Decimal:
    if mean_gross_quote <= 0:
        return Decimal(0)
    if mean_fee_quote <= 0 or scenario_bps_per_side <= 0:
        raise BottleneckValidationError("fee sensitivity inputs must be positive")
    with localcontext() as context:
        context.prec = 80
        return scenario_bps_per_side * mean_gross_quote / mean_fee_quote


def _load_json(
    path: Path,
    *,
    expected_sha256: str,
) -> dict[str, object]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BottleneckValidationError(f"cannot read frozen artifact: {path}") from exc
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise BottleneckValidationError(f"frozen artifact SHA-256 mismatch: {path}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BottleneckValidationError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise BottleneckValidationError(f"artifact must be a JSON object: {path}")
    return cast(dict[str, object], payload)


def _object_list(payload: dict[str, object], field: str) -> list[dict[str, object]]:
    value = payload.get(field)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise BottleneckValidationError(f"{field} must be a list of objects")
    return [cast(dict[str, object], item) for item in value]


def _dict_field(payload: dict[str, object], field: str) -> dict[str, object]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise BottleneckValidationError(f"{field} must be an object")
    return cast(dict[str, object], value)


def _str_field(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise BottleneckValidationError(f"{field} must be a string")
    return value


def _int_field(payload: dict[str, object], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise BottleneckValidationError(f"{field} must be an integer")
    return value


def _decimal_field(payload: dict[str, object], field: str) -> Decimal:
    value = payload.get(field)
    if not isinstance(value, str):
        raise BottleneckValidationError(f"{field} must be an exact decimal string")
    try:
        return Decimal(value)
    except Exception as exc:
        raise BottleneckValidationError(f"{field} is not a valid decimal") from exc


def _require_decision(
    payload: dict[str, object],
    expected: str,
    *,
    label: str,
) -> None:
    if _str_field(payload, "decision") != expected:
        raise BottleneckValidationError(f"{label} decision is not {expected}")


def _best_50s_dev_b_candidate(
    economic_50s: dict[str, object],
) -> dict[str, object]:
    results = _object_list(economic_50s, "dev_b_results")
    candidates = [item for item in results if _str_field(item, "candidate_id") != "E0_H2_BASELINE"]
    if not candidates:
        raise BottleneckValidationError("50s development has no new candidates")
    return max(candidates, key=lambda item: _decimal_field(item, "mean_known_net_quote"))


def _best_300s_dev_b_candidate(
    deterministic_300s: dict[str, object],
) -> tuple[str, dict[str, object]]:
    rows = _object_list(deterministic_300s, "results")
    new_candidates = [
        item
        for item in rows
        if _str_field(_dict_field(item, "candidate"), "id") != "BENCHMARK_H2_UNFILTERED_300S"
    ]
    if not new_candidates:
        raise BottleneckValidationError("300s development has no new candidates")

    def metric(item: dict[str, object]) -> Decimal:
        partitions = _dict_field(item, "partitions")
        dev_b = _dict_field(partitions, "DEV_B")
        return _decimal_field(dev_b, "mean_partial_known_cost_pnl")

    best = max(new_candidates, key=metric)
    candidate_id = _str_field(_dict_field(best, "candidate"), "id")
    return candidate_id, _dict_field(_dict_field(best, "partitions"), "DEV_B")


def build_task026_report(repo_root: str | Path = ".") -> EconomicBottleneckReport:
    root = Path(repo_root)
    selection = _load_json(
        root / "artifacts/stage_2/selection_result.json",
        expected_sha256=SELECTION_RESULT_SHA256,
    )
    remediation = _load_json(
        root / "artifacts/stage_2/selection_remediation.json",
        expected_sha256=REMEDIATION_SHA256,
    )
    economic_50s = _load_json(
        root / "artifacts/stage_2/economic_family_development.json",
        expected_sha256=ECONOMIC_50S_SHA256,
    )
    logistic_50s = _load_json(
        root / "artifacts/stage_2/economic_logistic_development.json",
        expected_sha256=LOGISTIC_50S_SHA256,
    )
    deterministic_300s = _load_json(
        root / "artifacts/stage_2/economic_300s_deterministic_results.json",
        expected_sha256=DETERMINISTIC_300S_SHA256,
    )
    decision_300s = _load_json(
        root / "artifacts/stage_2/economic_300s_decision.json",
        expected_sha256=DECISION_300S_SHA256,
    )
    microstructure = _load_json(
        root / "artifacts/stage_2/microstructure_decision.json",
        expected_sha256=MICROSTRUCTURE_DECISION_SHA256,
    )
    signal_protocol = _load_json(
        root / "artifacts/stage_2/signal_protocol.json",
        expected_sha256=SIGNAL_PROTOCOL_SHA256,
    )

    _require_decision(selection, "INCONCLUSIVE_SELECTION", label="TASK-021")
    _require_decision(remediation, "STOP_REGISTERED_H1_H2_FAMILY", label="TASK-022")
    _require_decision(logistic_50s, "STOP_LOGISTIC_DEVELOPMENT", label="TASK-023")
    _require_decision(decision_300s, "STOP_300S_FAMILY", label="TASK-024")
    _require_decision(microstructure, "STOP_MICROSTRUCTURE_FAMILY", label="TASK-025")

    best_50s = _best_50s_dev_b_candidate(economic_50s)
    mean_gross = _decimal_field(best_50s, "mean_gross_quote")
    mean_fee = _decimal_field(best_50s, "mean_fee_quote")
    mean_net = _decimal_field(best_50s, "mean_known_net_quote")
    break_even = break_even_fee_bps_per_side(
        mean_gross_quote=mean_gross,
        mean_fee_quote=mean_fee,
    )
    with localcontext() as context:
        context.prec = 80
        mean_net_at_documented_rate = mean_gross - mean_fee * (
            DOCUMENTED_TIER6_DIAMOND_TAKER_BPS_PER_SIDE / FEE_SCENARIO_BPS_PER_SIDE
        )

    best_300s_id, best_300s_dev_b = _best_300s_dev_b_candidate(deterministic_300s)
    support_50s = _dict_field(microstructure, "horizon_50s")
    support_300s = _dict_field(microstructure, "horizon_300s")
    row_count = _int_field(support_50s, "row_count")
    valid_count = _int_field(support_50s, "valid_target_count")
    positive_count = _int_field(support_50s, "positive_target_count")
    primary_dataset = _dict_field(signal_protocol, "primary_dataset")
    partitions = _dict_field(signal_protocol, "partitions")
    first_wall_ns = _int_field(primary_dataset, "first_decision_recv_wall_ns")
    confirmation_start_wall_ns = _int_field(partitions, "confirmation_start_wall_ns")
    if confirmation_start_wall_ns <= first_wall_ns:
        raise BottleneckValidationError("Stage-2 source exposure interval is nonpositive")
    nominal_intervals = CAMPAIGN_DURATION_HOURS * 3600 // PRIMARY_HORIZON_SECONDS
    with localcontext() as context:
        context.prec = 80
        source_exposure_hours = Decimal(confirmation_start_wall_ns - first_wall_ns) / Decimal(
            3_600_000_000_000
        )
        duration_ratio = Decimal(CAMPAIGN_DURATION_HOURS) / source_exposure_hours
        projected_rows = Decimal(row_count) * duration_ratio
        projected_valid = Decimal(valid_count) * duration_ratio
        projected_positive = Decimal(positive_count) * duration_ratio

    expansion = EvidenceExpansionPlan(
        fixed_duration_hours=CAMPAIGN_DURATION_HOURS,
        horizon_seconds=PRIMARY_HORIZON_SECONDS,
        source_row_count=row_count,
        source_valid_target_count=valid_count,
        source_positive_target_count=positive_count,
        source_exposure_hours=source_exposure_hours,
        nominal_decision_intervals=nominal_intervals,
        projected_rows_at_observed_rate=projected_rows,
        projected_valid_targets_at_observed_rate=projected_valid,
        projected_positive_targets_at_observed_rate=projected_positive,
    )

    if mean_net_at_documented_rate >= 0:
        raise BottleneckValidationError(
            "documented tier6+Diamond fee context unexpectedly rescues best 50s candidate"
        )
    if positive_count >= 30:
        raise BottleneckValidationError(
            "TASK-025 50s positive class no longer matches the frozen support bottleneck"
        )

    return EconomicBottleneckReport(
        source_sha256={
            "selection_result": SELECTION_RESULT_SHA256,
            "selection_remediation": REMEDIATION_SHA256,
            "economic_family_50s": ECONOMIC_50S_SHA256,
            "economic_logistic_50s": LOGISTIC_50S_SHA256,
            "economic_deterministic_300s": DETERMINISTIC_300S_SHA256,
            "economic_decision_300s": DECISION_300S_SHA256,
            "microstructure_decision": MICROSTRUCTURE_DECISION_SHA256,
            "signal_protocol": SIGNAL_PROTOCOL_SHA256,
        },
        h1_gap_to_partial_known_cost_breakeven=_decimal_field(
            remediation, "h1_gap_to_partial_known_cost_breakeven"
        ),
        h2_gap_to_partial_known_cost_breakeven=_decimal_field(
            remediation, "h2_gap_to_partial_known_cost_breakeven"
        ),
        fee_sensitivity=FeeSensitivity(
            candidate_id=_str_field(best_50s, "candidate_id"),
            scenario_bps_per_side=FEE_SCENARIO_BPS_PER_SIDE,
            mean_gross_quote=mean_gross,
            mean_fee_quote=mean_fee,
            mean_known_net_quote=mean_net,
            break_even_fee_bps_per_side=break_even,
            documented_tier6_diamond_taker_bps_per_side=(
                DOCUMENTED_TIER6_DIAMOND_TAKER_BPS_PER_SIDE
            ),
            mean_net_at_documented_tier6_diamond_quote=mean_net_at_documented_rate,
        ),
        best_300s_candidate_id=best_300s_id,
        best_300s_dev_b_valid_trade_count=_int_field(best_300s_dev_b, "valid_trade_count"),
        best_300s_dev_b_mean_partial_known_cost_pnl=_decimal_field(
            best_300s_dev_b, "mean_partial_known_cost_pnl"
        ),
        microstructure_50s_positive_target_count=positive_count,
        microstructure_50s_nonpositive_target_count=_int_field(
            support_50s, "nonpositive_target_count"
        ),
        microstructure_300s_positive_target_count=_int_field(support_300s, "positive_target_count"),
        microstructure_300s_nonpositive_target_count=_int_field(
            support_300s, "nonpositive_target_count"
        ),
        evidence_expansion=expansion,
        selected_primary_path=(PrimaryPath.PROSPECTIVE_DEVELOPMENT_EVIDENCE_EXPANSION),
        reasons=(
            "REPEATED_TAKER_FAMILIES_FAILED_PARTIAL_KNOWN_COST_ECONOMICS",
            "BEST_50S_GROSS_EDGE_REQUIRES_SUB_1_BPS_PER_SIDE_BREAK_EVEN_FEE",
            "DOCUMENTED_TIER6_DIAMOND_TAKER_CONTEXT_STILL_NEGATIVE_FOR_BEST_50S",
            "TASK025_50S_POSITIVE_CLASS_SUPPORT_BELOW_FROZEN_30_MINIMUM",
            "TASK025_300S_FEATURE_AND_CLASS_SUPPORT_INSUFFICIENT",
            "PUBLIC_ONLY_FIXED_DURATION_DEVELOPMENT_CAN_PROCEED_WITHOUT_PRIVATE_ACCESS",
            "MAKER_RESEARCH_WOULD_ADD_UNMEASURED_FILL_QUEUE_AND_ADVERSE_SELECTION_RISK",
        ),
    )


def write_economic_bottleneck_report(
    report: EconomicBottleneckReport,
    path: str | Path,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_json_bytes()
    try:
        with target.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if target.read_bytes() != payload:
            raise BottleneckValidationError("existing TASK-026 bottleneck report differs") from None
    return target
