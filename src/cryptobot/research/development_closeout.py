from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import cast

from cryptobot.data.numeric import serialize_exact_decimal
from cryptobot.research.campaign_dataset import load_campaign_segment, release_unused_arrow_memory
from cryptobot.research.development_campaign import (
    CAMPAIGN_ID,
    EVIDENCE_ROLE,
    TASK025_REGISTRY_SHA256,
    development_campaign_status,
    load_campaign_root,
    recover_campaign_start,
)
from cryptobot.research.microstructure_family import (
    FEATURE_NAMES,
    MIN_COMPLETE_300S,
    MicrostructureRow,
)
from cryptobot.research.microstructure_support import summarize_support
from cryptobot.research.prospective_microstructure import build_segment_rows


class DevelopmentCloseoutError(ValueError):
    """Raised when TASK-027 closeout cannot be reproduced from immutable evidence."""


def closeout_development_campaign(
    campaign_root: str | Path,
    *,
    output_root: str | Path,
    task025_registry_path: str | Path,
) -> dict[str, object]:
    root = Path(campaign_root)
    protocol, _ = load_campaign_root(root)
    start = recover_campaign_start(root, protocol=protocol)
    if start is None:
        raise DevelopmentCloseoutError("TASK-027 has no accepted campaign start")

    expected_deadline = start.started_wall_ns + protocol.duration_seconds * 1_000_000_000
    if start.deadline_wall_ns != expected_deadline:
        raise DevelopmentCloseoutError("campaign start/deadline violates frozen duration")

    registry_raw = Path(task025_registry_path).read_bytes()
    if hashlib.sha256(registry_raw).hexdigest() != TASK025_REGISTRY_SHA256:
        raise DevelopmentCloseoutError("TASK-025 registry SHA-256 mismatch")

    completion_path = root / "campaign-complete.json"
    if not completion_path.is_file():
        raise DevelopmentCloseoutError(
            "TASK-027 closeout is forbidden before fixed-duration completion"
        )
    completion_raw = completion_path.read_bytes()
    completion = _json_object(completion_raw, completion_path.name)
    if completion.get("protocol_sha256") != protocol.sha256:
        raise DevelopmentCloseoutError("completion protocol SHA-256 mismatch")
    if completion.get("started_wall_ns") != start.started_wall_ns:
        raise DevelopmentCloseoutError("completion start mismatch")
    if completion.get("deadline_wall_ns") != start.deadline_wall_ns:
        raise DevelopmentCloseoutError("completion deadline mismatch")
    if completion.get("reason") != "FIXED_DURATION_ELAPSED":
        raise DevelopmentCloseoutError("completion reason is not fixed-duration elapsed")
    if completion.get("outcome_dependent") is not False:
        raise DevelopmentCloseoutError("completion must be outcome-independent")
    observed_wall_ns = _required_int(completion, "observed_wall_ns")
    if observed_wall_ns < start.deadline_wall_ns:
        raise DevelopmentCloseoutError("completion marker predates frozen deadline")

    bindings = _bound_segments(
        root,
        protocol_sha256=protocol.sha256,
        started_wall_ns=start.started_wall_ns,
        deadline_wall_ns=start.deadline_wall_ns,
    )
    if not bindings:
        raise DevelopmentCloseoutError("TASK-027 has no bound DEVELOPMENT segments")

    rows_by_horizon: dict[int, list[tuple[MicrostructureRow, dict[str, object]]]] = {
        50: [],
        300: [],
    }
    intervals: list[tuple[int, int]] = []
    public_bindings: list[dict[str, object]] = []

    for segment_root, binding in bindings:
        segment_id = cast(str, binding["segment_id"])
        verified = load_campaign_segment(segment_root / "dataset", segment_id=segment_id)
        segment_meta = cast(dict[str, object], binding["segment"])
        if verified.data.evidence.as_dict() != segment_meta:
            raise DevelopmentCloseoutError(
                f"verified dataset metadata mismatch: {segment_root.name}"
            )
        if verified.manifest_sha256 != binding["dataset_manifest_sha256"]:
            raise DevelopmentCloseoutError(f"dataset manifest digest mismatch: {segment_root.name}")
        for horizon in (50, 300):
            rows_by_horizon[horizon].extend(
                build_segment_rows(
                    segment_root / "dataset",
                    segment_id=segment_id,
                    horizon_seconds=horizon,
                )
            )

        wall_start = max(start.started_wall_ns, _required_int(segment_meta, "wall_start_ns"))
        wall_end = min(start.deadline_wall_ns, _required_int(segment_meta, "wall_end_ns"))
        if wall_end > wall_start:
            intervals.append((wall_start, wall_end))
        public_bindings.append(
            {
                "run_id": binding["run_id"],
                "segment_id": segment_id,
                "segment_evidence_sha256": binding["segment_evidence_sha256"],
                "development_membership_sha256": binding["development_membership_sha256"],
                "dataset_bundle_sha256": segment_meta["dataset_bundle_sha256"],
                "dataset_manifest_sha256": binding["dataset_manifest_sha256"],
                "wall_start_ns": segment_meta["wall_start_ns"],
                "wall_end_ns": segment_meta["wall_end_ns"],
            }
        )
        del verified
        release_unused_arrow_memory()

    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    cache_meta: dict[str, object] = {}
    support_meta: dict[str, object] = {}

    for horizon in (50, 300):
        ordered = sorted(
            rows_by_horizon[horizon],
            key=lambda pair: (
                pair[0].base.decision_recv_wall_ns,
                pair[0].base.row_id,
            ),
        )
        rows = tuple(pair[0] for pair in ordered)
        cache_payload = {
            "schema_version": 1,
            "cache_version": "stage2-task027-development-feature-cache-v1",
            "campaign_protocol_sha256": protocol.sha256,
            "task025_registry_sha256": TASK025_REGISTRY_SHA256,
            "evidence_role": EVIDENCE_ROLE,
            "horizon_seconds": horizon,
            "source_segment_bindings": public_bindings,
            "row_count": len(rows),
            "rows": [pair[1] for pair in ordered],
        }
        cache_bytes = _canonical_bytes(cache_payload)
        cache_path = output / f"development-features-{horizon}s.json"
        _write_immutable(cache_path, cache_bytes)
        cache_sha = hashlib.sha256(cache_bytes).hexdigest()
        cache_meta[str(horizon)] = {
            "path": str(cache_path),
            "sha256": cache_sha,
            "row_count": len(rows),
        }

        minimum = 300 if horizon == 50 else MIN_COMPLETE_300S
        support = summarize_support(
            rows,
            horizon_seconds=horizon,
            min_feature_complete=minimum,
        )
        support_meta[str(horizon)] = {
            **support.as_dict(),
            "missing_feature_counts": _missing_feature_counts(rows),
            "zero_h2_direction_count": sum(
                1
                for row in rows
                if row.base.hl_bbo_imbalance is None or row.base.hl_bbo_imbalance == 0
            ),
            "task025_support_thresholds_are_reference_only": True,
            "task027_acceptance_rule": None,
        }

    coverage_ns = _union_ns(intervals)
    duration_ns = start.deadline_wall_ns - start.started_wall_ns
    status = development_campaign_status(root)
    pending_segments = tuple(
        sorted(
            path.name
            for path in root.glob("segment-*")
            if (path / "capture-ready.json").is_file()
            and not (path / "processing-started.json").exists()
            and not (path / "segment-evidence.json").exists()
        )
    )
    incomplete_segments = tuple(
        sorted(
            path.name
            for path in root.glob("segment-*")
            if (path / "processing-started.json").is_file()
            and not (path / "segment-evidence.json").is_file()
        )
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "report_version": "stage2-task027-development-closeout-v1",
        "campaign_id": CAMPAIGN_ID,
        "campaign_protocol_sha256": protocol.sha256,
        "task025_registry_sha256": TASK025_REGISTRY_SHA256,
        "evidence_role": EVIDENCE_ROLE,
        "started_wall_ns": start.started_wall_ns,
        "deadline_wall_ns": start.deadline_wall_ns,
        "completion_observed_wall_ns": observed_wall_ns,
        "completion_marker_sha256": hashlib.sha256(completion_raw).hexdigest(),
        "fixed_duration_elapsed": True,
        "published_capture_coverage_ns": coverage_ns,
        "protocol_duration_ns": duration_ns,
        "published_capture_coverage_fraction": serialize_exact_decimal(
            Decimal(coverage_ns) / Decimal(duration_ns)
        ),
        "uncovered_protocol_duration_ns": duration_ns - coverage_ns,
        "capture_attempt_count": status["capture_attempt_count"],
        "capture_ready_count": status["capture_ready_count"],
        "published_segment_count": status["published_segment_count"],
        "development_membership_count": status["development_membership_count"],
        "pending_processing_count": status["pending_processing_count"],
        "pending_processing_segments": list(pending_segments),
        "processing_incomplete_count": status["processing_incomplete_count"],
        "processing_incomplete_segments": list(incomplete_segments),
        "source_segment_binding_count": len(public_bindings),
        "source_segment_bindings": public_bindings,
        "feature_caches": cache_meta,
        "horizon_support": support_meta,
        "model_fitted": False,
        "new_threshold_selected": False,
        "new_horizon_selected": False,
        "fresh_registered_test_evidence": False,
        "current_task027_repurposed_as_selection": False,
        "old_confirmation_status": "UNOPENED_AND_EXCLUDED",
        "planning_estimates_are_not_acceptance_criteria": True,
        "coverage_is_descriptive_not_optional_stopping": True,
        "actual_project_account_fee": "UNKNOWN",
        "latency": "UNKNOWN",
        "realized_own_order_slippage_impact": "UNKNOWN",
        "funding_boundaries": "UNKNOWN",
        "maker_economics": "UNKNOWN",
    }
    report_bytes = _canonical_bytes(report)
    report_path = output / "development-closeout-report.json"
    _write_immutable(report_path, report_bytes)
    return {
        "report_path": str(report_path),
        "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "cache_50s_sha256": cast(dict[str, object], cache_meta["50"])["sha256"],
        "cache_300s_sha256": cast(dict[str, object], cache_meta["300"])["sha256"],
        "report": report,
    }


def _bound_segments(
    root: Path,
    *,
    protocol_sha256: str,
    started_wall_ns: int,
    deadline_wall_ns: int,
) -> tuple[tuple[Path, dict[str, object]], ...]:
    result: list[tuple[Path, dict[str, object]]] = []
    for segment_root in sorted(root.glob("segment-*")):
        membership_path = segment_root / "development-membership.json"
        evidence_path = segment_root / "segment-evidence.json"
        if not membership_path.is_file() or not evidence_path.is_file():
            continue

        membership_raw = membership_path.read_bytes()
        membership = _json_object(membership_raw, membership_path.name)
        evidence_raw = evidence_path.read_bytes()
        evidence = _json_object(evidence_raw, evidence_path.name)
        evidence_sha = hashlib.sha256(evidence_raw).hexdigest()
        if membership.get("protocol_sha256") != protocol_sha256:
            raise DevelopmentCloseoutError("membership protocol SHA-256 mismatch")
        if membership.get("segment_evidence_sha256") != evidence_sha:
            raise DevelopmentCloseoutError(
                f"membership evidence digest mismatch: {segment_root.name}"
            )
        if membership.get("evidence_role") != EVIDENCE_ROLE:
            raise DevelopmentCloseoutError("unexpected membership evidence role")
        if membership.get("old_confirmation_used") is not False:
            raise DevelopmentCloseoutError("membership claims old confirmation use")
        eligible = membership.get("eligible_decision_wall_ns")
        if not isinstance(eligible, dict):
            raise DevelopmentCloseoutError("membership eligibility interval missing")
        if eligible.get("start_inclusive") != started_wall_ns:
            raise DevelopmentCloseoutError("membership start boundary mismatch")
        if eligible.get("end_exclusive") != deadline_wall_ns:
            raise DevelopmentCloseoutError("membership end boundary mismatch")

        segment = evidence.get("segment")
        if not isinstance(segment, dict):
            raise DevelopmentCloseoutError("segment metadata missing")
        run_id = evidence.get("run_id")
        segment_id = segment.get("segment_id")
        manifest_sha = evidence.get("dataset_manifest_sha256")
        if not isinstance(run_id, str) or not run_id:
            raise DevelopmentCloseoutError("run_id missing")
        if not isinstance(segment_id, str) or not segment_id:
            raise DevelopmentCloseoutError("segment_id missing")
        if membership.get("run_id") != run_id:
            raise DevelopmentCloseoutError("membership run_id mismatch")
        if membership.get("segment_id") != segment_id:
            raise DevelopmentCloseoutError("membership segment_id mismatch")
        if not _is_sha256(manifest_sha):
            raise DevelopmentCloseoutError("dataset manifest SHA-256 invalid")

        result.append(
            (
                segment_root,
                {
                    "run_id": run_id,
                    "segment_id": segment_id,
                    "segment": cast(dict[str, object], segment),
                    "dataset_manifest_sha256": manifest_sha,
                    "segment_evidence_sha256": evidence_sha,
                    "development_membership_sha256": hashlib.sha256(membership_raw).hexdigest(),
                },
            )
        )
    return tuple(result)


def _missing_feature_counts(
    rows: tuple[MicrostructureRow, ...],
) -> dict[str, int]:
    counts = {name: 0 for name in FEATURE_NAMES}
    for row in rows:
        values = (
            row.base.hl_bbo_imbalance,
            row.hl_depth_imbalance_top5,
            row.hl_aggressive_trade_flow_5s,
            row.binance_aggressive_trade_flow_5s,
            row.hl_mid_return_5s_bps,
            row.base.binance_mid_return_5s_bps,
            row.cross_venue_return_gap_5s_bps,
            row.base.hl_spread_bps,
        )
        for name, value in zip(FEATURE_NAMES, values, strict=True):
            if value is None:
                counts[name] += 1
    return counts


def _union_ns(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    ordered = sorted(intervals)
    start, end = ordered[0]
    total = 0
    for next_start, next_end in ordered[1:]:
        if next_start <= end:
            end = max(end, next_end)
            continue
        total += end - start
        start, end = next_start, next_end
    return total + end - start


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode()


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise DevelopmentCloseoutError(f"existing immutable closeout output differs: {path}")
        return
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
    except OSError as exc:
        raise DevelopmentCloseoutError(f"cannot write closeout output: {path}") from exc


def _json_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DevelopmentCloseoutError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise DevelopmentCloseoutError(f"{label} root must be an object")
    return cast(dict[str, object], value)


def _required_int(item: dict[str, object], field: str) -> int:
    value = item.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise DevelopmentCloseoutError(f"{field} must be an integer")
    return value


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )