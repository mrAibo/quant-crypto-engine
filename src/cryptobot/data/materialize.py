from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq

from cryptobot.data.events import (
    BBO,
    BookLevel,
    EventEnvelope,
    FundingRateObservation,
    L2Snapshot,
    MarkPrice,
    OraclePrice,
    ReferenceBBO,
    ReferenceTrade,
    Trade,
)
from cryptobot.data.normalization_pipeline import (
    PIPELINE_VERSION,
    FrameResult,
    build_pipeline_report,
    serialize_pipeline_report,
)
from cryptobot.data.numeric import serialize_exact_decimal

MATERIALIZER_VERSION = "parquet-materializer-v1"
DATASET_SCHEMA_VERSION = 1
ROW_GROUP_SIZE = 65_536
PARQUET_VERSION = "2.6"
DATA_PAGE_VERSION = "1.0"
COMPRESSION = "zstd"
COMPRESSION_LEVEL = 3

type _WriteTableFn = Callable[..., None]
type _ReadTableFn = Callable[..., pa.Table]

_WRITE_TABLE = cast(_WriteTableFn, pq.write_table)
_READ_TABLE = cast(_ReadTableFn, pq.read_table)

_TABLE_FILENAMES = (
    "frames.parquet",
    "events.parquet",
    "l2_snapshots.parquet",
    "l2_levels.parquet",
    "bbo.parquet",
    "trades.parquet",
    "funding_rates.parquet",
    "mark_prices.parquet",
    "oracle_prices.parquet",
    "reference_bbo.parquet",
    "reference_trades.parquet",
)


class MaterializationError(ValueError):
    """Raised when normalized evidence cannot be materialized safely."""


@dataclass(frozen=True, slots=True)
class MaterializedTable:
    filename: str
    row_count: int
    sha256: str
    schema_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "row_count": self.row_count,
            "sha256": self.sha256,
            "schema_sha256": self.schema_sha256,
        }


@dataclass(frozen=True, slots=True)
class MaterializationManifest:
    dataset_schema_version: int
    materializer_version: str
    source_pipeline_version: str
    source_report_sha256: str
    source_normalized_records_sha256: str
    pyarrow_version: str
    writer_options: tuple[tuple[str, object], ...]
    tables: tuple[MaterializedTable, ...]
    bundle_sha256: str
    causal_domain_count: int
    raw_frame_count: int
    normalized_event_count: int
    creation_semantics: str
    authority: str

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_schema_version": self.dataset_schema_version,
            "materializer_version": self.materializer_version,
            "source_pipeline_version": self.source_pipeline_version,
            "source_report_sha256": self.source_report_sha256,
            "source_normalized_records_sha256": self.source_normalized_records_sha256,
            "pyarrow_version": self.pyarrow_version,
            "writer_options": dict(self.writer_options),
            "tables": [table.as_dict() for table in self.tables],
            "bundle_sha256": self.bundle_sha256,
            "causal_domain_count": self.causal_domain_count,
            "raw_frame_count": self.raw_frame_count,
            "normalized_event_count": self.normalized_event_count,
            "creation_semantics": self.creation_semantics,
            "authority": self.authority,
        }


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    output_dir: Path
    manifest: MaterializationManifest


def frames_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("source_id", pa.string(), nullable=False),
            pa.field("host_id", pa.string(), nullable=False),
            pa.field("boot_id", pa.string(), nullable=False),
            pa.field("recv_wall_ns", pa.int64(), nullable=False),
            pa.field("recv_mono_ns", pa.int64(), nullable=False),
            pa.field("connection_id", pa.string(), nullable=False),
            pa.field("ingest_seq", pa.int64(), nullable=False),
            pa.field("raw_segment_id", pa.string(), nullable=False),
            pa.field("raw_offset", pa.int64(), nullable=False),
            pa.field("raw_sha256", pa.string(), nullable=False),
            pa.field("parser_name", pa.string(), nullable=False),
            pa.field("channel_or_stream", pa.string(), nullable=True),
            pa.field("outcome", pa.string(), nullable=False),
            pa.field("event_count", pa.int32(), nullable=False),
            pa.field("error_code", pa.string(), nullable=True),
            pa.field("parser_error_code", pa.string(), nullable=True),
            pa.field("error_detail", pa.string(), nullable=True),
        ]
    )


def events_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("host_id", pa.string(), nullable=False),
            pa.field("boot_id", pa.string(), nullable=False),
            pa.field("recv_mono_ns", pa.int64(), nullable=False),
            pa.field("recv_wall_ns", pa.int64(), nullable=False),
            pa.field("source_id", pa.string(), nullable=False),
            pa.field("raw_segment_id", pa.string(), nullable=False),
            pa.field("raw_offset", pa.int64(), nullable=False),
            pa.field("event_ordinal", pa.int32(), nullable=False),
            pa.field("schema_version", pa.int32(), nullable=False),
            pa.field("event_id", pa.string(), nullable=False),
            pa.field("event_type", pa.string(), nullable=False),
            pa.field("instrument_id", pa.string(), nullable=False),
            pa.field("native_symbol", pa.string(), nullable=False),
            pa.field("exchange_ts_ns", pa.int64(), nullable=True),
            pa.field("exchange_ts_resolution_ns", pa.int64(), nullable=True),
            pa.field("exchange_ts_semantics", pa.string(), nullable=False),
            pa.field("connection_id", pa.string(), nullable=False),
            pa.field("ingest_seq", pa.int64(), nullable=False),
            pa.field("native_sequence", pa.int64(), nullable=True),
            pa.field("native_update_id", pa.string(), nullable=True),
            pa.field("raw_sha256", pa.string(), nullable=False),
            pa.field("parse_version", pa.string(), nullable=False),
            pa.field("quality_flags", pa.int64(), nullable=False),
            pa.field("availability_kind", pa.string(), nullable=False),
        ]
    )


def l2_snapshots_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("event_id", pa.string(), nullable=False),
            pa.field("depth_limit", pa.int32(), nullable=True),
            pa.field("aggregation", pa.string(), nullable=True),
            pa.field("full_snapshot", pa.bool_(), nullable=False),
        ]
    )


def l2_levels_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("event_id", pa.string(), nullable=False),
            pa.field("side", pa.string(), nullable=False),
            pa.field("level_ordinal", pa.int32(), nullable=False),
            pa.field("price_exact", pa.string(), nullable=False),
            pa.field("size_exact", pa.string(), nullable=False),
            pa.field("order_count", pa.int64(), nullable=True),
        ]
    )


def bbo_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("event_id", pa.string(), nullable=False),
            pa.field("bid_price_exact", pa.string(), nullable=True),
            pa.field("bid_size_exact", pa.string(), nullable=True),
            pa.field("ask_price_exact", pa.string(), nullable=True),
            pa.field("ask_size_exact", pa.string(), nullable=True),
        ]
    )


def trades_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("event_id", pa.string(), nullable=False),
            pa.field("price_exact", pa.string(), nullable=False),
            pa.field("size_exact", pa.string(), nullable=False),
            pa.field("native_side", pa.string(), nullable=True),
            pa.field("aggressor_side", pa.string(), nullable=False),
            pa.field("trade_id", pa.string(), nullable=True),
            pa.field("transaction_hash", pa.string(), nullable=True),
        ]
    )


def funding_rates_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("event_id", pa.string(), nullable=False),
            pa.field("rate_exact", pa.string(), nullable=False),
            pa.field("rate_period_seconds", pa.int64(), nullable=False),
            pa.field("kind", pa.string(), nullable=False),
            pa.field("effective_boundary_ns", pa.int64(), nullable=True),
        ]
    )


def mark_prices_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("event_id", pa.string(), nullable=False),
            pa.field("price_exact", pa.string(), nullable=False),
            pa.field("method", pa.string(), nullable=True),
        ]
    )


def oracle_prices_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("event_id", pa.string(), nullable=False),
            pa.field("price_exact", pa.string(), nullable=False),
            pa.field("oracle_id", pa.string(), nullable=True),
        ]
    )


def reference_bbo_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("event_id", pa.string(), nullable=False),
            pa.field("bid_price_exact", pa.string(), nullable=True),
            pa.field("bid_size_exact", pa.string(), nullable=True),
            pa.field("ask_price_exact", pa.string(), nullable=True),
            pa.field("ask_size_exact", pa.string(), nullable=True),
            pa.field("sampling_mode", pa.string(), nullable=False),
        ]
    )


def reference_trades_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("event_id", pa.string(), nullable=False),
            pa.field("price_exact", pa.string(), nullable=False),
            pa.field("size_exact", pa.string(), nullable=False),
            pa.field("native_side", pa.string(), nullable=True),
            pa.field("aggressor_side", pa.string(), nullable=False),
            pa.field("trade_id", pa.string(), nullable=True),
        ]
    )


def dataset_schemas() -> tuple[tuple[str, pa.Schema], ...]:
    return (
        ("frames.parquet", frames_schema()),
        ("events.parquet", events_schema()),
        ("l2_snapshots.parquet", l2_snapshots_schema()),
        ("l2_levels.parquet", l2_levels_schema()),
        ("bbo.parquet", bbo_schema()),
        ("trades.parquet", trades_schema()),
        ("funding_rates.parquet", funding_rates_schema()),
        ("mark_prices.parquet", mark_prices_schema()),
        ("oracle_prices.parquet", oracle_prices_schema()),
        ("reference_bbo.parquet", reference_bbo_schema()),
        ("reference_trades.parquet", reference_trades_schema()),
    )


def writer_options() -> tuple[tuple[str, object], ...]:
    return (
        ("version", PARQUET_VERSION),
        ("data_page_version", DATA_PAGE_VERSION),
        ("compression", COMPRESSION),
        ("compression_level", COMPRESSION_LEVEL),
        ("use_dictionary", False),
        ("write_statistics", True),
        ("write_page_checksum", True),
        ("row_group_size", ROW_GROUP_SIZE),
    )


def materialize_research_dataset(
    results: tuple[FrameResult, ...],
    output_dir: str | Path,
) -> MaterializationResult:
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite published dataset: {destination}")

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = parent / f".{destination.name}.tmp"
    if temporary.exists():
        raise FileExistsError(f"temporary materialization path already exists: {temporary}")

    rows = _build_rows(results)
    report = build_pipeline_report(results)
    report_bytes = serialize_pipeline_report(report)
    temporary.mkdir()

    try:
        table_results: list[MaterializedTable] = []
        for filename, schema in dataset_schemas():
            table_rows = rows[filename]
            table = pa.Table.from_pylist(table_rows, schema=schema)
            _reject_floating_schema(table.schema, filename)
            path = temporary / filename
            _write_table(table, path)
            _validate_round_trip(
                path=path,
                expected_schema=schema,
                expected_rows=table_rows,
            )
            table_results.append(
                MaterializedTable(
                    filename=filename,
                    row_count=table.num_rows,
                    sha256=_sha256_file(path),
                    schema_sha256=_schema_sha256(schema),
                )
            )

        tables = tuple(table_results)
        source_report_sha256 = hashlib.sha256(report_bytes).hexdigest()
        bundle_sha256 = _bundle_sha256(
            source_report_sha256=source_report_sha256,
            source_normalized_records_sha256=report.normalized_records_sha256,
            tables=tables,
        )
        manifest = MaterializationManifest(
            dataset_schema_version=DATASET_SCHEMA_VERSION,
            materializer_version=MATERIALIZER_VERSION,
            source_pipeline_version=PIPELINE_VERSION,
            source_report_sha256=source_report_sha256,
            source_normalized_records_sha256=report.normalized_records_sha256,
            pyarrow_version=pa.__version__,
            writer_options=writer_options(),
            tables=tables,
            bundle_sha256=bundle_sha256,
            causal_domain_count=report.causal_domain_count,
            raw_frame_count=report.total_raw_frames,
            normalized_event_count=report.normalized_record_count,
            creation_semantics="DERIVED_REBUILDABLE",
            authority="QCR1_RAW_IS_AUTHORITATIVE",
        )
        manifest_bytes = serialize_manifest(manifest)
        (temporary / "manifest.json").write_bytes(manifest_bytes)
        _validate_manifest(temporary, manifest)
        os.rename(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return MaterializationResult(output_dir=destination, manifest=manifest)


def serialize_manifest(manifest: MaterializationManifest) -> bytes:
    return (
        json.dumps(
            manifest.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode()


def read_manifest(path: str | Path) -> dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise MaterializationError("manifest root must be an object")
    return raw


def _build_rows(results: tuple[FrameResult, ...]) -> dict[str, list[dict[str, object]]]:
    rows: dict[str, list[dict[str, object]]] = {
        filename: [] for filename in _TABLE_FILENAMES
    }
    ordered_results = sorted(results, key=_frame_sort_key)
    seen_event_ids: set[str] = set()

    for result in ordered_results:
        rows["frames.parquet"].append(_frame_row(result))
        for ordinal, event in enumerate(result.events):
            _validate_event_matches_frame(result, event.envelope)
            if event.envelope.event_id in seen_event_ids:
                raise MaterializationError(
                    f"duplicate normalized event_id: {event.envelope.event_id}"
                )
            seen_event_ids.add(event.envelope.event_id)
            rows["events.parquet"].append(_event_row(result, ordinal, event.envelope))
            _append_payload_rows(rows, event)

    return rows


def _frame_sort_key(result: FrameResult) -> tuple[object, ...]:
    return (
        result.host_id,
        result.boot_id,
        result.recv_mono_ns,
        result.recv_wall_ns,
        result.source_id,
        result.raw_segment_id,
        result.raw_offset,
    )


def _frame_row(result: FrameResult) -> dict[str, object]:
    error = result.error
    return {
        "source_id": result.source_id,
        "host_id": result.host_id,
        "boot_id": result.boot_id,
        "recv_wall_ns": result.recv_wall_ns,
        "recv_mono_ns": result.recv_mono_ns,
        "connection_id": result.connection_id,
        "ingest_seq": result.ingest_seq,
        "raw_segment_id": result.raw_segment_id,
        "raw_offset": result.raw_offset,
        "raw_sha256": result.raw_sha256,
        "parser_name": result.parser_name,
        "channel_or_stream": result.channel_or_stream,
        "outcome": result.outcome.value,
        "event_count": len(result.events),
        "error_code": None if error is None else error.code.value,
        "parser_error_code": None if error is None else error.parser_code,
        "error_detail": None if error is None else error.detail,
    }


def _event_row(
    result: FrameResult,
    ordinal: int,
    envelope: EventEnvelope,
) -> dict[str, object]:
    return {
        "host_id": result.host_id,
        "boot_id": result.boot_id,
        "recv_mono_ns": result.recv_mono_ns,
        "recv_wall_ns": result.recv_wall_ns,
        "source_id": result.source_id,
        "raw_segment_id": result.raw_segment_id,
        "raw_offset": result.raw_offset,
        "event_ordinal": ordinal,
        "schema_version": envelope.schema_version,
        "event_id": envelope.event_id,
        "event_type": envelope.event_type.value,
        "instrument_id": envelope.instrument_id,
        "native_symbol": envelope.native_symbol,
        "exchange_ts_ns": envelope.exchange_ts_ns,
        "exchange_ts_resolution_ns": envelope.exchange_ts_resolution_ns,
        "exchange_ts_semantics": envelope.exchange_ts_semantics.value,
        "connection_id": envelope.connection_id,
        "ingest_seq": envelope.ingest_seq,
        "native_sequence": envelope.native_sequence,
        "native_update_id": envelope.native_update_id,
        "raw_sha256": envelope.raw_sha256,
        "parse_version": envelope.parse_version,
        "quality_flags": int(envelope.quality_flags),
        "availability_kind": envelope.availability_kind.value,
    }


def _validate_event_matches_frame(result: FrameResult, envelope: EventEnvelope) -> None:
    mismatches: list[str] = []
    comparisons = (
        ("source", envelope.source, result.source_id),
        ("host_id", envelope.host_id, result.host_id),
        ("boot_id", envelope.boot_id, result.boot_id),
        ("recv_wall_ns", envelope.recv_wall_ns, result.recv_wall_ns),
        ("recv_mono_ns", envelope.recv_mono_ns, result.recv_mono_ns),
        ("connection_id", envelope.connection_id, result.connection_id),
        ("ingest_seq", envelope.ingest_seq, result.ingest_seq),
        ("raw_segment_id", envelope.raw_segment_id, result.raw_segment_id),
        ("raw_offset", envelope.raw_offset, result.raw_offset),
        ("raw_sha256", envelope.raw_sha256, result.raw_sha256),
    )
    for field, actual, expected in comparisons:
        if actual != expected:
            mismatches.append(field)
    if mismatches:
        raise MaterializationError(
            "event envelope does not match frame provenance: " + ",".join(mismatches)
        )


def _append_payload_rows(
    rows: dict[str, list[dict[str, object]]],
    event: object,
) -> None:
    if isinstance(event, L2Snapshot):
        rows["l2_snapshots.parquet"].append(
            {
                "event_id": event.envelope.event_id,
                "depth_limit": event.depth_limit,
                "aggregation": event.aggregation,
                "full_snapshot": event.full_snapshot,
            }
        )
        for ordinal, level in enumerate(event.bids):
            rows["l2_levels.parquet"].append(
                _l2_level_row(event.envelope.event_id, "BID", ordinal, level)
            )
        for ordinal, level in enumerate(event.asks):
            rows["l2_levels.parquet"].append(
                _l2_level_row(event.envelope.event_id, "ASK", ordinal, level)
            )
        return

    if isinstance(event, BBO):
        rows["bbo.parquet"].append(
            {
                "event_id": event.envelope.event_id,
                "bid_price_exact": _decimal_or_none(event.bid_price),
                "bid_size_exact": _decimal_or_none(event.bid_size),
                "ask_price_exact": _decimal_or_none(event.ask_price),
                "ask_size_exact": _decimal_or_none(event.ask_size),
            }
        )
        return

    if isinstance(event, Trade):
        rows["trades.parquet"].append(
            {
                "event_id": event.envelope.event_id,
                "price_exact": serialize_exact_decimal(event.price),
                "size_exact": serialize_exact_decimal(event.size),
                "native_side": event.native_side,
                "aggressor_side": event.aggressor_side.value,
                "trade_id": event.trade_id,
                "transaction_hash": event.transaction_hash,
            }
        )
        return

    if isinstance(event, FundingRateObservation):
        rows["funding_rates.parquet"].append(
            {
                "event_id": event.envelope.event_id,
                "rate_exact": serialize_exact_decimal(event.rate),
                "rate_period_seconds": event.rate_period_seconds,
                "kind": event.kind.value,
                "effective_boundary_ns": event.effective_boundary_ns,
            }
        )
        return

    if isinstance(event, MarkPrice):
        rows["mark_prices.parquet"].append(
            {
                "event_id": event.envelope.event_id,
                "price_exact": serialize_exact_decimal(event.price),
                "method": event.method,
            }
        )
        return

    if isinstance(event, OraclePrice):
        rows["oracle_prices.parquet"].append(
            {
                "event_id": event.envelope.event_id,
                "price_exact": serialize_exact_decimal(event.price),
                "oracle_id": event.oracle_id,
            }
        )
        return

    if isinstance(event, ReferenceBBO):
        rows["reference_bbo.parquet"].append(
            {
                "event_id": event.envelope.event_id,
                "bid_price_exact": _decimal_or_none(event.bid_price),
                "bid_size_exact": _decimal_or_none(event.bid_size),
                "ask_price_exact": _decimal_or_none(event.ask_price),
                "ask_size_exact": _decimal_or_none(event.ask_size),
                "sampling_mode": event.sampling_mode,
            }
        )
        return

    if isinstance(event, ReferenceTrade):
        rows["reference_trades.parquet"].append(
            {
                "event_id": event.envelope.event_id,
                "price_exact": serialize_exact_decimal(event.price),
                "size_exact": serialize_exact_decimal(event.size),
                "native_side": event.native_side,
                "aggressor_side": event.aggressor_side.value,
                "trade_id": event.trade_id,
            }
        )
        return

    raise MaterializationError(f"unsupported normalized event class: {type(event).__name__}")


def _l2_level_row(
    event_id: str,
    side: str,
    ordinal: int,
    level: BookLevel,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "side": side,
        "level_ordinal": ordinal,
        "price_exact": serialize_exact_decimal(level.price),
        "size_exact": serialize_exact_decimal(level.size),
        "order_count": level.order_count,
    }


def _decimal_or_none(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return serialize_exact_decimal(value)


def _write_table(table: pa.Table, path: Path) -> None:
    _WRITE_TABLE(
        table,
        path,
        version=PARQUET_VERSION,
        data_page_version=DATA_PAGE_VERSION,
        compression=COMPRESSION,
        compression_level=COMPRESSION_LEVEL,
        use_dictionary=False,
        write_statistics=True,
        write_page_checksum=True,
        row_group_size=ROW_GROUP_SIZE,
    )


def _validate_round_trip(
    *,
    path: Path,
    expected_schema: pa.Schema,
    expected_rows: list[dict[str, object]],
) -> None:
    actual = _READ_TABLE(path, use_threads=False)
    if not actual.schema.equals(expected_schema, check_metadata=True):
        raise MaterializationError(f"schema mismatch after Parquet round trip: {path.name}")
    if actual.num_rows != len(expected_rows):
        raise MaterializationError(f"row-count mismatch after Parquet round trip: {path.name}")
    actual_rows = actual.to_pylist()
    if actual_rows != expected_rows:
        raise MaterializationError(f"row-order/value mismatch after Parquet round trip: {path.name}")
    _reject_floating_schema(actual.schema, path.name)


def _validate_manifest(directory: Path, manifest: MaterializationManifest) -> None:
    expected_names = {table.filename for table in manifest.tables}
    if expected_names != set(_TABLE_FILENAMES):
        raise MaterializationError("manifest table set does not match fixed dataset topology")
    for table in manifest.tables:
        path = directory / table.filename
        if not path.is_file():
            raise MaterializationError(f"materialized table is missing: {table.filename}")
        if _sha256_file(path) != table.sha256:
            raise MaterializationError(f"materialized file hash changed: {table.filename}")
    loaded = read_manifest(directory / "manifest.json")
    if loaded != manifest.as_dict():
        raise MaterializationError("manifest round trip mismatch")


def _schema_descriptor(schema: pa.Schema) -> list[dict[str, object]]:
    return [
        {
            "name": field.name,
            "type": str(field.type),
            "nullable": field.nullable,
        }
        for field in schema
    ]


def _schema_sha256(schema: pa.Schema) -> str:
    encoded = json.dumps(
        _schema_descriptor(schema),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _bundle_sha256(
    *,
    source_report_sha256: str,
    source_normalized_records_sha256: str,
    tables: tuple[MaterializedTable, ...],
) -> str:
    payload = {
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "materializer_version": MATERIALIZER_VERSION,
        "source_pipeline_version": PIPELINE_VERSION,
        "source_report_sha256": source_report_sha256,
        "source_normalized_records_sha256": source_normalized_records_sha256,
        "pyarrow_version": pa.__version__,
        "writer_options": dict(writer_options()),
        "tables": [table.as_dict() for table in tables],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _reject_floating_schema(schema: pa.Schema, filename: str) -> None:
    floating = [field.name for field in schema if pa.types.is_floating(field.type)]
    if floating:
        raise MaterializationError(
            f"floating-point columns are forbidden in {filename}: {','.join(floating)}"
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
