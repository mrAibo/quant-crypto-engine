from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import cast

from cryptobot.data.numeric import NumericValidationError, parse_exact_decimal
from cryptobot.research.campaign import (
    CampaignConfig,
    CampaignManifest,
    CampaignReport,
    CampaignValidationError,
    MovementWindow,
    SegmentData,
    SegmentEvidence,
    SegmentWindowAudit,
    adjudicate_windows,
    build_segment_windows,
)
from cryptobot.research.campaign_dataset import (
    load_campaign_segment,
    release_unused_arrow_memory,
)

_CONFIG_FILENAME = "campaign-config.json"
_SEGMENT_PREFIX = "segment-"
_SEGMENT_EVIDENCE_FILENAME = "segment-evidence.json"
_REPORTS_DIRNAME = "campaign-reports"


@dataclass(frozen=True, slots=True)
class PublishedSegment:
    root: Path
    data: SegmentData
    evidence_file_sha256: str


@dataclass(frozen=True, slots=True)
class CampaignDiscovery:
    config: CampaignConfig
    manifest: CampaignManifest
    segments: tuple[PublishedSegment, ...]
    incomplete_segment_directories: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CampaignReportDiscovery:
    config: CampaignConfig
    manifest: CampaignManifest
    segment_evidence: tuple[SegmentEvidence, ...]
    incomplete_segment_directories: tuple[str, ...]

    @property
    def segments(self) -> tuple[SegmentEvidence, ...]:
        return self.segment_evidence


@dataclass(frozen=True, slots=True)
class PublishedCampaignReport:
    discovery: CampaignReportDiscovery
    report: CampaignReport
    report_path: Path


def initialize_campaign_root(
    campaign_root: str | Path,
    config: CampaignConfig,
) -> Path:
    root = Path(campaign_root)
    root.mkdir(parents=True, exist_ok=True)
    existing_segments = tuple(
        child.name
        for child in root.iterdir()
        if child.is_dir() and child.name.startswith(_SEGMENT_PREFIX)
    )
    if existing_segments:
        raise CampaignValidationError(
            "cannot initialize campaign config after segment directories already exist"
        )
    path = root / _CONFIG_FILENAME
    payload = _canonical_json_bytes(
        {
            "schema_version": 1,
            "campaign_config": config.as_dict(),
        }
    )
    _write_new(path, payload)
    return path


def load_campaign_config(campaign_root: str | Path) -> CampaignConfig:
    path = Path(campaign_root) / _CONFIG_FILENAME
    raw = _load_object(path)
    if _required_int(raw, "schema_version") != 1:
        raise CampaignValidationError("unsupported campaign config schema_version")
    config_raw = raw.get("campaign_config")
    if not isinstance(config_raw, dict) or not all(isinstance(key, str) for key in config_raw):
        raise CampaignValidationError("campaign_config must be an object")
    config = cast(dict[str, object], config_raw)

    source_ids_raw = config.get("source_ids")
    if not isinstance(source_ids_raw, list) or not all(
        isinstance(item, str) and item.strip() for item in source_ids_raw
    ):
        raise CampaignValidationError("campaign source_ids must be an array of strings")

    return CampaignConfig(
        campaign_id=_required_str(config, "campaign_id"),
        fee_scenario_bps_per_side=_required_decimal(
            config,
            "fee_scenario_bps_per_side",
        ),
        target_horizon_seconds=_required_int(config, "target_horizon_seconds"),
        required_non_overlapping_windows=_required_int(
            config,
            "required_non_overlapping_windows",
        ),
        dkw_confidence=_required_decimal(config, "dkw_confidence"),
        dkw_maximum_cdf_error=_required_decimal(
            config,
            "dkw_maximum_cdf_error",
        ),
        source_ids=tuple(cast(list[str], source_ids_raw)),
        primary_instrument_id=_required_str(config, "primary_instrument_id"),
    )


def discover_campaign(campaign_root: str | Path) -> CampaignDiscovery:
    root = Path(campaign_root)
    config = load_campaign_config(root)
    published: list[PublishedSegment] = []
    incomplete: list[str] = []

    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or not child.name.startswith(_SEGMENT_PREFIX):
            continue
        evidence_path = child / _SEGMENT_EVIDENCE_FILENAME
        if not evidence_path.is_file():
            incomplete.append(child.name)
            continue
        published.append(_load_published_segment(child, config))
        release_unused_arrow_memory()

    data = tuple(item.data for item in published)
    manifest = CampaignManifest(
        config=config,
        segments=tuple(item.evidence for item in data),
    )
    ordered_published = tuple(
        sorted(
            published,
            key=lambda item: (
                item.data.evidence.wall_start_ns,
                item.data.evidence.wall_end_ns,
                item.data.evidence.segment_id,
            ),
        )
    )
    return CampaignDiscovery(
        config=config,
        manifest=manifest,
        segments=ordered_published,
        incomplete_segment_directories=tuple(sorted(incomplete)),
    )


def publish_campaign_report(
    campaign_root: str | Path,
) -> PublishedCampaignReport:
    root = Path(campaign_root)
    config = load_campaign_config(root)
    evidence: list[SegmentEvidence] = []
    windows: list[MovementWindow] = []
    audits: list[SegmentWindowAudit] = []
    incomplete: list[str] = []

    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or not child.name.startswith(_SEGMENT_PREFIX):
            continue
        evidence_path = child / _SEGMENT_EVIDENCE_FILENAME
        if not evidence_path.is_file():
            incomplete.append(child.name)
            continue

        published = _load_published_segment(child, config)
        segment_windows, audit = build_segment_windows(config, published.data)
        evidence.append(published.data.evidence)
        windows.extend(segment_windows)
        audits.append(audit)
        del published
        release_unused_arrow_memory()

    manifest = CampaignManifest(config=config, segments=tuple(evidence))
    ordered_windows = tuple(
        sorted(
            windows,
            key=lambda item: (
                item.start_recv_wall_ns,
                item.end_recv_wall_ns,
                item.segment_id,
                item.start_event_id,
            ),
        )
    )
    report = adjudicate_windows(
        manifest=manifest,
        windows=ordered_windows,
        segment_audits=tuple(audits),
    )

    reports_root = root / _REPORTS_DIRNAME
    reports_root.mkdir(parents=True, exist_ok=True)
    path = reports_root / f"{manifest.sha256}.json"
    payload = report.to_json_bytes()
    if path.exists():
        if path.read_bytes() != payload:
            raise CampaignValidationError(
                "existing campaign report revision does not match deterministic output"
            )
    else:
        _write_new(path, payload)

    discovery = CampaignReportDiscovery(
        config=config,
        manifest=manifest,
        segment_evidence=tuple(evidence),
        incomplete_segment_directories=tuple(sorted(incomplete)),
    )
    return PublishedCampaignReport(
        discovery=discovery,
        report=report,
        report_path=path,
    )


def _load_published_segment(
    root: Path,
    config: CampaignConfig,
) -> PublishedSegment:
    evidence_path = root / _SEGMENT_EVIDENCE_FILENAME
    evidence_bytes = _read_bytes(evidence_path)
    evidence_sha = hashlib.sha256(evidence_bytes).hexdigest()
    raw = _parse_object(evidence_bytes, _SEGMENT_EVIDENCE_FILENAME)

    if _required_int(raw, "schema_version") != 1:
        raise CampaignValidationError("unsupported segment evidence schema_version")
    if _required_str(raw, "campaign_segment_version") != "frontier-segment-v1":
        raise CampaignValidationError("unsupported campaign_segment_version")

    run_id = _required_str(raw, "run_id")
    if root.name != f"{_SEGMENT_PREFIX}{run_id}":
        raise CampaignValidationError("segment directory name does not match evidence run_id")

    segment_raw = raw.get("segment")
    if not isinstance(segment_raw, dict) or not all(isinstance(key, str) for key in segment_raw):
        raise CampaignValidationError("published segment evidence must contain segment object")
    segment_dict = cast(dict[str, object], segment_raw)
    segment_id = _required_str(segment_dict, "segment_id")

    loaded = load_campaign_segment(
        root / "dataset",
        segment_id=segment_id,
    )
    if loaded.data.evidence.as_dict() != segment_dict:
        raise CampaignValidationError(
            "published segment metadata does not match tamper-checked dataset"
        )
    if loaded.manifest_sha256 != _required_sha256(raw, "dataset_manifest_sha256"):
        raise CampaignValidationError(
            "published dataset_manifest_sha256 does not match dataset manifest"
        )

    _verify_file_digest(
        root / "recorder-summary.json",
        _required_sha256(raw, "recorder_summary_sha256"),
    )
    _verify_file_digest(
        root / "normalization-report.json",
        _required_sha256(raw, "normalization_report_sha256"),
    )
    _verify_file_digest(
        root / "frontier-audit.json",
        _required_sha256(raw, "frontier_audit_sha256"),
    )

    fee = _required_decimal(raw, "fee_scenario_bps_per_side")
    if fee != config.fee_scenario_bps_per_side:
        raise CampaignValidationError("segment fee scenario does not match frozen campaign config")

    acceptance_raw = raw.get("acceptance")
    if not isinstance(acceptance_raw, dict) or not all(
        isinstance(key, str) for key in acceptance_raw
    ):
        raise CampaignValidationError("segment acceptance must be an object")
    acceptance = cast(dict[str, object], acceptance_raw)
    required_acceptance = {
        "recorder_exit_code": 0,
        "normalization_error_count": 0,
        "dataset_bundle_verified": True,
        "table_hashes_verified": True,
        "single_causal_domain": True,
        "public_only": True,
    }
    if acceptance != required_acceptance:
        raise CampaignValidationError("segment acceptance contract is not satisfied")

    return PublishedSegment(
        root=root,
        data=loaded.data,
        evidence_file_sha256=evidence_sha,
    )


def _verify_file_digest(path: Path, expected: str) -> None:
    actual = hashlib.sha256(_read_bytes(path)).hexdigest()
    if actual != expected:
        raise CampaignValidationError(f"published evidence digest mismatch: {path.name}")


def _load_object(path: Path) -> dict[str, object]:
    return _parse_object(_read_bytes(path), path.name)


def _parse_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignValidationError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        raise CampaignValidationError(f"{label} root must be a string-keyed object")
    return cast(dict[str, object], decoded)


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise CampaignValidationError(f"cannot read campaign file: {path}") from exc


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
    except FileExistsError as exc:
        raise CampaignValidationError(f"refusing to overwrite campaign file: {path}") from exc


def _canonical_json_bytes(value: dict[str, object]) -> bytes:
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
        raise CampaignValidationError(f"{field} must be a non-empty string")
    return item


def _required_int(value: dict[str, object], field: str) -> int:
    item = value.get(field)
    if isinstance(item, bool) or not isinstance(item, int):
        raise CampaignValidationError(f"{field} must be an integer")
    return item


def _required_sha256(value: dict[str, object], field: str) -> str:
    item = _required_str(value, field)
    if len(item) != 64 or any(character not in "0123456789abcdef" for character in item):
        raise CampaignValidationError(f"{field} must be 64 lowercase hex characters")
    return item


def _required_decimal(value: dict[str, object], field: str) -> Decimal:
    item = value.get(field)
    if not isinstance(item, str):
        raise CampaignValidationError(f"{field} must be an exact decimal string")
    try:
        return parse_exact_decimal(item)
    except NumericValidationError as exc:
        raise CampaignValidationError(str(exc)) from exc