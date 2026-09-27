from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import cast

from cryptobot.runtime.dual_source_recorder import (
    DualSourceRecorderConfig,
    load_dual_source_recorder_config,
)
from cryptobot.runtime.frontier_segment import (
    capture_frontier_evidence_segment_sync,
    process_next_frontier_captured_segment,
)
from cryptobot.runtime.public_recorder import RuntimeIdentity, derive_runtime_identity

PROTOCOL_VERSION = "stage2-task027-development-campaign-v1"
CAMPAIGN_ID = "btc-microstructure-development-72h-v1"
EVIDENCE_ROLE = "DEVELOPMENT_ONLY"
TASK026_DECISION_SHA256 = "4c90657accb99a0caff44336bbca091b887f99cd9caedada01fd15364b77b39b"
TASK025_REGISTRY_SHA256 = "d5024ce6cb16c0d3dcce5b65f3f62f6d577b971d3bda7c8342ab67aaa100b130"
RUNTIME_CONFIG_SHA256 = "8bf2a31ec634b475f1e3b559663bb35e16950c1c721ab73ddc5812cd6b1f03e1"
DURATION_SECONDS = 72 * 60 * 60
SEGMENT_SECONDS = 900
FEE_SCENARIO_BPS_PER_SIDE = Decimal("4.5")


class DevelopmentCampaignError(RuntimeError):
    """Raised when TASK-027 campaign state violates the frozen protocol."""


@dataclass(frozen=True, slots=True)
class DevelopmentCampaignProtocol:
    runtime_config_sha256: str = RUNTIME_CONFIG_SHA256
    duration_seconds: int = DURATION_SECONDS
    segment_seconds: int = SEGMENT_SECONDS

    def __post_init__(self) -> None:
        if self.runtime_config_sha256 != RUNTIME_CONFIG_SHA256:
            raise DevelopmentCampaignError("runtime config digest is frozen")
        if self.duration_seconds != DURATION_SECONDS:
            raise DevelopmentCampaignError("campaign duration is frozen at 72 hours")
        if self.segment_seconds != SEGMENT_SECONDS:
            raise DevelopmentCampaignError("segment duration is frozen at 900 seconds")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "protocol_version": PROTOCOL_VERSION,
            "campaign_id": CAMPAIGN_ID,
            "evidence_role": EVIDENCE_ROLE,
            "frozen_before_capture": True,
            "task026_decision_sha256": TASK026_DECISION_SHA256,
            "task025_registry_sha256": TASK025_REGISTRY_SHA256,
            "runtime_config_sha256": self.runtime_config_sha256,
            "duration_seconds": self.duration_seconds,
            "segment_seconds": self.segment_seconds,
            "horizons_seconds": [50, 300],
            "fee_scenario": {
                "bps_per_side": "4.5",
                "evidence_class": "SCENARIO",
            },
            "capture_transport": {
                "profile": "VALIDATED_STAGE0_DUAL_SOURCE_PUBLIC_SUPERSET",
                "hyperliquid_coins": ["BTC", "ETH"],
                "hyperliquid_channels": ["l2Book", "bbo", "trades", "activeAssetCtx"],
                "binance_symbols": ["BTCUSDT", "ETHUSDT"],
                "binance_channels": ["bookTicker", "aggTrade"],
                "extra_public_frames": "PRESERVE_RAW_BUT_EXCLUDE_FROM_TASK027_ELIGIBILITY",
            },
            "development_eligibility": {
                "primary_instrument": "hyperliquid.mainnet.perpetual.btc",
                "reference_instrument": "binance_usdm.reference.perpetual.btcusdt",
                "hyperliquid_channels": ["l2Book", "bbo", "trades"],
                "binance_channels": ["bookTicker", "aggTrade"],
                "feature_family": "TASK025_EIGHT_FEATURE_MICROSTRUCTURE_V1_UNCHANGED",
            },
            "stopping_rule": (
                "FIXED_72H_WALL_DURATION_FROM_FIRST_SUCCESSFUL_CAPTURE_ATTEMPT; "
                "NO_OUTCOME_DEPENDENT_EXTENSION_OR_EARLY_STOP"
            ),
            "old_confirmation": "UNOPENED_AND_EXCLUDED",
            "model_fitting_allowed": False,
            "fresh_registered_test_evidence": False,
            "private_account_access_required": False,
            "aws_requester_pays_required": False,
            "unknown_costs": [
                "actual_project_account_fee_tier",
                "latency",
                "realized_own_order_slippage_impact",
                "funding_boundaries",
                "maker_economics",
            ],
        }

    def to_json_bytes(self) -> bytes:
        return _json_bytes(self.as_dict())

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_json_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class CampaignStart:
    protocol_sha256: str
    first_run_id: str
    started_wall_ns: int
    deadline_wall_ns: int

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "state_version": "stage2-task027-campaign-start-v1",
            "protocol_sha256": self.protocol_sha256,
            "first_run_id": self.first_run_id,
            "started_wall_ns": self.started_wall_ns,
            "deadline_wall_ns": self.deadline_wall_ns,
        }


@dataclass(frozen=True, slots=True)
class CapturePlan:
    status: str
    duration_seconds: float
    remaining_seconds: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "remaining_seconds": self.remaining_seconds,
        }


@dataclass(frozen=True, slots=True)
class CaptureCycleResult:
    status: str
    run_id: str | None
    segment_root: str | None
    duration_seconds: float
    started_wall_ns: int | None
    deadline_wall_ns: int | None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "run_id": self.run_id,
            "segment_root": self.segment_root,
            "duration_seconds": self.duration_seconds,
            "started_wall_ns": self.started_wall_ns,
            "deadline_wall_ns": self.deadline_wall_ns,
        }


@dataclass(frozen=True, slots=True)
class ProcessCycleResult:
    status: str
    run_id: str | None
    segment_id: str | None
    segment_root: str | None
    development_membership_sha256: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "run_id": self.run_id,
            "segment_id": self.segment_id,
            "segment_root": self.segment_root,
            "development_membership_sha256": self.development_membership_sha256,
        }


def build_protocol() -> DevelopmentCampaignProtocol:
    return DevelopmentCampaignProtocol()


def write_protocol_artifact(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_immutable(target, build_protocol().to_json_bytes())
    return target


def load_protocol(path: str | Path) -> DevelopmentCampaignProtocol:
    target = Path(path)
    payload = _read_json_object(target)
    expected = build_protocol()
    if payload != expected.as_dict():
        raise DevelopmentCampaignError("TASK-027 protocol does not match the frozen contract")
    return expected


def initialize_campaign_root(
    campaign_root: str | Path,
    *,
    protocol_path: str | Path,
    runtime_config_path: str | Path,
) -> dict[str, str]:
    protocol_source = Path(protocol_path)
    protocol = load_protocol(protocol_source)
    protocol_bytes = _read_bytes(protocol_source)

    runtime_source = Path(runtime_config_path)
    runtime_bytes = _read_bytes(runtime_source)
    runtime_sha = hashlib.sha256(runtime_bytes).hexdigest()
    if runtime_sha != protocol.runtime_config_sha256:
        raise DevelopmentCampaignError("runtime config SHA-256 does not match frozen protocol")
    load_dual_source_recorder_config(runtime_source)

    root = Path(campaign_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "capture-attempts").mkdir(exist_ok=True)
    _write_immutable(root / "campaign-protocol.json", protocol_bytes)
    _write_immutable(root / "runtime-config.json", runtime_bytes)
    return {
        "campaign_root": str(root),
        "protocol_sha256": protocol.sha256,
        "runtime_config_sha256": runtime_sha,
    }


def load_campaign_root(
    campaign_root: str | Path,
) -> tuple[DevelopmentCampaignProtocol, DualSourceRecorderConfig]:
    root = Path(campaign_root)
    protocol = load_protocol(root / "campaign-protocol.json")
    runtime_path = root / "runtime-config.json"
    runtime_bytes = _read_bytes(runtime_path)
    if hashlib.sha256(runtime_bytes).hexdigest() != protocol.runtime_config_sha256:
        raise DevelopmentCampaignError("campaign runtime config digest changed")
    config = load_dual_source_recorder_config(runtime_path)
    return protocol, config


def plan_capture(
    protocol: DevelopmentCampaignProtocol,
    start: CampaignStart | None,
    *,
    now_wall_ns: int,
) -> CapturePlan:
    _require_nonnegative_int(now_wall_ns, "now_wall_ns")
    if start is not None and start.protocol_sha256 != protocol.sha256:
        raise DevelopmentCampaignError("capture plan protocol digest mismatch")
    if start is None:
        return CapturePlan(
            status="CAPTURE",
            duration_seconds=float(protocol.segment_seconds),
            remaining_seconds=None,
        )
    remaining_ns = start.deadline_wall_ns - now_wall_ns
    if remaining_ns <= 0:
        return CapturePlan(status="COMPLETE", duration_seconds=0.0, remaining_seconds=0.0)
    remaining_seconds = remaining_ns / 1_000_000_000
    return CapturePlan(
        status="CAPTURE",
        duration_seconds=min(float(protocol.segment_seconds), remaining_seconds),
        remaining_seconds=remaining_seconds,
    )


def load_campaign_start(campaign_root: str | Path) -> CampaignStart | None:
    path = Path(campaign_root) / "campaign-start.json"
    if not path.exists():
        return None
    payload = _read_json_object(path)
    if payload.get("state_version") != "stage2-task027-campaign-start-v1":
        raise DevelopmentCampaignError("unsupported TASK-027 campaign-start version")
    start = CampaignStart(
        protocol_sha256=_required_sha256(payload, "protocol_sha256"),
        first_run_id=_required_str(payload, "first_run_id"),
        started_wall_ns=_required_int(payload, "started_wall_ns"),
        deadline_wall_ns=_required_int(payload, "deadline_wall_ns"),
    )
    if start.deadline_wall_ns <= start.started_wall_ns:
        raise DevelopmentCampaignError("campaign deadline must follow start")
    return start


def record_capture_attempt(
    campaign_root: str | Path,
    *,
    protocol: DevelopmentCampaignProtocol,
    identity: RuntimeIdentity,
    started_wall_ns: int,
) -> Path:
    _require_nonnegative_int(started_wall_ns, "started_wall_ns")
    _require_safe_run_id(identity.run_id)
    payload = {
        "schema_version": 1,
        "attempt_version": "stage2-task027-capture-attempt-v1",
        "protocol_sha256": protocol.sha256,
        "run_id": identity.run_id,
        "host_id": identity.host_id,
        "boot_id": identity.boot_id,
        "started_wall_ns": started_wall_ns,
    }
    path = Path(campaign_root) / "capture-attempts" / f"attempt-{identity.run_id}.json"
    _write_immutable(path, _json_bytes(payload))
    return path


def recover_campaign_start(
    campaign_root: str | Path,
    *,
    protocol: DevelopmentCampaignProtocol,
) -> CampaignStart | None:
    root = Path(campaign_root)
    existing = load_campaign_start(root)
    if existing is not None:
        if existing.protocol_sha256 != protocol.sha256:
            raise DevelopmentCampaignError("campaign-start protocol digest mismatch")
        return existing

    candidates: list[tuple[int, str]] = []
    attempts_root = root / "capture-attempts"
    for path in sorted(attempts_root.glob("attempt-*.json")):
        payload = _read_json_object(path)
        if payload.get("attempt_version") != "stage2-task027-capture-attempt-v1":
            raise DevelopmentCampaignError("unsupported capture-attempt version")
        if _required_sha256(payload, "protocol_sha256") != protocol.sha256:
            raise DevelopmentCampaignError("capture-attempt protocol digest mismatch")
        run_id = _required_str(payload, "run_id")
        _require_safe_run_id(run_id)
        started_wall_ns = _required_int(payload, "started_wall_ns")
        if (root / f"segment-{run_id}" / "capture-ready.json").is_file():
            candidates.append((started_wall_ns, run_id))

    if not candidates:
        return None
    started_wall_ns, first_run_id = min(candidates)
    start = CampaignStart(
        protocol_sha256=protocol.sha256,
        first_run_id=first_run_id,
        started_wall_ns=started_wall_ns,
        deadline_wall_ns=started_wall_ns + protocol.duration_seconds * 1_000_000_000,
    )
    _write_immutable(root / "campaign-start.json", _json_bytes(start.as_dict()))
    return load_campaign_start(root)


def publish_campaign_complete(
    campaign_root: str | Path,
    *,
    protocol: DevelopmentCampaignProtocol,
    start: CampaignStart,
    observed_wall_ns: int,
) -> Path:
    _require_nonnegative_int(observed_wall_ns, "observed_wall_ns")
    if start.protocol_sha256 != protocol.sha256:
        raise DevelopmentCampaignError("campaign-complete protocol digest mismatch")
    if observed_wall_ns < start.deadline_wall_ns:
        raise DevelopmentCampaignError("campaign cannot complete before the fixed deadline")
    path = Path(campaign_root) / "campaign-complete.json"
    if path.exists():
        payload = _read_json_object(path)
        if _required_sha256(payload, "protocol_sha256") != protocol.sha256:
            raise DevelopmentCampaignError("campaign-complete protocol digest mismatch")
        if _required_int(payload, "deadline_wall_ns") != start.deadline_wall_ns:
            raise DevelopmentCampaignError("campaign-complete deadline mismatch")
        return path
    payload = {
        "schema_version": 1,
        "completion_version": "stage2-task027-campaign-complete-v1",
        "protocol_sha256": protocol.sha256,
        "started_wall_ns": start.started_wall_ns,
        "deadline_wall_ns": start.deadline_wall_ns,
        "observed_wall_ns": observed_wall_ns,
        "reason": "FIXED_DURATION_ELAPSED",
        "outcome_dependent": False,
    }
    _write_immutable(path, _json_bytes(payload))
    return path


def capture_development_segment_sync(
    campaign_root: str | Path,
    *,
    clock_ns: Callable[[], int] = time.time_ns,
    identity: RuntimeIdentity | None = None,
) -> CaptureCycleResult:
    protocol, config = load_campaign_root(campaign_root)
    start = recover_campaign_start(campaign_root, protocol=protocol)
    now_wall_ns = clock_ns()
    plan = plan_capture(protocol, start, now_wall_ns=now_wall_ns)
    if plan.status == "COMPLETE":
        if start is None:
            raise DevelopmentCampaignError("complete capture plan requires campaign start")
        publish_campaign_complete(
            campaign_root,
            protocol=protocol,
            start=start,
            observed_wall_ns=now_wall_ns,
        )
        return CaptureCycleResult(
            status="COMPLETE",
            run_id=None,
            segment_root=None,
            duration_seconds=0.0,
            started_wall_ns=start.started_wall_ns,
            deadline_wall_ns=start.deadline_wall_ns,
        )

    runtime_identity = identity or derive_runtime_identity(run_wall_ns=now_wall_ns)
    record_capture_attempt(
        campaign_root,
        protocol=protocol,
        identity=runtime_identity,
        started_wall_ns=now_wall_ns,
    )
    capture = capture_frontier_evidence_segment_sync(
        config,
        campaign_root=campaign_root,
        run_duration_seconds=plan.duration_seconds,
        identity=runtime_identity,
    )
    start = recover_campaign_start(campaign_root, protocol=protocol)
    if start is None:
        raise DevelopmentCampaignError("successful capture did not establish campaign start")

    observed_wall_ns = clock_ns()
    if observed_wall_ns >= start.deadline_wall_ns:
        publish_campaign_complete(
            campaign_root,
            protocol=protocol,
            start=start,
            observed_wall_ns=observed_wall_ns,
        )

    return CaptureCycleResult(
        status="CAPTURE_READY",
        run_id=capture.run_id,
        segment_root=capture.segment_root,
        duration_seconds=plan.duration_seconds,
        started_wall_ns=start.started_wall_ns,
        deadline_wall_ns=start.deadline_wall_ns,
    )


def bind_development_membership(
    segment_root: str | Path,
    *,
    protocol: DevelopmentCampaignProtocol,
    start: CampaignStart,
) -> tuple[Path, str]:
    root = Path(segment_root)
    evidence_path = root / "segment-evidence.json"
    evidence_bytes = _read_bytes(evidence_path)
    evidence_sha = hashlib.sha256(evidence_bytes).hexdigest()
    evidence = _decode_json_object(evidence_bytes, evidence_path)
    run_id = _required_str(evidence, "run_id")
    segment = _required_dict(evidence, "segment")
    segment_id = _required_str(segment, "segment_id")

    if start.protocol_sha256 != protocol.sha256:
        raise DevelopmentCampaignError("membership protocol digest mismatch")
    attempt_path = root.parent / "capture-attempts" / f"attempt-{run_id}.json"
    attempt = _read_json_object(attempt_path)
    if _required_sha256(attempt, "protocol_sha256") != protocol.sha256:
        raise DevelopmentCampaignError("capture-attempt protocol digest mismatch")
    attempt_started_wall_ns = _required_int(attempt, "started_wall_ns")
    if not start.started_wall_ns <= attempt_started_wall_ns < start.deadline_wall_ns:
        raise DevelopmentCampaignError("processed segment started outside campaign window")

    membership = {
        "schema_version": 1,
        "membership_version": "stage2-task027-development-membership-v1",
        "protocol_sha256": protocol.sha256,
        "evidence_role": EVIDENCE_ROLE,
        "run_id": run_id,
        "segment_id": segment_id,
        "segment_evidence_sha256": evidence_sha,
        "eligible_decision_wall_ns": {
            "start_inclusive": start.started_wall_ns,
            "end_exclusive": start.deadline_wall_ns,
        },
        "extra_capture_frames": "PRESERVED_BUT_NOT_TASK027_ELIGIBLE",
        "old_confirmation_used": False,
    }
    payload = _json_bytes(membership)
    path = root / "development-membership.json"
    _write_immutable(path, payload)
    return path, hashlib.sha256(payload).hexdigest()


def _discover_unbound_processed_segments(campaign_root: str | Path) -> tuple[Path, ...]:
    root = Path(campaign_root)
    result = []
    for path in root.iterdir():
        if not path.is_dir() or not path.name.startswith("segment-"):
            continue
        if not (path / "segment-evidence.json").is_file():
            continue
        if (path / "development-membership.json").exists():
            continue
        result.append(path)
    return tuple(sorted(result, key=lambda item: item.name))


def process_development_segment_sync(
    campaign_root: str | Path,
    *,
    registry_path: str | Path = "config/instruments.yaml",
) -> ProcessCycleResult:
    protocol, _ = load_campaign_root(campaign_root)
    start = recover_campaign_start(campaign_root, protocol=protocol)
    if start is None:
        return ProcessCycleResult(
            status="IDLE_NO_ACCEPTED_CAPTURE",
            run_id=None,
            segment_id=None,
            segment_root=None,
            development_membership_sha256=None,
        )

    unbound = _discover_unbound_processed_segments(campaign_root)
    if unbound:
        segment_root = unbound[0]
        evidence = _read_json_object(segment_root / "segment-evidence.json")
        run_id = _required_str(evidence, "run_id")
        segment_id = _required_str(_required_dict(evidence, "segment"), "segment_id")
        _, membership_sha = bind_development_membership(
            segment_root,
            protocol=protocol,
            start=start,
        )
        return ProcessCycleResult(
            status="BOUND_RECOVERED",
            run_id=run_id,
            segment_id=segment_id,
            segment_root=str(segment_root),
            development_membership_sha256=membership_sha,
        )

    processed = process_next_frontier_captured_segment(
        campaign_root,
        fee_scenario_bps_per_side=FEE_SCENARIO_BPS_PER_SIDE,
        registry_path=registry_path,
    )
    if processed is None:
        return ProcessCycleResult(
            status="IDLE",
            run_id=None,
            segment_id=None,
            segment_root=None,
            development_membership_sha256=None,
        )

    _, membership_sha = bind_development_membership(
        processed.segment_root,
        protocol=protocol,
        start=start,
    )
    return ProcessCycleResult(
        status="PUBLISHED",
        run_id=processed.run_id,
        segment_id=processed.segment_id,
        segment_root=processed.segment_root,
        development_membership_sha256=membership_sha,
    )


def development_campaign_status(campaign_root: str | Path) -> dict[str, object]:
    root = Path(campaign_root)
    protocol, _ = load_campaign_root(root)
    start = recover_campaign_start(root, protocol=protocol)

    attempts = tuple(sorted((root / "capture-attempts").glob("attempt-*.json")))
    segment_dirs = tuple(
        sorted(
            path for path in root.iterdir() if path.is_dir() and path.name.startswith("segment-")
        )
    )
    capture_ready = tuple(path for path in segment_dirs if (path / "capture-ready.json").is_file())
    published = tuple(path for path in segment_dirs if (path / "segment-evidence.json").is_file())
    memberships = tuple(
        path for path in segment_dirs if (path / "development-membership.json").is_file()
    )
    processing_incomplete = tuple(
        path
        for path in segment_dirs
        if (path / "processing-started.json").is_file()
        and not (path / "segment-evidence.json").is_file()
    )
    pending = tuple(
        path
        for path in segment_dirs
        if (path / "capture-ready.json").is_file()
        and not (path / "processing-started.json").exists()
        and not (path / "segment-evidence.json").exists()
    )

    complete_path = root / "campaign-complete.json"
    state = "PRESTART"
    if start is not None:
        state = "COMPLETE" if complete_path.is_file() else "COLLECTING"

    return {
        "schema_version": 1,
        "status_version": "stage2-task027-campaign-status-v1",
        "campaign_id": CAMPAIGN_ID,
        "evidence_role": EVIDENCE_ROLE,
        "protocol_sha256": protocol.sha256,
        "campaign_state": state,
        "started_wall_ns": None if start is None else start.started_wall_ns,
        "deadline_wall_ns": None if start is None else start.deadline_wall_ns,
        "capture_attempt_count": len(attempts),
        "segment_directory_count": len(segment_dirs),
        "capture_ready_count": len(capture_ready),
        "published_segment_count": len(published),
        "development_membership_count": len(memberships),
        "pending_processing_count": len(pending),
        "processing_incomplete_count": len(processing_incomplete),
        "completion_marker_present": complete_path.is_file(),
        "old_confirmation_status": "UNOPENED_AND_EXCLUDED",
        "model_fitted": False,
        "fresh_registered_test_evidence": False,
    }


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise DevelopmentCampaignError(f"cannot read TASK-027 evidence file: {path}") from exc


def _decode_json_object(raw: bytes, path: Path) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DevelopmentCampaignError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DevelopmentCampaignError(f"JSON root must be object: {path}")
    return cast(dict[str, object], value)


def _read_json_object(path: Path) -> dict[str, object]:
    return _decode_json_object(_read_bytes(path), path)


def _write_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
    except FileExistsError:
        if _read_bytes(path) != payload:
            raise DevelopmentCampaignError(
                f"existing immutable TASK-027 evidence differs: {path}"
            ) from None


def _json_bytes(value: dict[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode()


def _required_str(value: dict[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise DevelopmentCampaignError(f"{field} must be a non-empty string")
    return item


def _required_int(value: dict[str, object], field: str) -> int:
    item = value.get(field)
    if isinstance(item, bool) or not isinstance(item, int):
        raise DevelopmentCampaignError(f"{field} must be an integer")
    return item


def _required_sha256(value: dict[str, object], field: str) -> str:
    item = _required_str(value, field)
    if len(item) != 64 or any(char not in "0123456789abcdef" for char in item):
        raise DevelopmentCampaignError(f"{field} must be 64 lowercase hex characters")
    return item


def _required_dict(value: dict[str, object], field: str) -> dict[str, object]:
    item = value.get(field)
    if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
        raise DevelopmentCampaignError(f"{field} must be an object")
    return cast(dict[str, object], item)


def _require_nonnegative_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DevelopmentCampaignError(f"{field} must be a non-negative integer")


def _require_safe_run_id(value: str) -> None:
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or not value.startswith("run-")
    ):
        raise DevelopmentCampaignError("run_id is not safe for campaign storage")
