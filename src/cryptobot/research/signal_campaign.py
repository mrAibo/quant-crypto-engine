from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq

from cryptobot.data.events import QualityFlag
from cryptobot.data.instruments import InstrumentRole
from cryptobot.data.numeric import parse_exact_decimal
from cryptobot.research.campaign_dataset import (
    load_campaign_segment,
    release_unused_arrow_memory,
)
from cryptobot.research.signal_dataset import (
    TopOfBookFeatureObservation,
    build_signal_feature_rows,
)
from cryptobot.research.signal_protocol import (
    HORIZON_NS,
    MAX_EXECUTION_STEP_NS,
    SignalFeatureRow,
    Stage2FeatureDataset,
)
from cryptobot.sim import QuoteObservation, build_fixed_horizon_opportunities

type _ReadTableFn = Callable[..., pa.Table]
_READ_TABLE = cast(_ReadTableFn, pq.read_table)


class SignalCampaignValidationError(ValueError):
    """Raised when frozen campaign evidence cannot support Stage-2 dataset build."""


@dataclass(frozen=True, slots=True)
class GateDatasetSource:
    gate_report_sha256: str
    campaign_manifest_sha256: str
    segment_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.gate_report_sha256, "gate_report_sha256")
        _require_sha256(self.campaign_manifest_sha256, "campaign_manifest_sha256")
        if not self.segment_ids:
            raise SignalCampaignValidationError("gate source must contain segments")
        if len(set(self.segment_ids)) != len(self.segment_ids):
            raise SignalCampaignValidationError("gate segment_ids must be unique")
        if any(not item.strip() for item in self.segment_ids):
            raise SignalCampaignValidationError("gate segment_ids must be non-empty")


def load_gate_dataset_source(
    report_path: str | Path,
    *,
    expected_report_sha256: str,
) -> GateDatasetSource:
    path = Path(report_path)
    raw = _read_bytes(path)
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_report_sha256:
        raise SignalCampaignValidationError("gate report SHA-256 does not match frozen value")

    report = _parse_object(raw, "gate report")
    if report.get("gate_decision") != "PASS_FEASIBILITY":
        raise SignalCampaignValidationError("gate report is not PASS_FEASIBILITY")
    if report.get("readiness") != "READY_FOR_FRONTIER_ADJUDICATION":
        raise SignalCampaignValidationError("gate report is not ready for adjudication")
    if report.get("adjudication_window_count") != 2952:
        raise SignalCampaignValidationError("gate report adjudication sample is not frozen 2952")

    audits = report.get("segment_audits")
    if not isinstance(audits, list) or not audits:
        raise SignalCampaignValidationError("gate report segment_audits must be non-empty")
    segment_ids: list[str] = []
    for item in audits:
        if not isinstance(item, dict):
            raise SignalCampaignValidationError("gate segment audit must be an object")
        segment_id = item.get("segment_id")
        if not isinstance(segment_id, str) or not segment_id.strip():
            raise SignalCampaignValidationError("gate segment_id must be non-empty")
        segment_ids.append(segment_id)

    manifest_sha = report.get("campaign_manifest_sha256")
    if not isinstance(manifest_sha, str):
        raise SignalCampaignValidationError("campaign_manifest_sha256 must be a string")
    return GateDatasetSource(
        gate_report_sha256=actual_sha,
        campaign_manifest_sha256=manifest_sha,
        segment_ids=tuple(segment_ids),
    )


def build_gate_feature_dataset(
    *,
    campaign_root: str | Path,
    gate_report_path: str | Path,
    expected_gate_report_sha256: str,
    instrument_id: str,
    reference_instrument_id: str,
    role: InstrumentRole,
) -> Stage2FeatureDataset:
    root = Path(campaign_root)
    source = load_gate_dataset_source(
        gate_report_path,
        expected_report_sha256=expected_gate_report_sha256,
    )
    segment_roots = _discover_segment_roots(root)

    rows: list[SignalFeatureRow] = []
    segment_digests: list[tuple[str, str]] = []
    for segment_id in source.segment_ids:
        segment_root = segment_roots.get(segment_id)
        if segment_root is None:
            raise SignalCampaignValidationError(
                f"frozen gate segment is missing locally: {segment_id}"
            )
        dataset_root = segment_root / "dataset"
        verified = load_campaign_segment(dataset_root, segment_id=segment_id)
        primary_books, reference_books = load_segment_books(
            dataset_root,
            primary_instrument_id=instrument_id,
            reference_instrument_id=reference_instrument_id,
        )
        quotes = tuple(
            QuoteObservation(
                event_id=item.event_id,
                source_id=item.source_id,
                instrument_id=item.instrument_id,
                role=role,
                host_id=item.host_id,
                boot_id=item.boot_id,
                recv_mono_ns=item.recv_mono_ns,
                recv_wall_ns=item.recv_wall_ns,
                bid_price=item.bid_price,
                ask_price=item.ask_price,
                quality_flags=item.quality_flags,
            )
            for item in primary_books
        )
        opportunities = build_fixed_horizon_opportunities(
            quotes,
            horizon_ns=HORIZON_NS,
            max_step_ns=MAX_EXECUTION_STEP_NS,
        )
        rows.extend(
            build_signal_feature_rows(
                segment_id=segment_id,
                opportunities=opportunities,
                primary_books=primary_books,
                reference_books=reference_books,
                reference_instrument_id=reference_instrument_id,
            )
        )
        segment_digests.append((segment_id, verified.data.evidence.dataset_bundle_sha256))
        del verified, primary_books, reference_books, quotes, opportunities
        release_unused_arrow_memory()

    ordered_rows = tuple(
        sorted(
            rows,
            key=lambda item: (
                item.decision_recv_wall_ns,
                item.decision_recv_mono_ns,
                item.row_id,
            ),
        )
    )
    return Stage2FeatureDataset(
        source_gate_report_sha256=source.gate_report_sha256,
        source_campaign_manifest_sha256=source.campaign_manifest_sha256,
        source_segment_digests=tuple(segment_digests),
        rows=ordered_rows,
    )


def load_segment_books(
    dataset_root: str | Path,
    *,
    primary_instrument_id: str,
    reference_instrument_id: str,
) -> tuple[
    tuple[TopOfBookFeatureObservation, ...],
    tuple[TopOfBookFeatureObservation, ...],
]:
    root = Path(dataset_root)
    primary_meta = _load_event_metadata(
        root / "events.parquet",
        event_type="BBO",
        instrument_id=primary_instrument_id,
    )
    reference_meta = _load_event_metadata(
        root / "events.parquet",
        event_type="REFERENCE_BBO",
        instrument_id=reference_instrument_id,
    )
    primary = _load_payload_books(
        root / "bbo.parquet",
        metadata=primary_meta,
    )
    reference = _load_payload_books(
        root / "reference_bbo.parquet",
        metadata=reference_meta,
    )
    return primary, reference


def write_frozen_feature_dataset(
    dataset: Stage2FeatureDataset,
    path: str | Path,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dataset.to_json_bytes()
    try:
        with target.open("xb") as stream:
            stream.write(payload)
            stream.flush()
    except FileExistsError:
        if target.read_bytes() != payload:
            raise SignalCampaignValidationError(
                "existing Stage-2 feature dataset differs from deterministic output"
            ) from None
    return target


def _load_event_metadata(
    path: Path,
    *,
    event_type: str,
    instrument_id: str,
) -> dict[str, tuple[str, str, str, str, int, int, int]]:
    try:
        table = _READ_TABLE(
            path,
            columns=[
                "event_id",
                "source_id",
                "instrument_id",
                "host_id",
                "boot_id",
                "recv_mono_ns",
                "recv_wall_ns",
                "quality_flags",
            ],
            filters=[
                ("event_type", "=", event_type),
                ("instrument_id", "=", instrument_id),
            ],
            use_threads=False,
        )
    except Exception as exc:
        raise SignalCampaignValidationError(
            f"cannot read Stage-2 event metadata: {path.name}"
        ) from exc

    output: dict[str, tuple[str, str, str, str, int, int, int]] = {}
    for raw in table.to_pylist():
        row = cast(dict[str, object], raw)
        event_id = _row_str(row, "event_id")
        if event_id in output:
            raise SignalCampaignValidationError("duplicate event_id in event metadata")
        output[event_id] = (
            _row_str(row, "source_id"),
            _row_str(row, "instrument_id"),
            _row_str(row, "host_id"),
            _row_str(row, "boot_id"),
            _row_int(row, "recv_mono_ns"),
            _row_int(row, "recv_wall_ns"),
            _row_int(row, "quality_flags"),
        )
    return output


def _load_payload_books(
    path: Path,
    *,
    metadata: dict[str, tuple[str, str, str, str, int, int, int]],
) -> tuple[TopOfBookFeatureObservation, ...]:
    if not metadata:
        return ()
    event_ids = tuple(metadata)
    try:
        table = _READ_TABLE(
            path,
            columns=[
                "event_id",
                "bid_price_exact",
                "bid_size_exact",
                "ask_price_exact",
                "ask_size_exact",
            ],
            filters=[("event_id", "in", event_ids)],
            use_threads=False,
        )
    except Exception as exc:
        raise SignalCampaignValidationError(
            f"cannot read Stage-2 BBO payloads: {path.name}"
        ) from exc

    books: list[TopOfBookFeatureObservation] = []
    seen: set[str] = set()
    for raw in table.to_pylist():
        row = cast(dict[str, object], raw)
        event_id = _row_str(row, "event_id")
        meta = metadata.get(event_id)
        if meta is None:
            continue
        if event_id in seen:
            raise SignalCampaignValidationError("duplicate BBO payload event_id")
        seen.add(event_id)
        source_id, instrument_id, host_id, boot_id, mono, wall, flags = meta
        books.append(
            TopOfBookFeatureObservation(
                event_id=event_id,
                source_id=source_id,
                instrument_id=instrument_id,
                host_id=host_id,
                boot_id=boot_id,
                recv_mono_ns=mono,
                recv_wall_ns=wall,
                bid_price=_row_optional_decimal(row, "bid_price_exact"),
                bid_size=_row_optional_decimal(row, "bid_size_exact"),
                ask_price=_row_optional_decimal(row, "ask_price_exact"),
                ask_size=_row_optional_decimal(row, "ask_size_exact"),
                quality_flags=QualityFlag(flags),
            )
        )
    if seen != set(metadata):
        missing = len(set(metadata) - seen)
        raise SignalCampaignValidationError(
            f"BBO payload table is missing {missing} selected event IDs"
        )
    return tuple(
        sorted(
            books,
            key=lambda item: (
                item.recv_mono_ns,
                item.recv_wall_ns,
                item.event_id,
            ),
        )
    )


def _discover_segment_roots(root: Path) -> dict[str, Path]:
    output: dict[str, Path] = {}
    for child in sorted(root.glob("segment-*"), key=lambda item: item.name):
        evidence_path = child / "segment-evidence.json"
        if not evidence_path.is_file():
            continue
        evidence = _parse_object(_read_bytes(evidence_path), "segment evidence")
        segment = evidence.get("segment")
        if not isinstance(segment, dict):
            raise SignalCampaignValidationError("segment evidence segment must be object")
        segment_id = segment.get("segment_id")
        if not isinstance(segment_id, str) or not segment_id.strip():
            raise SignalCampaignValidationError("segment evidence segment_id is invalid")
        if segment_id in output:
            raise SignalCampaignValidationError("duplicate published segment_id")
        output[segment_id] = child
    return output


def _row_optional_decimal(
    row: dict[str, object],
    field: str,
) -> Decimal | None:
    value = row.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SignalCampaignValidationError(f"{field} must be string or null")
    return parse_exact_decimal(value)


def _row_str(row: dict[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise SignalCampaignValidationError(f"{field} must be a non-empty string")
    return value


def _row_int(row: dict[str, object], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SignalCampaignValidationError(f"{field} must be integer")
    return value


def _parse_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SignalCampaignValidationError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SignalCampaignValidationError(f"{label} root must be object")
    return cast(dict[str, object], value)


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SignalCampaignValidationError(f"cannot read file: {path}") from exc


def _require_sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise SignalCampaignValidationError(f"{field} must be 64 lowercase hex characters")
