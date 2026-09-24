from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import cast

from cryptobot.data.instruments import load_instrument_registry
from cryptobot.data.materialize import materialize_research_dataset
from cryptobot.data.normalization_pipeline import (
    FrameOutcome,
    build_pipeline_report,
    normalize_frames,
    serialize_pipeline_report,
)
from cryptobot.data.rawlog import iter_raw_frames
from cryptobot.research.campaign_dataset import load_campaign_segment
from cryptobot.research.frontier_dataset import analyze_frontier_pilot_dataset
from cryptobot.runtime.dual_source_recorder import (
    DualSourceRecorderConfig,
    run_dual_source_recorder,
)
from cryptobot.runtime.public_recorder import RuntimeIdentity, derive_runtime_identity

_CAPTURE_READY_FILENAME = "capture-ready.json"
_PROCESSING_STARTED_FILENAME = "processing-started.json"
_SEGMENT_EVIDENCE_FILENAME = "segment-evidence.json"


class FrontierSegmentError(RuntimeError):
    """Raised when a bounded public evidence segment cannot be accepted."""


@dataclass(frozen=True, slots=True)
class FrontierCaptureResult:
    run_id: str
    segment_id: str
    segment_root: str
    raw_frame_count: int
    recorder_summary_sha256: str
    raw_manifest_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "CAPTURE_READY",
            "run_id": self.run_id,
            "segment_id": self.segment_id,
            "segment_root": self.segment_root,
            "raw_frame_count": self.raw_frame_count,
            "recorder_summary_sha256": self.recorder_summary_sha256,
            "raw_manifest_sha256": self.raw_manifest_sha256,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class FrontierSegmentRunResult:
    run_id: str
    segment_id: str
    segment_root: str
    raw_frame_count: int
    normalized_event_count: int
    dataset_bundle_sha256: str
    segment_evidence_sha256: str
    dataset_manifest_sha256: str
    frontier_audit_status: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "SUCCESS",
            "run_id": self.run_id,
            "segment_id": self.segment_id,
            "segment_root": self.segment_root,
            "raw_frame_count": self.raw_frame_count,
            "normalized_event_count": self.normalized_event_count,
            "dataset_bundle_sha256": self.dataset_bundle_sha256,
            "segment_evidence_sha256": self.segment_evidence_sha256,
            "dataset_manifest_sha256": self.dataset_manifest_sha256,
            "frontier_audit_status": self.frontier_audit_status,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


async def capture_frontier_evidence_segment(
    base_config: DualSourceRecorderConfig,
    *,
    campaign_root: str | Path,
    run_duration_seconds: float,
    identity: RuntimeIdentity | None = None,
) -> FrontierCaptureResult:
    runtime_identity = identity or derive_runtime_identity()
    if run_duration_seconds <= 0:
        raise FrontierSegmentError("run_duration_seconds must be positive")

    root = Path(campaign_root)
    segment_root = root / f"segment-{runtime_identity.run_id}"
    if segment_root.exists():
        raise FrontierSegmentError(f"refusing to reuse segment directory: {segment_root}")
    segment_root.mkdir(parents=True)

    raw_root = segment_root / "raw"
    config = replace(
        base_config,
        storage_root=raw_root,
        manifest_path=raw_root / "manifest.json",
        run_duration_seconds=run_duration_seconds,
    )

    recorder_summary = await run_dual_source_recorder(config, identity=runtime_identity)
    recorder_summary_bytes = _json_bytes(recorder_summary.as_dict())
    recorder_summary_path = segment_root / "recorder-summary.json"
    _write_new(recorder_summary_path, recorder_summary_bytes)

    if recorder_summary.exit_code != 0:
        raise FrontierSegmentError(
            f"dual-source recorder failed with exit_code={recorder_summary.exit_code}"
        )
    if recorder_summary.recorder.final_path is None:
        raise FrontierSegmentError("successful recorder summary has no final raw path")
    if recorder_summary.recorder.manifest_path is None:
        raise FrontierSegmentError("successful recorder summary has no raw manifest path")
    if recorder_summary.recorder.segment_id is None:
        raise FrontierSegmentError("successful recorder summary has no raw segment_id")

    raw_path = Path(recorder_summary.recorder.final_path)
    raw_manifest_path = Path(recorder_summary.recorder.manifest_path)
    raw_relative_path = _relative_path_inside(raw_path, segment_root, "raw segment")
    raw_manifest_relative_path = _relative_path_inside(
        raw_manifest_path,
        segment_root,
        "raw manifest",
    )
    raw_manifest_bytes = _read_bytes(raw_manifest_path)
    raw_frame_count = recorder_summary.recorder.counters.durable_frames
    if raw_frame_count <= 0:
        raise FrontierSegmentError("sealed raw segment contains no durable frames")

    capture_payload = {
        "schema_version": 1,
        "capture_version": "frontier-capture-v1",
        "run_id": runtime_identity.run_id,
        "segment_id": recorder_summary.recorder.segment_id,
        "raw_frame_count": raw_frame_count,
        "raw_relative_path": raw_relative_path,
        "raw_manifest_relative_path": raw_manifest_relative_path,
        "recorder_summary_sha256": hashlib.sha256(recorder_summary_bytes).hexdigest(),
        "raw_manifest_sha256": hashlib.sha256(raw_manifest_bytes).hexdigest(),
        "public_only": True,
    }
    capture_bytes = _json_bytes(capture_payload)
    _write_new(segment_root / _CAPTURE_READY_FILENAME, capture_bytes)

    return FrontierCaptureResult(
        run_id=runtime_identity.run_id,
        segment_id=recorder_summary.recorder.segment_id,
        segment_root=str(segment_root),
        raw_frame_count=raw_frame_count,
        recorder_summary_sha256=hashlib.sha256(recorder_summary_bytes).hexdigest(),
        raw_manifest_sha256=hashlib.sha256(raw_manifest_bytes).hexdigest(),
    )


def process_frontier_captured_segment(
    segment_root: str | Path,
    *,
    fee_scenario_bps_per_side: Decimal,
    registry_path: str | Path = "config/instruments.yaml",
) -> FrontierSegmentRunResult:
    if fee_scenario_bps_per_side < 0:
        raise FrontierSegmentError("fee_scenario_bps_per_side must be non-negative")

    root = Path(segment_root)
    if (root / _SEGMENT_EVIDENCE_FILENAME).exists():
        raise FrontierSegmentError(f"segment is already published: {root}")

    capture_path = root / _CAPTURE_READY_FILENAME
    capture_bytes = _read_bytes(capture_path)
    capture = _parse_capture_ready(capture_bytes)
    run_id = _required_str(capture, "run_id")
    if root.name != f"segment-{run_id}":
        raise FrontierSegmentError("segment directory name does not match capture run_id")
    segment_id = _required_str(capture, "segment_id")
    raw_frame_count = _required_int(capture, "raw_frame_count")
    if raw_frame_count <= 0:
        raise FrontierSegmentError("capture raw_frame_count must be positive")
    if capture.get("public_only") is not True:
        raise FrontierSegmentError("capture-ready evidence must be public-only")

    recorder_summary_bytes = _read_bytes(root / "recorder-summary.json")
    if hashlib.sha256(recorder_summary_bytes).hexdigest() != _required_sha256(
        capture,
        "recorder_summary_sha256",
    ):
        raise FrontierSegmentError("recorder-summary digest does not match capture-ready")

    raw_path = _safe_segment_path(root, _required_str(capture, "raw_relative_path"))
    raw_manifest_path = _safe_segment_path(
        root,
        _required_str(capture, "raw_manifest_relative_path"),
    )
    if hashlib.sha256(_read_bytes(raw_manifest_path)).hexdigest() != _required_sha256(
        capture,
        "raw_manifest_sha256",
    ):
        raise FrontierSegmentError("raw manifest digest does not match capture-ready")
    if not raw_path.is_file():
        raise FrontierSegmentError("captured raw segment is missing")

    registry = load_instrument_registry(registry_path)
    processing_payload = {
        "schema_version": 1,
        "processing_version": "frontier-processing-v1",
        "run_id": run_id,
        "segment_id": segment_id,
        "capture_ready_sha256": hashlib.sha256(capture_bytes).hexdigest(),
    }
    _write_new(root / _PROCESSING_STARTED_FILENAME, _json_bytes(processing_payload))

    frames = tuple(iter_raw_frames(raw_path, segment_id))
    if not frames:
        raise FrontierSegmentError("sealed raw segment contains no frames")
    if len(frames) != raw_frame_count:
        raise FrontierSegmentError("capture raw-frame count does not match sealed QCR1")

    normalized = normalize_frames(frames, registry)
    errors = tuple(result for result in normalized if result.outcome is FrameOutcome.ERROR)
    pipeline_report = build_pipeline_report(normalized)
    pipeline_report_bytes = serialize_pipeline_report(pipeline_report)
    _write_new(root / "normalization-report.json", pipeline_report_bytes)

    if errors:
        raise FrontierSegmentError(f"normalization produced {len(errors)} target/source errors")
    if pipeline_report.total_raw_frames != len(frames):
        raise FrontierSegmentError("pipeline raw-frame count does not match sealed QCR1")
    if pipeline_report.causal_domain_count != 1:
        raise FrontierSegmentError(
            "bounded evidence segment must remain in one host/boot causal domain"
        )

    dataset_dir = root / "dataset"
    materialized = materialize_research_dataset(normalized, dataset_dir)
    loaded = load_campaign_segment(materialized.output_dir, segment_id=segment_id)

    frontier_audit = analyze_frontier_pilot_dataset(
        materialized.output_dir,
        fee_scenario_bps_per_side=fee_scenario_bps_per_side,
    )
    frontier_audit_bytes = frontier_audit.to_json_bytes()
    _write_new(root / "frontier-audit.json", frontier_audit_bytes)

    evidence_payload = {
        "schema_version": 1,
        "campaign_segment_version": "frontier-segment-v1",
        "run_id": run_id,
        "segment": loaded.data.evidence.as_dict(),
        "dataset_manifest_sha256": loaded.manifest_sha256,
        "recorder_summary_sha256": hashlib.sha256(recorder_summary_bytes).hexdigest(),
        "normalization_report_sha256": hashlib.sha256(pipeline_report_bytes).hexdigest(),
        "frontier_audit_sha256": hashlib.sha256(frontier_audit_bytes).hexdigest(),
        "frontier_audit_status": frontier_audit.status,
        "fee_scenario_bps_per_side": format(fee_scenario_bps_per_side, "f"),
        "acceptance": {
            "recorder_exit_code": 0,
            "normalization_error_count": len(errors),
            "dataset_bundle_verified": True,
            "table_hashes_verified": True,
            "single_causal_domain": True,
            "public_only": True,
        },
    }
    evidence_bytes = _json_bytes(evidence_payload)
    _write_new(root / _SEGMENT_EVIDENCE_FILENAME, evidence_bytes)

    return FrontierSegmentRunResult(
        run_id=run_id,
        segment_id=segment_id,
        segment_root=str(root),
        raw_frame_count=pipeline_report.total_raw_frames,
        normalized_event_count=pipeline_report.normalized_record_count,
        dataset_bundle_sha256=materialized.manifest.bundle_sha256,
        segment_evidence_sha256=hashlib.sha256(evidence_bytes).hexdigest(),
        dataset_manifest_sha256=loaded.manifest_sha256,
        frontier_audit_status=frontier_audit.status,
    )


def discover_pending_captured_segments(campaign_root: str | Path) -> tuple[Path, ...]:
    root = Path(campaign_root)
    if not root.is_dir():
        raise FrontierSegmentError(f"campaign root does not exist: {root}")
    pending = []
    for path in root.iterdir():
        if not path.is_dir() or not path.name.startswith("segment-"):
            continue
        if not (path / _CAPTURE_READY_FILENAME).is_file():
            continue
        if (path / _SEGMENT_EVIDENCE_FILENAME).exists():
            continue
        if (path / _PROCESSING_STARTED_FILENAME).exists():
            continue
        pending.append(path)
    return tuple(sorted(pending, key=lambda item: item.name))


def process_next_frontier_captured_segment(
    campaign_root: str | Path,
    *,
    fee_scenario_bps_per_side: Decimal,
    registry_path: str | Path = "config/instruments.yaml",
) -> FrontierSegmentRunResult | None:
    pending = discover_pending_captured_segments(campaign_root)
    if not pending:
        return None
    return process_frontier_captured_segment(
        pending[0],
        fee_scenario_bps_per_side=fee_scenario_bps_per_side,
        registry_path=registry_path,
    )


async def run_frontier_evidence_segment(
    base_config: DualSourceRecorderConfig,
    *,
    campaign_root: str | Path,
    run_duration_seconds: float,
    fee_scenario_bps_per_side: Decimal,
    registry_path: str | Path = "config/instruments.yaml",
    identity: RuntimeIdentity | None = None,
) -> FrontierSegmentRunResult:
    if fee_scenario_bps_per_side < 0:
        raise FrontierSegmentError("fee_scenario_bps_per_side must be non-negative")
    capture = await capture_frontier_evidence_segment(
        base_config,
        campaign_root=campaign_root,
        run_duration_seconds=run_duration_seconds,
        identity=identity,
    )
    return process_frontier_captured_segment(
        capture.segment_root,
        fee_scenario_bps_per_side=fee_scenario_bps_per_side,
        registry_path=registry_path,
    )


def capture_frontier_evidence_segment_sync(
    base_config: DualSourceRecorderConfig,
    *,
    campaign_root: str | Path,
    run_duration_seconds: float,
    identity: RuntimeIdentity | None = None,
) -> FrontierCaptureResult:
    return asyncio.run(
        capture_frontier_evidence_segment(
            base_config,
            campaign_root=campaign_root,
            run_duration_seconds=run_duration_seconds,
            identity=identity,
        )
    )


def run_frontier_evidence_segment_sync(
    base_config: DualSourceRecorderConfig,
    *,
    campaign_root: str | Path,
    run_duration_seconds: float,
    fee_scenario_bps_per_side: Decimal,
    registry_path: str | Path = "config/instruments.yaml",
    identity: RuntimeIdentity | None = None,
) -> FrontierSegmentRunResult:
    return asyncio.run(
        run_frontier_evidence_segment(
            base_config,
            campaign_root=campaign_root,
            run_duration_seconds=run_duration_seconds,
            fee_scenario_bps_per_side=fee_scenario_bps_per_side,
            registry_path=registry_path,
            identity=identity,
        )
    )


def _parse_capture_ready(raw: bytes) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FrontierSegmentError("capture-ready is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise FrontierSegmentError("capture-ready root must be an object")
    result = cast(dict[str, object], value)
    if _required_int(result, "schema_version") != 1:
        raise FrontierSegmentError("unsupported capture-ready schema_version")
    if _required_str(result, "capture_version") != "frontier-capture-v1":
        raise FrontierSegmentError("unsupported capture_version")
    return result


def _safe_segment_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise FrontierSegmentError("capture-ready path must be relative")
    resolved_root = root.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise FrontierSegmentError("capture-ready path escapes segment root") from exc
    return resolved


def _relative_path_inside(path: Path, root: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise FrontierSegmentError(f"{label} path escapes segment root") from exc


def _required_str(value: dict[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise FrontierSegmentError(f"{field} must be a non-empty string")
    return item


def _required_int(value: dict[str, object], field: str) -> int:
    item = value.get(field)
    if isinstance(item, bool) or not isinstance(item, int):
        raise FrontierSegmentError(f"{field} must be an integer")
    return item


def _required_sha256(value: dict[str, object], field: str) -> str:
    item = _required_str(value, field)
    if len(item) != 64 or any(char not in "0123456789abcdef" for char in item):
        raise FrontierSegmentError(f"{field} must be 64 lowercase hex characters")
    return item


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise FrontierSegmentError(f"cannot read evidence file: {path}") from exc


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
    except FileExistsError as exc:
        raise FrontierSegmentError(f"refusing to overwrite published evidence: {path}") from exc


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