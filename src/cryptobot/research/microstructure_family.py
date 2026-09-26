from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from statistics import median
from typing import cast

from cryptobot.data.numeric import serialize_exact_decimal
from cryptobot.research.economic_family import (
    EconomicDevelopmentRow,
    EconomicFamilyValidationError,
    executable_known_net,
)

REGISTRY_SHA256 = "d5024ce6cb16c0d3dcce5b65f3f62f6d577b971d3bda7c8342ab67aaa100b130"
TRAINING_CACHE_50S_SHA256 = "2c084630a2778fa575fabc3d7c7df4c94b6d64f48ede342a9a14e735d21a9afb"
TRAINING_CACHE_300S_SHA256 = "932aafae64ac26678c152e8d556e50f7bad0fa6cbaa26eda4fc08b7b88add130"
MIN_COMPLETE_50S = 300
MIN_COMPLETE_300S = 80
L2_LAMBDA = Decimal("1")
MAX_ITERATIONS = 80
CONVERGENCE_TOLERANCE = Decimal("1e-24")
_ZERO = Decimal(0)
_ONE = Decimal(1)
_EXP_CLIP = Decimal(40)

FEATURE_NAMES = (
    "abs_hl_bbo_imbalance",
    "h2_aligned_hl_depth_imbalance_top5",
    "h2_aligned_hl_aggressive_trade_flow_5s",
    "h2_aligned_binance_aggressive_trade_flow_5s",
    "h2_aligned_hl_mid_return_5s_bps",
    "h2_aligned_binance_mid_return_5s_bps",
    "h2_aligned_cross_venue_return_gap_5s_bps",
    "hl_spread_bps",
)


@dataclass(frozen=True, slots=True)
class MicrostructureRow:
    base: EconomicDevelopmentRow
    hl_depth_imbalance_top5: Decimal | None
    hl_aggressive_trade_flow_5s: Decimal | None
    binance_aggressive_trade_flow_5s: Decimal | None
    hl_mid_return_5s_bps: Decimal | None
    cross_venue_return_gap_5s_bps: Decimal | None

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> MicrostructureRow:
        return cls(
            base=EconomicDevelopmentRow.from_dict(payload),
            hl_depth_imbalance_top5=_decimal(payload.get("hl_depth_imbalance_top5")),
            hl_aggressive_trade_flow_5s=_decimal(payload.get("hl_aggressive_trade_flow_5s")),
            binance_aggressive_trade_flow_5s=_decimal(
                payload.get("binance_aggressive_trade_flow_5s")
            ),
            hl_mid_return_5s_bps=_decimal(payload.get("hl_mid_return_5s_bps")),
            cross_venue_return_gap_5s_bps=_decimal(payload.get("cross_venue_return_gap_5s_bps")),
        )


@dataclass(frozen=True, slots=True)
class Standardization:
    means: tuple[Decimal, ...]
    scales: tuple[Decimal, ...]

    def transform(self, values: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
        return tuple(
            (value - mean) / scale
            for value, mean, scale in zip(
                values,
                self.means,
                self.scales,
                strict=True,
            )
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "means": [serialize_exact_decimal(value) for value in self.means],
            "scales": [serialize_exact_decimal(value) for value in self.scales],
        }


@dataclass(frozen=True, slots=True)
class FrozenMicrostructureModel:
    horizon_seconds: int
    training_source_sha256: str
    feature_complete_count: int
    training_sample_count: int
    standardization: Standardization
    coefficients: tuple[Decimal, ...]
    iterations: int
    economic_probability_hurdle: Decimal
    mean_positive_known_net_quote: Decimal
    mean_nonpositive_known_net_quote: Decimal

    def probability(self, row: MicrostructureRow) -> Decimal | None:
        raw = feature_vector(row)
        if raw is None:
            return None
        x = (_ONE, *self.standardization.transform(raw))
        score = sum(
            (coefficient * value for coefficient, value in zip(self.coefficients, x, strict=True)),
            _ZERO,
        )
        return _sigmoid(score)

    def action(self, row: MicrostructureRow) -> int:
        direction = h2_direction(row)
        probability = self.probability(row)
        if direction == 0 or probability is None:
            return 0
        return direction if probability >= self.economic_probability_hurdle else 0

    def as_dict(self) -> dict[str, object]:
        return {
            "model_id": "S2-T025-H2-MICROSTRUCTURE-L2-LOGISTIC-V1",
            "horizon_seconds": self.horizon_seconds,
            "registry_sha256": REGISTRY_SHA256,
            "training_source_sha256": self.training_source_sha256,
            "feature_names": list(FEATURE_NAMES),
            "feature_complete_count": self.feature_complete_count,
            "training_sample_count": self.training_sample_count,
            "l2_lambda": serialize_exact_decimal(L2_LAMBDA),
            "solver": "DETERMINISTIC_DECIMAL_NEWTON_V1",
            "max_iterations": MAX_ITERATIONS,
            "convergence_tolerance": serialize_exact_decimal(CONVERGENCE_TOLERANCE),
            "standardization": self.standardization.as_dict(),
            "coefficients": [serialize_exact_decimal(value) for value in self.coefficients],
            "iterations": self.iterations,
            "target": ("H2_DIRECTIONAL_TRADE_PARTIAL_KNOWN_COST_PNL_GT_ZERO"),
            "probability_gate_rule": (
                "EXPOSED_TRAINING_EXPECTED_VALUE_BREAKEVEN_FROM_MEAN_POSITIVE_"
                "AND_NONPOSITIVE_KNOWN_NET_NO_SWEEP"
            ),
            "economic_probability_hurdle": serialize_exact_decimal(
                self.economic_probability_hurdle
            ),
            "mean_positive_known_net_quote": serialize_exact_decimal(
                self.mean_positive_known_net_quote
            ),
            "mean_nonpositive_known_net_quote": serialize_exact_decimal(
                self.mean_nonpositive_known_net_quote
            ),
        }


@dataclass(frozen=True, slots=True)
class TrainingEvaluation:
    eligible_rows: int
    selected_trades: int
    positive_selected_trades: int
    mean_known_net_quote: Decimal | None
    median_known_net_bps: Decimal | None
    aggregate_known_net_quote: Decimal

    @property
    def selected_fraction(self) -> Decimal:
        if self.eligible_rows <= 0:
            return _ZERO
        return Decimal(self.selected_trades) / Decimal(self.eligible_rows)

    def as_dict(self) -> dict[str, object]:
        return {
            "eligible_rows": self.eligible_rows,
            "selected_trades": self.selected_trades,
            "positive_selected_trades": self.positive_selected_trades,
            "selected_fraction": serialize_exact_decimal(self.selected_fraction),
            "mean_known_net_quote": _optional(self.mean_known_net_quote),
            "median_known_net_bps": _optional(self.median_known_net_bps),
            "aggregate_known_net_quote": serialize_exact_decimal(self.aggregate_known_net_quote),
        }


@dataclass(frozen=True, slots=True)
class TrainingReport:
    registry_sha256: str
    exposed_dev_b_contaminated: bool
    contamination_reason: str
    horizon_50s_complete: int
    horizon_300s_complete: int
    horizon_300s_eligible: bool
    model_50s: FrozenMicrostructureModel
    training_evaluation_50s: TrainingEvaluation
    fresh_validation_allowed: bool
    fresh_validation_reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "report_version": "stage2-task025-microstructure-training-v1",
            "registry_sha256": self.registry_sha256,
            "exposed_dev_b_contaminated": self.exposed_dev_b_contaminated,
            "contamination_reason": self.contamination_reason,
            "horizon_50s_complete": self.horizon_50s_complete,
            "horizon_50s_min_complete": MIN_COMPLETE_50S,
            "horizon_300s_complete": self.horizon_300s_complete,
            "horizon_300s_min_complete": MIN_COMPLETE_300S,
            "horizon_300s_eligible": self.horizon_300s_eligible,
            "model_50s": self.model_50s.as_dict(),
            "training_evaluation_50s": self.training_evaluation_50s.as_dict(),
            "fresh_validation_allowed": self.fresh_validation_allowed,
            "fresh_validation_reason": self.fresh_validation_reason,
            "old_confirmation_used": False,
            "fresh_registered_test_started": False,
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


def load_cache(
    path: str | Path,
    *,
    expected_sha256: str,
) -> tuple[MicrostructureRow, ...]:
    raw = Path(path).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise EconomicFamilyValidationError("microstructure cache SHA-256 mismatch")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise EconomicFamilyValidationError("microstructure cache must be object")
    if payload.get("registry_sha256") != REGISTRY_SHA256:
        raise EconomicFamilyValidationError("microstructure registry SHA mismatch")
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list):
        raise EconomicFamilyValidationError("microstructure rows must be list")
    rows: list[MicrostructureRow] = []
    for item in raw_rows:
        if not isinstance(item, dict):
            raise EconomicFamilyValidationError("microstructure row must be object")
        rows.append(MicrostructureRow.from_dict(cast(dict[str, object], item)))
    return tuple(
        sorted(
            rows,
            key=lambda item: (
                item.base.decision_recv_wall_ns,
                item.base.row_id,
            ),
        )
    )


def feature_vector(row: MicrostructureRow) -> tuple[Decimal, ...] | None:
    direction = h2_direction(row)
    base = row.base
    if (
        direction == 0
        or base.hl_bbo_imbalance is None
        or base.hl_spread_bps is None
        or base.binance_mid_return_5s_bps is None
        or row.hl_depth_imbalance_top5 is None
        or row.hl_aggressive_trade_flow_5s is None
        or row.binance_aggressive_trade_flow_5s is None
        or row.hl_mid_return_5s_bps is None
        or row.cross_venue_return_gap_5s_bps is None
    ):
        return None
    d = Decimal(direction)
    return (
        abs(base.hl_bbo_imbalance),
        d * row.hl_depth_imbalance_top5,
        d * row.hl_aggressive_trade_flow_5s,
        d * row.binance_aggressive_trade_flow_5s,
        d * row.hl_mid_return_5s_bps,
        d * base.binance_mid_return_5s_bps,
        d * row.cross_venue_return_gap_5s_bps,
        base.hl_spread_bps,
    )


def h2_direction(row: MicrostructureRow) -> int:
    value = row.base.hl_bbo_imbalance
    if value is None or value == 0:
        return 0
    return 1 if value > 0 else -1


def fit_frozen_model_50s(
    rows: tuple[MicrostructureRow, ...],
) -> FrozenMicrostructureModel:
    complete = sum(feature_vector(row) is not None for row in rows)
    if complete < MIN_COMPLETE_50S:
        raise EconomicFamilyValidationError(
            "50s microstructure training support below frozen minimum"
        )

    samples: list[tuple[tuple[Decimal, ...], int, Decimal]] = []
    for row in rows:
        values = feature_vector(row)
        direction = h2_direction(row)
        economics = executable_known_net(row.base, action=direction)
        if values is None or direction == 0 or economics is None:
            continue
        known_net = economics[2]
        samples.append((values, int(known_net > 0), known_net))
    if len(samples) < MIN_COMPLETE_50S:
        raise EconomicFamilyValidationError("50s valid training support below frozen minimum")
    positives = tuple(net for _, target, net in samples if target == 1)
    nonpositives = tuple(net for _, target, net in samples if target == 0)
    if len(positives) < 30 or len(nonpositives) < 30:
        raise EconomicFamilyValidationError("50s training target classes are insufficient")

    raw_x = tuple(item[0] for item in samples)
    y = tuple(item[1] for item in samples)
    standardization = fit_standardization(raw_x)
    design = tuple((_ONE, *standardization.transform(row)) for row in raw_x)
    coefficients, iterations = fit_logistic(design, y)
    mean_positive = _mean(positives)
    mean_nonpositive = _mean(nonpositives)
    hurdle = expected_value_hurdle(
        mean_positive=mean_positive,
        mean_nonpositive=mean_nonpositive,
    )
    return FrozenMicrostructureModel(
        horizon_seconds=50,
        training_source_sha256=TRAINING_CACHE_50S_SHA256,
        feature_complete_count=complete,
        training_sample_count=len(samples),
        standardization=standardization,
        coefficients=coefficients,
        iterations=iterations,
        economic_probability_hurdle=hurdle,
        mean_positive_known_net_quote=mean_positive,
        mean_nonpositive_known_net_quote=mean_nonpositive,
    )


def evaluate_training(
    model: FrozenMicrostructureModel,
    rows: tuple[MicrostructureRow, ...],
) -> TrainingEvaluation:
    eligible = 0
    selected: list[tuple[Decimal, Decimal]] = []
    positive = 0
    for row in rows:
        values = feature_vector(row)
        if values is None:
            continue
        eligible += 1
        action = model.action(row)
        economics = executable_known_net(row.base, action=action)
        if economics is None:
            continue
        net = economics[2]
        selected.append((net, economics[3]))
        positive += int(net > 0)
    if not selected:
        return TrainingEvaluation(
            eligible_rows=eligible,
            selected_trades=0,
            positive_selected_trades=0,
            mean_known_net_quote=None,
            median_known_net_bps=None,
            aggregate_known_net_quote=_ZERO,
        )
    nets = tuple(item[0] for item in selected)
    bps = tuple(item[1] for item in selected)
    return TrainingEvaluation(
        eligible_rows=eligible,
        selected_trades=len(selected),
        positive_selected_trades=positive,
        mean_known_net_quote=_mean(nets),
        median_known_net_bps=median(bps),
        aggregate_known_net_quote=sum(nets, _ZERO),
    )


def build_training_report(
    rows_50s: tuple[MicrostructureRow, ...],
    rows_300s: tuple[MicrostructureRow, ...],
) -> TrainingReport:
    complete_50 = sum(feature_vector(row) is not None for row in rows_50s)
    complete_300 = sum(feature_vector(row) is not None for row in rows_300s)
    model = fit_frozen_model_50s(rows_50s)
    evaluation = evaluate_training(model, rows_50s)

    validation_allowed = evaluation.selected_trades > 0
    reason = (
        "FULL_8_FEATURE_50S_MODEL_SELECTS_NONZERO_EXPOSED_TRAINING_REGION"
        if validation_allowed
        else "FULL_8_FEATURE_50S_MODEL_SELECTS_ZERO_EXPOSED_TRAINING_TRADES"
    )
    return TrainingReport(
        registry_sha256=REGISTRY_SHA256,
        exposed_dev_b_contaminated=True,
        contamination_reason=(
            "A prior six-feature microstructure DEV_B report existed before the "
            "full eight-feature TASK-025 registry; all pre-cutoff rows are therefore "
            "treated as exposed training only."
        ),
        horizon_50s_complete=complete_50,
        horizon_300s_complete=complete_300,
        horizon_300s_eligible=complete_300 >= MIN_COMPLETE_300S,
        model_50s=model,
        training_evaluation_50s=evaluation,
        fresh_validation_allowed=validation_allowed,
        fresh_validation_reason=reason,
    )


def write_training_report(report: TrainingReport, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_json_bytes()
    try:
        with target.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if target.read_bytes() != payload:
            raise EconomicFamilyValidationError(
                "existing TASK-025 training report differs"
            ) from None
    return target


def fit_standardization(
    raw_x: tuple[tuple[Decimal, ...], ...],
) -> Standardization:
    columns = tuple(zip(*raw_x, strict=True))
    means = tuple(_mean(tuple(column)) for column in columns)
    scales: list[Decimal] = []
    for column, mean in zip(columns, means, strict=True):
        with localcontext() as ctx:
            ctx.prec = 60
            variance = sum(
                ((value - mean) * (value - mean) for value in column),
                _ZERO,
            ) / Decimal(len(column))
            scale = variance.sqrt()
        if scale <= 0:
            raise EconomicFamilyValidationError("microstructure feature scale must be positive")
        scales.append(scale)
    return Standardization(means=means, scales=tuple(scales))


def fit_logistic(
    design: tuple[tuple[Decimal, ...], ...],
    y: tuple[int, ...],
) -> tuple[tuple[Decimal, ...], int]:
    width = len(design[0])
    weights = [_ZERO for _ in range(width)]
    with localcontext() as ctx:
        ctx.prec = 60
        for iteration in range(1, MAX_ITERATIONS + 1):
            gradient = [_ZERO for _ in range(width)]
            information = [[_ZERO for _ in range(width)] for _ in range(width)]
            for features, target in zip(design, y, strict=True):
                score = sum(
                    (weight * value for weight, value in zip(weights, features, strict=True)),
                    _ZERO,
                )
                probability = _sigmoid(score)
                residual = Decimal(target) - probability
                variance = probability * (_ONE - probability)
                for j, value_j in enumerate(features):
                    gradient[j] += residual * value_j
                    for k, value_k in enumerate(features):
                        information[j][k] += variance * value_j * value_k
            for index in range(1, width):
                gradient[index] -= L2_LAMBDA * weights[index]
                information[index][index] += L2_LAMBDA

            delta = solve_linear_system(information, gradient)
            weights = [weight + step for weight, step in zip(weights, delta, strict=True)]
            if max(abs(step) for step in delta) <= CONVERGENCE_TOLERANCE:
                return tuple(weights), iteration
    raise EconomicFamilyValidationError("microstructure logistic did not converge")


def expected_value_hurdle(
    *,
    mean_positive: Decimal,
    mean_nonpositive: Decimal,
) -> Decimal:
    if mean_positive <= 0 or mean_nonpositive > 0:
        raise EconomicFamilyValidationError("invalid hurdle economics")
    denominator = mean_positive - mean_nonpositive
    with localcontext() as ctx:
        ctx.prec = 60
        hurdle = (-mean_nonpositive) / denominator
    if hurdle <= 0 or hurdle >= 1:
        raise EconomicFamilyValidationError("economic hurdle must lie in (0,1)")
    return hurdle


def solve_linear_system(
    matrix: list[list[Decimal]],
    vector: list[Decimal],
) -> list[Decimal]:
    n = len(vector)
    augmented = [[*matrix[row], vector[row]] for row in range(n)]
    for column in range(n):
        pivot = max(
            range(column, n),
            key=lambda row: abs(augmented[row][column]),
        )
        if augmented[pivot][column] == 0:
            raise EconomicFamilyValidationError("singular microstructure information matrix")
        augmented[column], augmented[pivot] = (
            augmented[pivot],
            augmented[column],
        )
        pivot_value = augmented[column][column]
        augmented[column] = [value / pivot_value for value in augmented[column]]
        for row in range(n):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0:
                continue
            augmented[row] = [
                left - factor * right
                for left, right in zip(
                    augmented[row],
                    augmented[column],
                    strict=True,
                )
            ]
    return [augmented[row][-1] for row in range(n)]


def _sigmoid(value: Decimal) -> Decimal:
    clipped = max(-_EXP_CLIP, min(_EXP_CLIP, value))
    with localcontext() as ctx:
        ctx.prec = 60
        return _ONE / (_ONE + (-clipped).exp())


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise EconomicFamilyValidationError("cannot average empty values")
    with localcontext() as ctx:
        ctx.prec = 60
        return sum(values, _ZERO) / Decimal(len(values))


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EconomicFamilyValidationError(
            "microstructure numeric field must be exact decimal string"
        )
    return Decimal(value)


def _optional(value: Decimal | None) -> str | None:
    return None if value is None else serialize_exact_decimal(value)
