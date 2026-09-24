from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

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
from cryptobot.runtime.public_recorder import (
    RuntimeIdentity,
    derive_runtime_identity,
)


class FrontierSegmentError(RuntimeError):
    """Raised when a bounded public evidence segment cannot be accepted."""


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
        return json.dumps(
            self.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
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
    runtime_identity = identity or derive_runtime_identity()
    if run_duration_seconds <= 0:
        raise FrontierSegmentError("run_duration_seconds must be positive")
    if fee_scenario_bps_per_side < 0:
        raise FrontierSegmentError("fee_scenario_bps_per_side must be non-negative")

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

    recorder_summary = await run_dual_source_recorder(
        config,
        identity=runtime_identity,
    )
    recorder_summary_bytes = _json_bytes(recorder_summary.as_dict())
    _write_new(segment_root / "recorder-summary.json", recorder_summary_bytes)

    if recorder_summary.exit_code != 0:
        raise FrontierSegmentError(
            f"dual-source recorder failed with exit_code={recorder_summary.exit_code}"
        )
    if recorder_summary.recorder.final_path is None:
        raise FrontierSegmentError("successful recorder summary has no final raw path")
    if recorder_summary.recorder.segment_id is None:
        raise FrontierSegmentError("successful recorder summary has no raw segment_id")

    raw_segment_id = recorder_summary.recorder.segment_id
    frames = tuple(
        iter_raw_frames(
            recorder_summary.recorder.final_path,
            raw_segment_id,
        )
    )
    if not frames:
        raise FrontierSegmentError("sealed raw segment contains no frames")

    registry = load_instrument_registry(registry_path)
    normalized = normalize_frames(frames, registry)
    errors = tuple(result for result in normalized if result.outcome is FrameOutcome.ERROR)
    pipeline_report = build_pipeline_report(normalized)
    pipeline_report_bytes = serialize_pipeline_report(pipeline_report)
    _write_new(segment_root / "normalization-report.json", pipeline_report_bytes)

    if errors:
        raise FrontierSegmentError(f"normalization produced {len(errors)} target/source errors")
    if pipeline_report.total_raw_frames != len(frames):
        raise FrontierSegmentError("pipeline raw-frame count does not match sealed QCR1")
    if pipeline_report.causal_domain_count != 1:
        raise FrontierSegmentError(
            "bounded evidence segment must remain in one host/boot causal domain"
        )

    dataset_dir = segment_root / "dataset"
    materialized = materialize_research_dataset(normalized, dataset_dir)
    loaded = load_campaign_segment(
        materialized.output_dir,
        segment_id=raw_segment_id,
    )

    frontier_audit = analyze_frontier_pilot_dataset(
        materialized.output_dir,
        fee_scenario_bps_per_side=fee_scenario_bps_per_side,
    )
    frontier_audit_bytes = frontier_audit.to_json_bytes()
    _write_new(segment_root / "frontier-audit.json", frontier_audit_bytes)

    evidence_payload = {
        "schema_version": 1,
        "campaign_segment_version": "frontier-segment-v1",
        "run_id": runtime_identity.run_id,
        "segment": loaded.data.evidence.as_dict(),
        "dataset_manifest_sha256": loaded.manifest_sha256,
        "recorder_summary_sha256": hashlib.sha256(recorder_summary_bytes).hexdigest(),
        "normalization_report_sha256": hashlib.sha256(pipeline_report_bytes).hexdigest(),
        "frontier_audit_sha256": hashlib.sha256(frontier_audit_bytes).hexdigest(),
        "frontier_audit_status": frontier_audit.status,
        "fee_scenario_bps_per_side": format(fee_scenario_bps_per_side, "f"),
        "acceptance": {
            "recorder_exit_code": recorder_summary.exit_code,
            "normalization_error_count": len(errors),
            "dataset_bundle_verified": True,
            "table_hashes_verified": True,
            "single_causal_domain": True,
            "public_only": True,
        },
    }
    evidence_bytes = _json_bytes(evidence_payload)
    evidence_path = segment_root / "segment-evidence.json"
    _write_new(evidence_path, evidence_bytes)

    return FrontierSegmentRunResult(
        run_id=runtime_identity.run_id,
        segment_id=raw_segment_id,
        segment_root=str(segment_root),
        raw_frame_count=pipeline_report.total_raw_frames,
        normalized_event_count=pipeline_report.normalized_record_count,
        dataset_bundle_sha256=materialized.manifest.bundle_sha256,
        segment_evidence_sha256=hashlib.sha256(evidence_bytes).hexdigest(),
        dataset_manifest_sha256=loaded.manifest_sha256,
        frontier_audit_status=frontier_audit.status,
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
