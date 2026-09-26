from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import cast

HORIZON_CONTEXT_SHA256 = "effefa74fe611bc2e77bc40177cf652193632b1163768a384870a3eb579dc722"
HORIZON_DECISION_SHA256 = "626f85a08ca187d0c1762cdc7a22c49dfe2301baa97ad9d09c1fdd5acfb164e6"
REGISTRY_SHA256 = "f0290fc70dda2911afab02f1a92b4f4262ff6ec1883a25fa86cb129fd4d2a7a8"
CACHE_SHA256 = "459e85a618f5026862428eadd34a652fe1bc63d59d19580e3ea38cf0d3d243b4"
DETERMINISTIC_RESULTS_SHA256 = "b7555046b013a6564560095d36c4cd2a7638fc4b5b880e8359acd08919920201"
LOGISTIC_RESULTS_SHA256 = "a11358926b8b69f764e3e0a595f913d17baec8f133521efb81f1f9578ce456d0"
MIN_VALID_TRADES = 30


class LongHorizonValidationError(ValueError):
    """Raised when frozen TASK-024 development evidence is inconsistent."""


class LongHorizonDecision(StrEnum):
    FREEZE_300S_FAMILY = "FREEZE_300S_FAMILY"
    STOP_300S_FAMILY = "STOP_300S_FAMILY"


@dataclass(frozen=True, slots=True)
class LongHorizonReport:
    horizon_seconds: int
    horizon_context_sha256: str
    horizon_decision_sha256: str
    registry_sha256: str
    cache_sha256: str
    deterministic_results_sha256: str
    logistic_results_sha256: str
    deterministic_passing_candidates: tuple[str, ...]
    logistic_passing_gates: tuple[str, ...]
    decision: LongHorizonDecision
    old_confirmation_status: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "report_version": "stage2-long-horizon-development-v1",
            "horizon_seconds": self.horizon_seconds,
            "horizon_context_sha256": self.horizon_context_sha256,
            "horizon_decision_sha256": self.horizon_decision_sha256,
            "registry_sha256": self.registry_sha256,
            "cache_sha256": self.cache_sha256,
            "deterministic_results_sha256": self.deterministic_results_sha256,
            "logistic_results_sha256": self.logistic_results_sha256,
            "deterministic_passing_candidates": list(self.deterministic_passing_candidates),
            "logistic_passing_gates": list(self.logistic_passing_gates),
            "decision": self.decision.value,
            "old_confirmation_status": self.old_confirmation_status,
            "fresh_test_evidence_collected": False,
            "economic_scope": (
                "partial-known-cost only: executable bid/ask plus frozen "
                "4.5 bps/side fee scenario; latency/impact/funding and actual "
                "project-account fee tier remain UNKNOWN"
            ),
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


def load_json_with_sha(
    path: str | Path,
    *,
    expected_sha256: str,
) -> dict[str, object]:
    target = Path(path)
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise LongHorizonValidationError(f"cannot read artifact: {target}") from exc
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise LongHorizonValidationError(f"artifact SHA-256 mismatch for {target.name}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LongHorizonValidationError(f"artifact is invalid JSON: {target.name}") from exc
    if not isinstance(payload, dict):
        raise LongHorizonValidationError("artifact root must be an object")
    return cast(dict[str, object], payload)


def adjudicate_long_horizon(
    *,
    horizon_context: dict[str, object],
    horizon_decision: dict[str, object],
    registry: dict[str, object],
    deterministic_results: dict[str, object],
    logistic_results: dict[str, object],
) -> LongHorizonReport:
    _validate_chain(
        horizon_context=horizon_context,
        horizon_decision=horizon_decision,
        registry=registry,
        deterministic_results=deterministic_results,
        logistic_results=logistic_results,
    )

    deterministic_passes = _deterministic_passes(deterministic_results)
    if deterministic_passes:
        return LongHorizonReport(
            horizon_seconds=300,
            horizon_context_sha256=HORIZON_CONTEXT_SHA256,
            horizon_decision_sha256=HORIZON_DECISION_SHA256,
            registry_sha256=REGISTRY_SHA256,
            cache_sha256=CACHE_SHA256,
            deterministic_results_sha256=DETERMINISTIC_RESULTS_SHA256,
            logistic_results_sha256=LOGISTIC_RESULTS_SHA256,
            deterministic_passing_candidates=deterministic_passes,
            logistic_passing_gates=(),
            decision=LongHorizonDecision.FREEZE_300S_FAMILY,
            old_confirmation_status="UNOPENED_AND_EXCLUDED",
        )

    logistic_passes = _logistic_passes(logistic_results)
    return LongHorizonReport(
        horizon_seconds=300,
        horizon_context_sha256=HORIZON_CONTEXT_SHA256,
        horizon_decision_sha256=HORIZON_DECISION_SHA256,
        registry_sha256=REGISTRY_SHA256,
        cache_sha256=CACHE_SHA256,
        deterministic_results_sha256=DETERMINISTIC_RESULTS_SHA256,
        logistic_results_sha256=LOGISTIC_RESULTS_SHA256,
        deterministic_passing_candidates=(),
        logistic_passing_gates=logistic_passes,
        decision=(
            LongHorizonDecision.FREEZE_300S_FAMILY
            if logistic_passes
            else LongHorizonDecision.STOP_300S_FAMILY
        ),
        old_confirmation_status="UNOPENED_AND_EXCLUDED",
    )


def write_long_horizon_report(
    report: LongHorizonReport,
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
            raise LongHorizonValidationError(
                "existing long-horizon report differs from deterministic output"
            ) from None
    return target


def _validate_chain(
    *,
    horizon_context: dict[str, object],
    horizon_decision: dict[str, object],
    registry: dict[str, object],
    deterministic_results: dict[str, object],
    logistic_results: dict[str, object],
) -> None:
    if horizon_context.get("purpose") != "TASK_023_DEVELOPMENT_ONLY_HORIZON_CONTEXT":
        raise LongHorizonValidationError("unexpected horizon context purpose")
    if horizon_decision.get("source_sha256") != HORIZON_CONTEXT_SHA256:
        raise LongHorizonValidationError("horizon decision source hash mismatch")
    if horizon_decision.get("chosen_development_horizon_seconds") != 300:
        raise LongHorizonValidationError("frozen development horizon must be 300s")
    if registry.get("created_before_hyperliquid_300s_outcome_evaluation") is not True:
        raise LongHorizonValidationError("300s registry must be pre-outcome")
    if registry.get("horizon_decision_sha256") != HORIZON_DECISION_SHA256:
        raise LongHorizonValidationError("registry horizon-decision hash mismatch")
    if registry.get("old_confirmation") != "EXCLUDED_AND_UNOPENED":
        raise LongHorizonValidationError("old confirmation must remain excluded")
    if deterministic_results.get("cache_sha256") != CACHE_SHA256:
        raise LongHorizonValidationError("deterministic cache hash mismatch")
    if deterministic_results.get("registry_sha256") != REGISTRY_SHA256:
        raise LongHorizonValidationError("deterministic registry hash mismatch")
    if logistic_results.get("cache_sha256") != CACHE_SHA256:
        raise LongHorizonValidationError("logistic cache hash mismatch")
    if logistic_results.get("registry_sha256") != REGISTRY_SHA256:
        raise LongHorizonValidationError("logistic registry hash mismatch")


def _deterministic_passes(
    payload: dict[str, object],
) -> tuple[str, ...]:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise LongHorizonValidationError("deterministic results must be a list")

    passing: list[str] = []
    for raw in raw_results:
        if not isinstance(raw, dict):
            raise LongHorizonValidationError("deterministic result must be an object")
        result = cast(dict[str, object], raw)
        candidate_raw = result.get("candidate")
        partitions_raw = result.get("partitions")
        if not isinstance(candidate_raw, dict) or not isinstance(partitions_raw, dict):
            raise LongHorizonValidationError("candidate/partitions are missing")
        candidate = cast(dict[str, object], candidate_raw)
        partitions = cast(dict[str, object], partitions_raw)
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise LongHorizonValidationError("candidate id is invalid")
        if candidate_id == "BENCHMARK_H2_UNFILTERED_300S":
            continue
        dev_b_raw = partitions.get("DEV_B")
        if not isinstance(dev_b_raw, dict):
            raise LongHorizonValidationError("DEV_B result is missing")
        dev_b = cast(dict[str, object], dev_b_raw)
        valid = _int(dev_b, "valid_trade_count")
        mean = _optional_decimal(dev_b.get("mean_partial_known_cost_pnl"))
        total = _optional_decimal(dev_b.get("sum_partial_known_cost_pnl"))
        if (
            valid >= MIN_VALID_TRADES
            and mean is not None
            and mean > 0
            and total is not None
            and total > 0
        ):
            passing.append(candidate_id)
    return tuple(sorted(passing))


def _logistic_passes(payload: dict[str, object]) -> tuple[str, ...]:
    gates_raw = payload.get("gates")
    if not isinstance(gates_raw, dict):
        raise LongHorizonValidationError("logistic gates must be an object")
    gates = cast(dict[str, object], gates_raw)
    passing: list[str] = []
    for name, raw in sorted(gates.items()):
        if not isinstance(raw, dict):
            raise LongHorizonValidationError("logistic gate must be an object")
        gate = cast(dict[str, object], raw)
        dev_b_raw = gate.get("DEV_B")
        if not isinstance(dev_b_raw, dict):
            raise LongHorizonValidationError("logistic DEV_B is missing")
        dev_b = cast(dict[str, object], dev_b_raw)
        valid = _int(dev_b, "valid_trade_count")
        mean = _optional_decimal(dev_b.get("mean_partial_known_cost_pnl"))
        total = _optional_decimal(dev_b.get("sum_partial_known_cost_pnl"))
        if (
            valid >= MIN_VALID_TRADES
            and mean is not None
            and mean > 0
            and total is not None
            and total > 0
        ):
            passing.append(name)
    return tuple(passing)


def _int(payload: dict[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LongHorizonValidationError(f"{field} must be an integer")
    return value


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LongHorizonValidationError("numeric result must be an exact decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise LongHorizonValidationError("invalid exact decimal result") from exc
