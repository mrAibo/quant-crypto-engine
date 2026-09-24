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
from cryptobot.data.materialize import (
    DATASET_SCHEMA_VERSION,
    MATERIALIZER_VERSION,
    dataset_schemas,
)
from cryptobot.data.normalization_pipeline import PIPELINE_VERSION
from cryptobot.data.numeric import NumericValidationError, parse_exact_decimal
from cryptobot.research.campaign import (
    CampaignValidationError,
    SegmentData,
    SegmentEvidence,
)
from cryptobot.research.frontier_dataset import PrimaryBBOObservation

_PRIMARY_SOURCE = "hyperliquid-mainnet-public"
_REFERENCE_SOURCE = "binance-usdm-reference-public"
_PRIMARY_INSTRUMENT = "hyperliquid.mainnet.perpetual.btc"
_REQUIRED_SOURCES = (_REFERENCE_SOURCE, _PRIMARY_SOURCE)

type _ReadTableFn = Callable[..., pa.Table]
_READ_TABLE = cast(_ReadTableFn, pq.read_table)


@dataclass(frozen=True, slots=True)
class LoadedCampaignSegment:
    data: SegmentData
    manifest_sha256: str

    def __post_init__(self) -> None:
        _require_sha256(self.manifest_sha256, "manifest_sha256")


def load_campaign_segment(
    dataset_dir: str | Path,
    *,
    segment_id: str,
) -> LoadedCampaignSegment:
    root = Path(dataset_dir)
    if not segment_id.strip():
        raise CampaignValidationError("segment_id must be non-empty")

    manifest_path = root / "manifest.json"
    manifest_bytes = _read_bytes(manifest_path)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = _parse_manifest(manifest_bytes)
    _validate_manifest_contract(root, manifest)

    frame_rows = _read_rows(
        root / "frames.parquet",
        columns=[
            "source_id",
            "host_id",
            "boot_id",
            "recv_wall_ns",
        ],
    )
    event_rows = _read_rows(
        root / "events.parquet",
        columns=[
            "event_id",
            "source_id",
            "instrument_id",
            "event_type",
            "host_id",
            "boot_id",
            "recv_mono_ns",
            "recv_wall_ns",
            "quality_flags",
        ],
    )

    raw_frame_count = _required_int(manifest, "raw_frame_count")
    normalized_event_count = _required_int(manifest, "normalized_event_count")
    if len(frame_rows) != raw_frame_count:
        raise CampaignValidationError(
            "frames.parquet row count does not match manifest raw_frame_count"
        )
    if len(event_rows) != normalized_event_count:
        raise CampaignValidationError(
            "events.parquet row count does not match manifest normalized_event_count"
        )
    if not frame_rows:
        raise CampaignValidationError("campaign segment dataset contains no raw frames")

    source_ids = tuple(sorted(_frame_source_ids(frame_rows)))
    if source_ids != _REQUIRED_SOURCES:
        raise CampaignValidationError(
            "campaign segment dataset does not contain exactly the frozen source set"
        )

    domains = tuple(sorted(_frame_domains(frame_rows)))
    wall_values = tuple(_frame_wall_ns(frame_rows))
    wall_start_ns = min(wall_values)
    wall_end_ns = max(wall_values)
    if wall_end_ns <= wall_start_ns:
        raise CampaignValidationError("campaign segment must span a positive receive-wall interval")

    primary_bbo = _load_primary_bbo(root, event_rows)
    primary_l2_count = _primary_l2_count(event_rows)

    evidence = SegmentEvidence(
        segment_id=segment_id,
        dataset_bundle_sha256=_required_sha256(manifest, "bundle_sha256"),
        normalized_records_sha256=_required_sha256(
            manifest,
            "source_normalized_records_sha256",
        ),
        dataset_schema_version=_required_int(manifest, "dataset_schema_version"),
        materializer_version=_required_str(manifest, "materializer_version"),
        raw_frame_count=raw_frame_count,
        normalized_event_count=normalized_event_count,
        source_ids=source_ids,
        causal_domains=domains,
        wall_start_ns=wall_start_ns,
        wall_end_ns=wall_end_ns,
        primary_bbo_count=len(primary_bbo),
        primary_l2_count=primary_l2_count,
    )
    return LoadedCampaignSegment(
        data=SegmentData(
            evidence=evidence,
            primary_bbo=primary_bbo,
        ),
        manifest_sha256=manifest_sha256,
    )


def _parse_manifest(raw: bytes) -> dict[str, object]:
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignValidationError("dataset manifest is not valid UTF-8 JSON") from exc
    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        raise CampaignValidationError("dataset manifest root must be a string-keyed object")
    return cast(dict[str, object], decoded)


def _validate_manifest_contract(
    root: Path,
    manifest: dict[str, object],
) -> None:
    if _required_int(manifest, "dataset_schema_version") != DATASET_SCHEMA_VERSION:
        raise CampaignValidationError("unsupported dataset_schema_version")
    if _required_str(manifest, "materializer_version") != MATERIALIZER_VERSION:
        raise CampaignValidationError("unsupported materializer_version")
    if _required_str(manifest, "source_pipeline_version") != PIPELINE_VERSION:
        raise CampaignValidationError("unsupported source_pipeline_version")
    if _required_str(manifest, "creation_semantics") != "DERIVED_REBUILDABLE":
        raise CampaignValidationError("dataset creation_semantics is invalid")
    if _required_str(manifest, "authority") != "QCR1_RAW_IS_AUTHORITATIVE":
        raise CampaignValidationError("dataset authority is invalid")

    tables_raw = manifest.get("tables")
    if not isinstance(tables_raw, list):
        raise CampaignValidationError("dataset manifest tables must be an array")
    tables: list[dict[str, object]] = []
    for item in tables_raw:
        if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
            raise CampaignValidationError("dataset manifest table entry must be an object")
        tables.append(cast(dict[str, object], item))

    expected_names = {name for name, _ in dataset_schemas()}
    actual_names = {_required_str(item, "filename") for item in tables}
    if actual_names != expected_names or len(tables) != len(expected_names):
        raise CampaignValidationError("dataset manifest table topology is invalid")

    for table in tables:
        filename = _required_str(table, "filename")
        expected_sha = _required_sha256(table, "sha256")
        _required_sha256(table, "schema_sha256")
        expected_rows = _required_int(table, "row_count")
        if expected_rows < 0:
            raise CampaignValidationError("table row_count must be non-negative")
        path = root / filename
        if not path.is_file():
            raise CampaignValidationError(f"dataset table is missing: {filename}")
        if _sha256_file(path) != expected_sha:
            raise CampaignValidationError(f"dataset table hash mismatch: {filename}")

    expected_bundle = _required_sha256(manifest, "bundle_sha256")
    actual_bundle = _manifest_bundle_sha256(manifest, tables)
    if actual_bundle != expected_bundle:
        raise CampaignValidationError("dataset bundle_sha256 does not match manifest content")


def _manifest_bundle_sha256(
    manifest: dict[str, object],
    tables: list[dict[str, object]],
) -> str:
    writer_options = manifest.get("writer_options")
    if not isinstance(writer_options, dict) or not all(
        isinstance(key, str) for key in writer_options
    ):
        raise CampaignValidationError("dataset writer_options must be an object")

    payload = {
        "dataset_schema_version": _required_int(manifest, "dataset_schema_version"),
        "materializer_version": _required_str(manifest, "materializer_version"),
        "source_pipeline_version": _required_str(manifest, "source_pipeline_version"),
        "source_report_sha256": _required_sha256(manifest, "source_report_sha256"),
        "source_normalized_records_sha256": _required_sha256(
            manifest,
            "source_normalized_records_sha256",
        ),
        "pyarrow_version": _required_str(manifest, "pyarrow_version"),
        "writer_options": cast(dict[str, object], writer_options),
        "tables": tables,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _load_primary_bbo(
    root: Path,
    event_rows: tuple[dict[str, object], ...],
) -> tuple[PrimaryBBOObservation, ...]:
    bbo_rows = _read_rows(
        root / "bbo.parquet",
        columns=["event_id", "bid_price_exact", "ask_price_exact"],
    )
    prices: dict[str, tuple[Decimal, Decimal]] = {}
    for row in bbo_rows:
        event_id = row.get("event_id")
        bid_raw = row.get("bid_price_exact")
        ask_raw = row.get("ask_price_exact")
        if not isinstance(event_id, str):
            raise CampaignValidationError("BBO event_id must be a string")
        if bid_raw is None and ask_raw is None:
            continue
        if not isinstance(bid_raw, str) or not isinstance(ask_raw, str):
            raise CampaignValidationError("BBO bid/ask prices must be paired exact strings")
        try:
            bid = parse_exact_decimal(bid_raw)
            ask = parse_exact_decimal(ask_raw)
        except NumericValidationError as exc:
            raise CampaignValidationError(str(exc)) from exc
        if bid <= 0 or ask <= bid:
            continue
        prices[event_id] = (bid, ask)

    output: list[PrimaryBBOObservation] = []
    for row in event_rows:
        if row.get("source_id") != _PRIMARY_SOURCE:
            continue
        if row.get("instrument_id") != _PRIMARY_INSTRUMENT:
            continue
        if row.get("event_type") != "BBO":
            continue

        quality_flags = _row_int(row, "quality_flags")
        if quality_flags & int(QualityFlag.SUSPECT):
            continue
        event_id = _row_str(row, "event_id")
        pair = prices.get(event_id)
        if pair is None:
            continue
        output.append(
            PrimaryBBOObservation(
                event_id=event_id,
                host_id=_row_str(row, "host_id"),
                boot_id=_row_str(row, "boot_id"),
                recv_mono_ns=_row_int(row, "recv_mono_ns"),
                recv_wall_ns=_row_int(row, "recv_wall_ns"),
                bid=pair[0],
                ask=pair[1],
            )
        )
    return tuple(output)


def _primary_l2_count(event_rows: tuple[dict[str, object], ...]) -> int:
    count = 0
    for row in event_rows:
        if row.get("source_id") != _PRIMARY_SOURCE:
            continue
        if row.get("instrument_id") != _PRIMARY_INSTRUMENT:
            continue
        if row.get("event_type") != "L2_SNAPSHOT":
            continue
        if _row_int(row, "quality_flags") & int(QualityFlag.SUSPECT):
            continue
        count += 1
    return count


def _frame_source_ids(rows: tuple[dict[str, object], ...]) -> set[str]:
    return {_row_str(row, "source_id") for row in rows}


def _frame_domains(rows: tuple[dict[str, object], ...]) -> set[tuple[str, str]]:
    return {(_row_str(row, "host_id"), _row_str(row, "boot_id")) for row in rows}


def _frame_wall_ns(rows: tuple[dict[str, object], ...]) -> tuple[int, ...]:
    return tuple(_row_int(row, "recv_wall_ns") for row in rows)


def _read_rows(
    path: Path,
    *,
    columns: list[str],
) -> tuple[dict[str, object], ...]:
    try:
        rows = _READ_TABLE(path, columns=columns, use_threads=False).to_pylist()
    except Exception as exc:
        raise CampaignValidationError(f"cannot read Parquet table: {path.name}") from exc
    return tuple(cast(dict[str, object], row) for row in rows)


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise CampaignValidationError(f"cannot read dataset file: {path.name}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CampaignValidationError(f"cannot hash dataset file: {path.name}") from exc
    return digest.hexdigest()


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
    _require_sha256(item, field)
    return item


def _row_str(row: dict[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise CampaignValidationError(f"Parquet {field} must be a non-empty string")
    return value


def _row_int(row: dict[str, object], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CampaignValidationError(f"Parquet {field} must be an integer")
    return value


def _require_sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise CampaignValidationError(f"{field} must be 64 lowercase hex characters")
