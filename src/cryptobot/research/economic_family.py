from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum
from pathlib import Path
from statistics import median
from typing import cast

from cryptobot.data.numeric import serialize_exact_decimal

FEE_SCENARIO_BPS_PER_SIDE = Decimal("4.5")
EXPECTED_DEVELOPMENT_SOURCE_SHA256 = "TO_BE_BOUND_AFTER_DETERMINISTIC_CACHE_BUILD"
BPS = Decimal("10000")


class EconomicFamilyValidationError(ValueError):
    """Raised when TASK-023 development evidence violates its frozen development contract."""


class DevelopmentDecision(StrEnum):
    FREEZE_DETERMINISTIC_FAMILY = "FREEZE_DETERMINISTIC_FAMILY"
    DEVELOP_REGULARIZED_LOGISTIC_BASELINE = "DEVELOP_REGULARIZED_LOGISTIC_BASELINE"


@dataclass(frozen=True, slots=True)
class EconomicDevelopmentRow:
    row_id: str
    decision_recv_wall_ns: int
    invalid_reasons: tuple[str, ...]
    entry_bid: Decimal | None
    entry_ask: Decimal | None
    exit_bid: Decimal | None
    exit_ask: Decimal | None
    hl_spread_bps: Decimal | None
    hl_bbo_imbalance: Decimal | None
    binance_mid_return_5s_bps: Decimal | None
    outcome_invalid_reasons: tuple[str, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> EconomicDevelopmentRow:
        return cls(
            row_id=_string(payload, "row_id"),
            decision_recv_wall_ns=_integer(payload, "decision_recv_wall_ns"),
            invalid_reasons=_string_tuple(payload, "invalid_reasons"),
            entry_bid=_decimal_or_none(payload.get("entry_bid")),
            entry_ask=_decimal_or_none(payload.get("entry_ask")),
            exit_bid=_decimal_or_none(payload.get("exit_bid")),
            exit_ask=_decimal_or_none(payload.get("exit_ask")),
            hl_spread_bps=_decimal_or_none(payload.get("hl_spread_bps")),
            hl_bbo_imbalance=_decimal_or_none(payload.get("hl_bbo_imbalance")),
            binance_mid_return_5s_bps=_decimal_or_none(payload.get("binance_mid_return_5s_bps")),
            outcome_invalid_reasons=_string_tuple(payload, "outcome_invalid_reasons"),
        )


@dataclass(frozen=True, slots=True)
class FeatureThresholds:
    abs_imbalance_q75: Decimal
    abs_reference_return_q75: Decimal
    spread_q50: Decimal

    def as_dict(self) -> dict[str, str]:
        return {
            "abs_imbalance_q75": serialize_exact_decimal(self.abs_imbalance_q75),
            "abs_reference_return_q75": serialize_exact_decimal(self.abs_reference_return_q75),
            "spread_q50": serialize_exact_decimal(self.spread_q50),
        }


@dataclass(frozen=True, slots=True)
class CandidateResult:
    candidate_id: str
    row_count: int
    action_count: int
    valid_trade_count: int
    positive_known_net_count: int
    mean_gross_quote: Decimal | None
    mean_fee_quote: Decimal | None
    mean_known_net_quote: Decimal | None
    mean_known_net_bps: Decimal | None
    median_known_net_bps: Decimal | None

    @property
    def positive_known_net_fraction(self) -> Decimal | None:
        if self.valid_trade_count == 0:
            return None
        return _ratio(self.positive_known_net_count, self.valid_trade_count)

    @property
    def trade_rate(self) -> Decimal:
        return _ratio(self.valid_trade_count, self.row_count)

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "row_count": self.row_count,
            "action_count": self.action_count,
            "valid_trade_count": self.valid_trade_count,
            "positive_known_net_count": self.positive_known_net_count,
            "positive_known_net_fraction": _serialize_optional(self.positive_known_net_fraction),
            "trade_rate": serialize_exact_decimal(self.trade_rate),
            "mean_gross_quote": _serialize_optional(self.mean_gross_quote),
            "mean_fee_quote": _serialize_optional(self.mean_fee_quote),
            "mean_known_net_quote": _serialize_optional(self.mean_known_net_quote),
            "mean_known_net_bps": _serialize_optional(self.mean_known_net_bps),
            "median_known_net_bps": _serialize_optional(self.median_known_net_bps),
        }


CANDIDATE_IDS = (
    "E0_H2_BASELINE",
    "E1_H2_STRONG_IMBALANCE",
    "E2_H2_REFERENCE_AGREEMENT",
    "E3_H2_AGREE_STRONG_REFERENCE",
    "E4_H2_AGREE_STRONG_IMBALANCE_TIGHT_SPREAD",
)
NEW_CANDIDATE_IDS = CANDIDATE_IDS[1:]


@dataclass(frozen=True, slots=True)
class EconomicDevelopmentReport:
    source_sha256: str
    row_count: int
    dev_a_row_count: int
    dev_b_row_count: int
    dev_b_start_wall_ns: int
    thresholds: FeatureThresholds
    dev_a_results: tuple[CandidateResult, ...]
    dev_b_results: tuple[CandidateResult, ...]
    decision: DevelopmentDecision
    deterministic_shortlist: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "report_version": "stage2-economic-family-development-v1",
            "source_sha256": self.source_sha256,
            "row_count": self.row_count,
            "dev_a_row_count": self.dev_a_row_count,
            "dev_b_row_count": self.dev_b_row_count,
            "dev_b_start_wall_ns": self.dev_b_start_wall_ns,
            "split_rule": ("chronological 50/50 by row count; equal wall timestamps stay in DEV_B"),
            "threshold_source": "DEV_A_FEATURE_DISTRIBUTION_ONLY",
            "thresholds": self.thresholds.as_dict(),
            "candidate_registry": list(CANDIDATE_IDS),
            "dev_a_results": [item.as_dict() for item in self.dev_a_results],
            "dev_b_results": [item.as_dict() for item in self.dev_b_results],
            "decision": self.decision.value,
            "deterministic_shortlist": list(self.deterministic_shortlist),
            "decision_rule": (
                "shortlist at most two NEW candidates with >=100 DEV_B valid trades, "
                "positive DEV_B mean known-net quote PnL, and positive DEV_B median "
                "known-net bps; rank by mean known-net bps then candidate_id. If none "
                "qualify, do not collect fresh test data yet and develop one regularized "
                "logistic baseline on development evidence only."
            ),
            "economic_scope": (
                "partial-known-cost only: executable bid/ask plus frozen 4.5 bps/side "
                "fee scenario; latency/impact/funding remain UNKNOWN"
            ),
            "confirmation_used": False,
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


def load_development_rows(
    path: str | Path,
) -> tuple[str, tuple[EconomicDevelopmentRow, ...]]:
    target = Path(path)
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise EconomicFamilyValidationError(
            f"cannot read TASK-023 development cache: {target}"
        ) from exc
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EconomicFamilyValidationError("TASK-023 development cache is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise EconomicFamilyValidationError("development cache must be an object")
    obj = cast(dict[str, object], payload)
    raw_rows = obj.get("rows")
    if not isinstance(raw_rows, list):
        raise EconomicFamilyValidationError("development rows must be a list")
    rows: list[EconomicDevelopmentRow] = []
    for item in raw_rows:
        if not isinstance(item, dict):
            raise EconomicFamilyValidationError("development row must be an object")
        rows.append(EconomicDevelopmentRow.from_dict(cast(dict[str, object], item)))
    ordered = tuple(sorted(rows, key=lambda item: (item.decision_recv_wall_ns, item.row_id)))
    if len({row.row_id for row in ordered}) != len(ordered):
        raise EconomicFamilyValidationError("development row_id values must be unique")
    return digest, ordered


def evaluate_economic_development(
    source_sha256: str,
    rows: tuple[EconomicDevelopmentRow, ...],
) -> EconomicDevelopmentReport:
    if len(source_sha256) != 64:
        raise EconomicFamilyValidationError("source SHA-256 must be 64 hex characters")
    if len(rows) < 400:
        raise EconomicFamilyValidationError("development evidence is too small")

    dev_a, dev_b = chronological_development_split(rows)
    thresholds = derive_feature_thresholds(dev_a)

    a_results = tuple(
        evaluate_candidate(dev_a, candidate_id=item, thresholds=thresholds)
        for item in CANDIDATE_IDS
    )
    b_results = tuple(
        evaluate_candidate(dev_b, candidate_id=item, thresholds=thresholds)
        for item in CANDIDATE_IDS
    )
    shortlist = deterministic_shortlist(b_results)
    decision = (
        DevelopmentDecision.FREEZE_DETERMINISTIC_FAMILY
        if shortlist
        else DevelopmentDecision.DEVELOP_REGULARIZED_LOGISTIC_BASELINE
    )
    return EconomicDevelopmentReport(
        source_sha256=source_sha256,
        row_count=len(rows),
        dev_a_row_count=len(dev_a),
        dev_b_row_count=len(dev_b),
        dev_b_start_wall_ns=dev_b[0].decision_recv_wall_ns,
        thresholds=thresholds,
        dev_a_results=a_results,
        dev_b_results=b_results,
        decision=decision,
        deterministic_shortlist=shortlist,
    )


def chronological_development_split(
    rows: tuple[EconomicDevelopmentRow, ...],
) -> tuple[tuple[EconomicDevelopmentRow, ...], tuple[EconomicDevelopmentRow, ...]]:
    ordered = tuple(sorted(rows, key=lambda item: (item.decision_recv_wall_ns, item.row_id)))
    split = len(ordered) // 2
    while (
        split < len(ordered)
        and split > 0
        and ordered[split].decision_recv_wall_ns == ordered[split - 1].decision_recv_wall_ns
    ):
        split += 1
    if split <= 0 or split >= len(ordered):
        raise EconomicFamilyValidationError("cannot form chronological DEV_A/DEV_B split")
    return ordered[:split], ordered[split:]


def derive_feature_thresholds(
    dev_a: tuple[EconomicDevelopmentRow, ...],
) -> FeatureThresholds:
    imbalance = tuple(
        abs(row.hl_bbo_imbalance) for row in dev_a if row.hl_bbo_imbalance is not None
    )
    reference = tuple(
        abs(row.binance_mid_return_5s_bps)
        for row in dev_a
        if row.binance_mid_return_5s_bps is not None
    )
    spreads = tuple(row.hl_spread_bps for row in dev_a if row.hl_spread_bps is not None)
    if not imbalance or not reference or not spreads:
        raise EconomicFamilyValidationError("DEV_A feature distribution is incomplete")
    return FeatureThresholds(
        abs_imbalance_q75=_quantile(imbalance, Decimal("0.75")),
        abs_reference_return_q75=_quantile(reference, Decimal("0.75")),
        spread_q50=_quantile(spreads, Decimal("0.50")),
    )


def evaluate_candidate(
    rows: tuple[EconomicDevelopmentRow, ...],
    *,
    candidate_id: str,
    thresholds: FeatureThresholds,
) -> CandidateResult:
    if candidate_id not in CANDIDATE_IDS:
        raise EconomicFamilyValidationError(f"unknown candidate_id: {candidate_id}")

    action_count = 0
    economics: list[tuple[Decimal, Decimal, Decimal, Decimal]] = []
    for row in rows:
        action = candidate_action(row, candidate_id=candidate_id, thresholds=thresholds)
        action_count += int(action != 0)
        result = executable_known_net(row, action=action)
        if result is not None:
            economics.append(result)

    if not economics:
        return CandidateResult(
            candidate_id=candidate_id,
            row_count=len(rows),
            action_count=action_count,
            valid_trade_count=0,
            positive_known_net_count=0,
            mean_gross_quote=None,
            mean_fee_quote=None,
            mean_known_net_quote=None,
            mean_known_net_bps=None,
            median_known_net_bps=None,
        )

    gross = tuple(item[0] for item in economics)
    fees = tuple(item[1] for item in economics)
    net = tuple(item[2] for item in economics)
    net_bps = tuple(item[3] for item in economics)
    return CandidateResult(
        candidate_id=candidate_id,
        row_count=len(rows),
        action_count=action_count,
        valid_trade_count=len(economics),
        positive_known_net_count=sum(value > 0 for value in net),
        mean_gross_quote=_mean(gross),
        mean_fee_quote=_mean(fees),
        mean_known_net_quote=_mean(net),
        mean_known_net_bps=_mean(net_bps),
        median_known_net_bps=median(net_bps),
    )


def candidate_action(
    row: EconomicDevelopmentRow,
    *,
    candidate_id: str,
    thresholds: FeatureThresholds,
) -> int:
    imbalance = row.hl_bbo_imbalance
    reference = row.binance_mid_return_5s_bps
    spread = row.hl_spread_bps
    direction = _sign(imbalance)
    reference_direction = _sign(reference)
    if direction == 0:
        return 0
    if candidate_id == "E0_H2_BASELINE":
        return direction
    if candidate_id == "E1_H2_STRONG_IMBALANCE":
        return (
            direction
            if imbalance is not None and abs(imbalance) >= thresholds.abs_imbalance_q75
            else 0
        )
    if candidate_id == "E2_H2_REFERENCE_AGREEMENT":
        return direction if reference_direction != 0 and reference_direction == direction else 0
    if candidate_id == "E3_H2_AGREE_STRONG_REFERENCE":
        return (
            direction
            if reference_direction == direction
            and reference is not None
            and abs(reference) >= thresholds.abs_reference_return_q75
            else 0
        )
    if candidate_id == "E4_H2_AGREE_STRONG_IMBALANCE_TIGHT_SPREAD":
        return (
            direction
            if reference_direction == direction
            and imbalance is not None
            and abs(imbalance) >= thresholds.abs_imbalance_q75
            and spread is not None
            and spread <= thresholds.spread_q50
            else 0
        )
    raise EconomicFamilyValidationError(f"unknown candidate_id: {candidate_id}")


def executable_known_net(
    row: EconomicDevelopmentRow,
    *,
    action: int,
) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
    if action == 0:
        return None
    if row.invalid_reasons or row.outcome_invalid_reasons:
        return None
    if None in (row.entry_bid, row.entry_ask, row.exit_bid, row.exit_ask):
        return None
    entry_bid = cast(Decimal, row.entry_bid)
    entry_ask = cast(Decimal, row.entry_ask)
    exit_bid = cast(Decimal, row.exit_bid)
    exit_ask = cast(Decimal, row.exit_ask)

    if action > 0:
        gross = exit_bid - entry_ask
        fee = (entry_ask + exit_bid) * FEE_SCENARIO_BPS_PER_SIDE / BPS
        entry_notional = entry_ask
    else:
        gross = entry_bid - exit_ask
        fee = (entry_bid + exit_ask) * FEE_SCENARIO_BPS_PER_SIDE / BPS
        entry_notional = entry_bid
    net = gross - fee
    return gross, fee, net, net / entry_notional * BPS


def deterministic_shortlist(
    dev_b_results: tuple[CandidateResult, ...],
) -> tuple[str, ...]:
    eligible = [
        item
        for item in dev_b_results
        if item.candidate_id in NEW_CANDIDATE_IDS
        and item.valid_trade_count >= 100
        and item.mean_known_net_quote is not None
        and item.mean_known_net_quote > 0
        and item.median_known_net_bps is not None
        and item.median_known_net_bps > 0
    ]
    eligible.sort(
        key=lambda item: (
            -cast(Decimal, item.mean_known_net_bps),
            item.candidate_id,
        )
    )
    return tuple(item.candidate_id for item in eligible[:2])


def write_development_report(
    report: EconomicDevelopmentReport,
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
                "existing development report differs from deterministic output"
            ) from None
    return target


def _quantile(values: tuple[Decimal, ...], q: Decimal) -> Decimal:
    if not values or q < 0 or q > 1:
        raise EconomicFamilyValidationError("invalid quantile request")
    ordered = tuple(sorted(values))
    if len(ordered) == 1:
        return ordered[0]
    with localcontext() as ctx:
        ctx.prec = 60
        position = Decimal(len(ordered) - 1) * q
        low = int(position)
        high = min(low + 1, len(ordered) - 1)
        fraction = position - Decimal(low)
        return ordered[low] * (_ONE - fraction) + ordered[high] * fraction


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 60
        return sum(values, Decimal(0)) / Decimal(len(values))


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        raise EconomicFamilyValidationError("ratio denominator must be positive")
    with localcontext() as ctx:
        ctx.prec = 60
        return Decimal(numerator) / Decimal(denominator)


def _sign(value: Decimal | None) -> int:
    if value is None or value == 0:
        return 0
    return 1 if value > 0 else -1


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EconomicFamilyValidationError("numeric development fields must be strings")
    try:
        return Decimal(value)
    except Exception as exc:
        raise EconomicFamilyValidationError("invalid exact decimal string") from exc


def _string(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise EconomicFamilyValidationError(f"{field} must be a non-empty string")
    return value


def _integer(payload: dict[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EconomicFamilyValidationError(f"{field} must be an integer")
    return value


def _string_tuple(payload: dict[str, object], field: str) -> tuple[str, ...]:
    value = payload.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise EconomicFamilyValidationError(f"{field} must be a string list")
    return tuple(cast(list[str], value))


def _serialize_optional(value: Decimal | None) -> str | None:
    return None if value is None else serialize_exact_decimal(value)


_ONE = Decimal(1)
