from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum
from pathlib import Path
from statistics import median

from cryptobot.data.numeric import serialize_exact_decimal
from cryptobot.research.economic_family import (
    BPS,
    EconomicDevelopmentRow,
    EconomicFamilyValidationError,
    chronological_development_split,
    executable_known_net,
)

FEATURE_NAMES = (
    "abs_hl_bbo_imbalance",
    "h2_aligned_binance_mid_return_5s_bps",
    "abs_binance_mid_return_5s_bps",
    "hl_spread_bps",
)
L2_LAMBDA = Decimal("1")
MAX_ITERATIONS = 80
CONVERGENCE_TOLERANCE = Decimal("1e-24")
MIN_DEV_B_SELECTED_TRADES = 50
_ZERO = Decimal(0)
_ONE = Decimal(1)
_EXP_CLIP = Decimal(40)


class LogisticDevelopmentDecision(StrEnum):
    FREEZE_LOGISTIC_FAMILY = "FREEZE_LOGISTIC_FAMILY"
    STOP_LOGISTIC_DEVELOPMENT = "STOP_LOGISTIC_DEVELOPMENT"


@dataclass(frozen=True, slots=True)
class Standardization:
    means: tuple[Decimal, ...]
    scales: tuple[Decimal, ...]

    def transform(self, values: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
        if len(values) != len(self.means):
            raise EconomicFamilyValidationError("feature vector length mismatch")
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
            "feature_names": list(FEATURE_NAMES),
            "means": [serialize_exact_decimal(value) for value in self.means],
            "scales": [serialize_exact_decimal(value) for value in self.scales],
        }


@dataclass(frozen=True, slots=True)
class LogisticModel:
    standardization: Standardization
    coefficients: tuple[Decimal, ...]
    iterations: int
    converged: bool

    def probability(self, raw_features: tuple[Decimal, ...]) -> Decimal:
        x = (_ONE, *self.standardization.transform(raw_features))
        z = sum(
            (weight * value for weight, value in zip(self.coefficients, x, strict=True)),
            _ZERO,
        )
        return _sigmoid(z)

    def as_dict(self) -> dict[str, object]:
        return {
            "model_type": "L2_LOGISTIC_REGRESSION",
            "l2_lambda": serialize_exact_decimal(L2_LAMBDA),
            "feature_names": list(FEATURE_NAMES),
            "standardization": self.standardization.as_dict(),
            "coefficients": [serialize_exact_decimal(value) for value in self.coefficients],
            "iterations": self.iterations,
            "converged": self.converged,
            "solver": "deterministic_decimal_newton_v1",
        }


@dataclass(frozen=True, slots=True)
class LogisticEvaluation:
    partition: str
    eligible_rows: int
    selected_trades: int
    positive_selected_trades: int
    selection_rate: Decimal
    positive_fraction: Decimal | None
    mean_known_net_quote: Decimal | None
    median_known_net_bps: Decimal | None
    aggregate_known_net_quote: Decimal | None

    def as_dict(self) -> dict[str, object]:
        return {
            "partition": self.partition,
            "eligible_rows": self.eligible_rows,
            "selected_trades": self.selected_trades,
            "positive_selected_trades": self.positive_selected_trades,
            "selection_rate": serialize_exact_decimal(self.selection_rate),
            "positive_fraction": _serialize_optional(self.positive_fraction),
            "mean_known_net_quote": _serialize_optional(self.mean_known_net_quote),
            "median_known_net_bps": _serialize_optional(self.median_known_net_bps),
            "aggregate_known_net_quote": _serialize_optional(self.aggregate_known_net_quote),
        }


@dataclass(frozen=True, slots=True)
class LogisticDevelopmentReport:
    source_sha256: str
    dev_a_row_count: int
    dev_b_row_count: int
    target: str
    threshold_rule: str
    economic_probability_hurdle: Decimal
    dev_a_positive_rate: Decimal
    dev_a_mean_positive_known_net_quote: Decimal
    dev_a_mean_nonpositive_known_net_quote: Decimal
    model: LogisticModel
    dev_a_evaluation: LogisticEvaluation
    dev_b_evaluation: LogisticEvaluation
    decision: LogisticDevelopmentDecision

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "report_version": "stage2-economic-logistic-development-v1",
            "source_sha256": self.source_sha256,
            "dev_a_row_count": self.dev_a_row_count,
            "dev_b_row_count": self.dev_b_row_count,
            "target": self.target,
            "features": list(FEATURE_NAMES),
            "threshold_rule": self.threshold_rule,
            "economic_probability_hurdle": serialize_exact_decimal(
                self.economic_probability_hurdle
            ),
            "dev_a_positive_rate": serialize_exact_decimal(self.dev_a_positive_rate),
            "dev_a_mean_positive_known_net_quote": serialize_exact_decimal(
                self.dev_a_mean_positive_known_net_quote
            ),
            "dev_a_mean_nonpositive_known_net_quote": serialize_exact_decimal(
                self.dev_a_mean_nonpositive_known_net_quote
            ),
            "model": self.model.as_dict(),
            "dev_a_evaluation": self.dev_a_evaluation.as_dict(),
            "dev_b_evaluation": self.dev_b_evaluation.as_dict(),
            "decision": self.decision.value,
            "decision_rule": (
                "FREEZE only if DEV_B has at least 50 selected valid trades, positive "
                "mean known-net quote PnL, and positive median known-net bps. Otherwise "
                "STOP_LOGISTIC_DEVELOPMENT and do not collect fresh test evidence."
            ),
            "economic_scope": (
                "partial-known-cost only: executable bid/ask plus frozen 4.5 bps/side "
                "fee scenario; latency/impact/funding remain UNKNOWN"
            ),
            "old_confirmation_used": False,
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


def fit_and_evaluate_logistic_development(
    *,
    source_sha256: str,
    rows: tuple[EconomicDevelopmentRow, ...],
) -> LogisticDevelopmentReport:
    dev_a, dev_b = chronological_development_split(rows)
    x_a, y_a, net_a = _model_matrix(dev_a)
    if len(x_a) < 200:
        raise EconomicFamilyValidationError("DEV_A logistic sample is too small")

    model = fit_logistic_model(x_a, y_a)
    positives = tuple(net for net, target in zip(net_a, y_a, strict=True) if target == 1)
    nonpositives = tuple(net for net, target in zip(net_a, y_a, strict=True) if target == 0)
    if not positives or not nonpositives:
        raise EconomicFamilyValidationError(
            "DEV_A target must contain positive and nonpositive examples"
        )
    mean_positive = _mean(positives)
    mean_nonpositive = _mean(nonpositives)
    hurdle = economic_probability_hurdle(
        mean_positive=mean_positive,
        mean_nonpositive=mean_nonpositive,
    )

    dev_a_eval = evaluate_logistic_policy(
        partition="DEV_A",
        rows=dev_a,
        model=model,
        hurdle=hurdle,
    )
    dev_b_eval = evaluate_logistic_policy(
        partition="DEV_B",
        rows=dev_b,
        model=model,
        hurdle=hurdle,
    )
    passes = (
        dev_b_eval.selected_trades >= MIN_DEV_B_SELECTED_TRADES
        and dev_b_eval.mean_known_net_quote is not None
        and dev_b_eval.mean_known_net_quote > 0
        and dev_b_eval.median_known_net_bps is not None
        and dev_b_eval.median_known_net_bps > 0
    )
    return LogisticDevelopmentReport(
        source_sha256=source_sha256,
        dev_a_row_count=len(dev_a),
        dev_b_row_count=len(dev_b),
        target=(
            "H2_DIRECTIONAL_TRADE_HAS_POSITIVE_PARTIAL_KNOWN_COST_PNL_AFTER_"
            "EXECUTABLE_BID_ASK_AND_4_5_BPS_PER_SIDE_FEE"
        ),
        threshold_rule=(
            "DEV_A expected-value breakeven hurdle from mean positive and mean "
            "nonpositive known-net quote PnL; no threshold sweep"
        ),
        economic_probability_hurdle=hurdle,
        dev_a_positive_rate=_ratio(sum(y_a), len(y_a)),
        dev_a_mean_positive_known_net_quote=mean_positive,
        dev_a_mean_nonpositive_known_net_quote=mean_nonpositive,
        model=model,
        dev_a_evaluation=dev_a_eval,
        dev_b_evaluation=dev_b_eval,
        decision=(
            LogisticDevelopmentDecision.FREEZE_LOGISTIC_FAMILY
            if passes
            else LogisticDevelopmentDecision.STOP_LOGISTIC_DEVELOPMENT
        ),
    )


def fit_logistic_model(
    raw_x: tuple[tuple[Decimal, ...], ...],
    y: tuple[int, ...],
) -> LogisticModel:
    if not raw_x or len(raw_x) != len(y):
        raise EconomicFamilyValidationError("invalid logistic training matrix")
    width = len(FEATURE_NAMES)
    if any(len(row) != width for row in raw_x):
        raise EconomicFamilyValidationError("unexpected logistic feature width")
    if any(target not in (0, 1) for target in y):
        raise EconomicFamilyValidationError("logistic target must be binary")

    standardization = _fit_standardization(raw_x)
    x = tuple((_ONE, *standardization.transform(row)) for row in raw_x)
    weights = [_ZERO for _ in range(width + 1)]
    converged = False
    completed = 0

    for iteration in range(1, MAX_ITERATIONS + 1):
        gradient = [_ZERO for _ in weights]
        information = [[_ZERO for _ in weights] for _ in weights]
        for features, target in zip(x, y, strict=True):
            z = sum(
                (weight * value for weight, value in zip(weights, features, strict=True)),
                _ZERO,
            )
            probability = _sigmoid(z)
            residual = Decimal(target) - probability
            variance = probability * (_ONE - probability)
            for j, value_j in enumerate(features):
                gradient[j] += residual * value_j
                for k, value_k in enumerate(features):
                    information[j][k] += variance * value_j * value_k

        for index in range(1, len(weights)):
            gradient[index] -= L2_LAMBDA * weights[index]
            information[index][index] += L2_LAMBDA

        delta = _solve_linear_system(information, gradient)
        weights = [weight + step for weight, step in zip(weights, delta, strict=True)]
        completed = iteration
        if max(abs(step) for step in delta) <= CONVERGENCE_TOLERANCE:
            converged = True
            break

    if not converged:
        raise EconomicFamilyValidationError("logistic solver did not converge")
    return LogisticModel(
        standardization=standardization,
        coefficients=tuple(weights),
        iterations=completed,
        converged=True,
    )


def evaluate_logistic_policy(
    *,
    partition: str,
    rows: tuple[EconomicDevelopmentRow, ...],
    model: LogisticModel,
    hurdle: Decimal,
) -> LogisticEvaluation:
    eligible = 0
    selected: list[tuple[Decimal, Decimal]] = []
    for row in rows:
        prepared = _prepared_row(row)
        if prepared is None:
            continue
        raw_features, known_net = prepared
        eligible += 1
        if model.probability(raw_features) >= hurdle:
            entry = row.entry_ask if _h2_action(row) > 0 else row.entry_bid
            if entry is None:
                raise EconomicFamilyValidationError("selected row entry price is missing")
            selected.append((known_net, known_net / entry * BPS))

    if not selected:
        return LogisticEvaluation(
            partition=partition,
            eligible_rows=eligible,
            selected_trades=0,
            positive_selected_trades=0,
            selection_rate=_ZERO,
            positive_fraction=None,
            mean_known_net_quote=None,
            median_known_net_bps=None,
            aggregate_known_net_quote=None,
        )
    nets = tuple(item[0] for item in selected)
    net_bps = tuple(item[1] for item in selected)
    return LogisticEvaluation(
        partition=partition,
        eligible_rows=eligible,
        selected_trades=len(selected),
        positive_selected_trades=sum(value > 0 for value in nets),
        selection_rate=_ratio(len(selected), eligible),
        positive_fraction=_ratio(sum(value > 0 for value in nets), len(selected)),
        mean_known_net_quote=_mean(nets),
        median_known_net_bps=median(net_bps),
        aggregate_known_net_quote=sum(nets, _ZERO),
    )


def economic_probability_hurdle(
    *,
    mean_positive: Decimal,
    mean_nonpositive: Decimal,
) -> Decimal:
    if mean_positive <= 0 or mean_nonpositive > 0:
        raise EconomicFamilyValidationError(
            "economic hurdle requires positive gain and nonpositive loss means"
        )
    denominator = mean_positive - mean_nonpositive
    if denominator <= 0:
        raise EconomicFamilyValidationError("economic hurdle denominator must be positive")
    with localcontext() as ctx:
        ctx.prec = 60
        hurdle = (-mean_nonpositive) / denominator
    if hurdle <= 0 or hurdle >= 1:
        raise EconomicFamilyValidationError("economic probability hurdle must lie in (0,1)")
    return hurdle


def write_logistic_development_report(
    report: LogisticDevelopmentReport,
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
            raise EconomicFamilyValidationError(
                "existing logistic development report differs from deterministic output"
            ) from None
    return target


def _model_matrix(
    rows: tuple[EconomicDevelopmentRow, ...],
) -> tuple[tuple[tuple[Decimal, ...], ...], tuple[int, ...], tuple[Decimal, ...]]:
    features: list[tuple[Decimal, ...]] = []
    targets: list[int] = []
    nets: list[Decimal] = []
    for row in rows:
        prepared = _prepared_row(row)
        if prepared is None:
            continue
        raw_features, known_net = prepared
        features.append(raw_features)
        targets.append(int(known_net > 0))
        nets.append(known_net)
    return tuple(features), tuple(targets), tuple(nets)


def _prepared_row(
    row: EconomicDevelopmentRow,
) -> tuple[tuple[Decimal, ...], Decimal] | None:
    action = _h2_action(row)
    if action == 0:
        return None
    if (
        row.hl_bbo_imbalance is None
        or row.binance_mid_return_5s_bps is None
        or row.hl_spread_bps is None
    ):
        return None
    economics = executable_known_net(row, action=action)
    if economics is None:
        return None
    known_net = economics[2]
    raw_features = (
        abs(row.hl_bbo_imbalance),
        Decimal(action) * row.binance_mid_return_5s_bps,
        abs(row.binance_mid_return_5s_bps),
        row.hl_spread_bps,
    )
    return raw_features, known_net


def _h2_action(row: EconomicDevelopmentRow) -> int:
    imbalance = row.hl_bbo_imbalance
    if imbalance is None or imbalance == 0:
        return 0
    return 1 if imbalance > 0 else -1


def _fit_standardization(
    x: tuple[tuple[Decimal, ...], ...],
) -> Standardization:
    columns = tuple(zip(*x, strict=True))
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
        if scale == 0:
            raise EconomicFamilyValidationError("logistic feature has zero variance")
        scales.append(scale)
    return Standardization(means=means, scales=tuple(scales))


def _sigmoid(value: Decimal) -> Decimal:
    clipped = max(-_EXP_CLIP, min(_EXP_CLIP, value))
    with localcontext() as ctx:
        ctx.prec = 60
        return _ONE / (_ONE + (-clipped).exp())


def _solve_linear_system(
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
            raise EconomicFamilyValidationError("singular logistic information matrix")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
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


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise EconomicFamilyValidationError("cannot take mean of empty values")
    with localcontext() as ctx:
        ctx.prec = 60
        return sum(values, _ZERO) / Decimal(len(values))


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        raise EconomicFamilyValidationError("ratio denominator must be positive")
    with localcontext() as ctx:
        ctx.prec = 60
        return Decimal(numerator) / Decimal(denominator)


def _serialize_optional(value: Decimal | None) -> str | None:
    return None if value is None else serialize_exact_decimal(value)
