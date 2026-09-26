from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptobot.research.economic_family import (
    EconomicFamilyValidationError,
    executable_known_net,
)
from cryptobot.research.microstructure_family import (
    MIN_COMPLETE_300S,
    REGISTRY_SHA256,
    TRAINING_CACHE_50S_SHA256,
    TRAINING_CACHE_300S_SHA256,
    MicrostructureRow,
    feature_vector,
    h2_direction,
    load_cache,
)

MIN_POSITIVE_CLASS = 30
MIN_NONPOSITIVE_CLASS = 30


@dataclass(frozen=True, slots=True)
class HorizonSupport:
    horizon_seconds: int
    row_count: int
    feature_complete_count: int
    valid_target_count: int
    positive_target_count: int
    nonpositive_target_count: int
    feature_support_passed: bool
    class_support_passed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "horizon_seconds": self.horizon_seconds,
            "row_count": self.row_count,
            "feature_complete_count": self.feature_complete_count,
            "valid_target_count": self.valid_target_count,
            "positive_target_count": self.positive_target_count,
            "nonpositive_target_count": self.nonpositive_target_count,
            "feature_support_passed": self.feature_support_passed,
            "class_support_passed": self.class_support_passed,
            "min_positive_class": MIN_POSITIVE_CLASS,
            "min_nonpositive_class": MIN_NONPOSITIVE_CLASS,
        }


@dataclass(frozen=True, slots=True)
class MicrostructureDecisionReport:
    registry_sha256: str
    cache_50s_sha256: str
    cache_300s_sha256: str
    exposed_dev_b_contaminated: bool
    contamination_reason: str
    horizon_50s: HorizonSupport
    horizon_300s: HorizonSupport
    decision: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "report_version": "stage2-task025-microstructure-decision-v1",
            "registry_sha256": self.registry_sha256,
            "cache_50s_sha256": self.cache_50s_sha256,
            "cache_300s_sha256": self.cache_300s_sha256,
            "exposed_dev_b_contaminated": self.exposed_dev_b_contaminated,
            "contamination_reason": self.contamination_reason,
            "horizon_50s": self.horizon_50s.as_dict(),
            "horizon_300s": self.horizon_300s.as_dict(),
            "decision": self.decision,
            "reasons": list(self.reasons),
            "old_confirmation_used": False,
            "fresh_development_validation_started": False,
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


def summarize_support(
    rows: tuple[MicrostructureRow, ...],
    *,
    horizon_seconds: int,
    min_feature_complete: int,
) -> HorizonSupport:
    complete = 0
    valid = 0
    positive = 0
    nonpositive = 0
    for row in rows:
        if feature_vector(row) is None:
            continue
        complete += 1
        economics = executable_known_net(row.base, action=h2_direction(row))
        if economics is None:
            continue
        valid += 1
        if economics[2] > 0:
            positive += 1
        else:
            nonpositive += 1
    return HorizonSupport(
        horizon_seconds=horizon_seconds,
        row_count=len(rows),
        feature_complete_count=complete,
        valid_target_count=valid,
        positive_target_count=positive,
        nonpositive_target_count=nonpositive,
        feature_support_passed=complete >= min_feature_complete,
        class_support_passed=(
            positive >= MIN_POSITIVE_CLASS and nonpositive >= MIN_NONPOSITIVE_CLASS
        ),
    )


def adjudicate_task025(
    rows_50s: tuple[MicrostructureRow, ...],
    rows_300s: tuple[MicrostructureRow, ...],
) -> MicrostructureDecisionReport:
    support_50 = summarize_support(
        rows_50s,
        horizon_seconds=50,
        min_feature_complete=300,
    )
    support_300 = summarize_support(
        rows_300s,
        horizon_seconds=300,
        min_feature_complete=MIN_COMPLETE_300S,
    )

    reasons: list[str] = []
    if not support_50.class_support_passed:
        reasons.append("50S_TARGET_CLASS_SUPPORT_BELOW_30_30")
    if not support_300.feature_support_passed:
        reasons.append("300S_FEATURE_SUPPORT_BELOW_FROZEN_MINIMUM")
    if not support_300.class_support_passed:
        reasons.append("300S_TARGET_CLASS_SUPPORT_BELOW_30_30")
    reasons.append("PRE_REGISTRY_SIX_FEATURE_DEV_B_WAS_ALREADY_EXPOSED")

    return MicrostructureDecisionReport(
        registry_sha256=REGISTRY_SHA256,
        cache_50s_sha256=TRAINING_CACHE_50S_SHA256,
        cache_300s_sha256=TRAINING_CACHE_300S_SHA256,
        exposed_dev_b_contaminated=True,
        contamination_reason=(
            "A six-feature microstructure DEV_B report was generated before the "
            "full eight-feature TASK-025 registry. Pre-cutoff evidence is therefore "
            "treated as exposed development only and is not reused as independent "
            "DEV_B validation."
        ),
        horizon_50s=support_50,
        horizon_300s=support_300,
        decision="STOP_MICROSTRUCTURE_FAMILY",
        reasons=tuple(sorted(set(reasons))),
    )


def build_task025_decision_from_paths(
    *,
    cache_50s: str | Path,
    cache_300s: str | Path,
) -> MicrostructureDecisionReport:
    rows_50 = load_cache(
        cache_50s,
        expected_sha256=TRAINING_CACHE_50S_SHA256,
    )
    rows_300 = load_cache(
        cache_300s,
        expected_sha256=TRAINING_CACHE_300S_SHA256,
    )
    return adjudicate_task025(rows_50, rows_300)


def write_decision_report(
    report: MicrostructureDecisionReport,
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
            raise EconomicFamilyValidationError(
                "existing TASK-025 decision report differs"
            ) from None
    return target
