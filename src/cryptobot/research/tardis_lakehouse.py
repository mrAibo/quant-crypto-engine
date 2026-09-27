from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import duckdb

from cryptobot.research.tardis_historical import frozen_specs

DUCKDB_VERSION = "1.5.5"
LAKEHOUSE_VERSION = "stage2-task029-tardis-lakehouse-v1"
EXPECTED_CORPUS_SHA256 = "9696dca5f57fe160a8438236f1af82947a1588d2476a882fdf627f4cbd26e5e8"
DECIMAL_SQL = "DECIMAL(38,18)"
PARQUET_COMPRESSION = "ZSTD"
ROW_GROUP_SIZE = 100_000


class TardisLakehouseError(ValueError):
    """Raised when the reproducible TASK-029 analytical layer is invalid."""


@dataclass(frozen=True, slots=True)
class LakehouseFile:
    relative_path: str
    sha256: str
    row_count: int
    min_local_timestamp_us: int
    max_local_timestamp_us: int
    source_archive_relative_path: str
    source_archive_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "row_count": self.row_count,
            "min_local_timestamp_us": self.min_local_timestamp_us,
            "max_local_timestamp_us": self.max_local_timestamp_us,
            "source_archive_relative_path": self.source_archive_relative_path,
            "source_archive_sha256": self.source_archive_sha256,
        }


def build_lakehouse(
    *,
    source_root: str | Path,
    corpus_manifest_path: str | Path,
    output_root: str | Path,
) -> dict[str, object]:
    source = Path(source_root)
    output = Path(output_root)
    corpus_path = Path(corpus_manifest_path)
    corpus_raw = corpus_path.read_bytes()
    corpus_sha = hashlib.sha256(corpus_raw).hexdigest()
    if corpus_sha != EXPECTED_CORPUS_SHA256:
        raise TardisLakehouseError("TASK-028 corpus manifest SHA mismatch")
    corpus = cast(dict[str, object], json.loads(corpus_raw))
    archives = cast(list[dict[str, object]], corpus["archives"])
    archive_by_path = {cast(str, item["relative_path"]): item for item in archives}
    if len(archive_by_path) != 80:
        raise TardisLakehouseError("TASK-028 corpus must bind exactly 80 archives")

    parquet_root = output / "parquet"
    catalog_root = output / "catalog"
    parquet_root.mkdir(parents=True, exist_ok=True)
    catalog_root.mkdir(parents=True, exist_ok=True)

    files: list[LakehouseFile] = []
    connection = duckdb.connect(":memory:")
    connection.execute("SET threads = 1")
    connection.execute("SET preserve_insertion_order = true")
    try:
        for spec in frozen_specs():
            archive_rel = spec.relative_path.as_posix()
            archive_info = archive_by_path.get(archive_rel)
            if archive_info is None:
                raise TardisLakehouseError(f"corpus archive missing from manifest: {archive_rel}")
            source_path = source / spec.relative_path
            expected_archive_sha = cast(str, archive_info["archive_sha256"])
            if _sha256_file(source_path) != expected_archive_sha:
                raise TardisLakehouseError(f"source archive SHA mismatch: {archive_rel}")

            target = (
                parquet_root
                / spec.exchange
                / spec.data_type
                / spec.day.isoformat()
                / f"{spec.symbol}.parquet"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            _write_parquet(connection, source_path, target, spec.data_type)

            row_count, minimum, maximum, reversals = _parquet_stats(connection, target)
            if row_count <= 0:
                raise TardisLakehouseError(f"derived parquet is empty: {target}")
            if reversals != 0:
                raise TardisLakehouseError(f"local timestamp reversal detected: {target}")
            _validate_day_range(spec.day.isoformat(), minimum, maximum)

            files.append(
                LakehouseFile(
                    relative_path=target.relative_to(output).as_posix(),
                    sha256=_sha256_file(target),
                    row_count=row_count,
                    min_local_timestamp_us=minimum,
                    max_local_timestamp_us=maximum,
                    source_archive_relative_path=archive_rel,
                    source_archive_sha256=expected_archive_sha,
                )
            )
    finally:
        connection.close()

    files.sort(key=lambda item: item.relative_path)
    _build_catalog(output, files)
    return _manifest(output, corpus_sha, files)


def write_lakehouse_manifest(
    *,
    source_root: str | Path,
    corpus_manifest_path: str | Path,
    output_root: str | Path,
    manifest_path: str | Path,
) -> Path:
    report = build_lakehouse(
        source_root=source_root,
        corpus_manifest_path=corpus_manifest_path,
        output_root=output_root,
    )
    target = Path(manifest_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_bytes(report)
    try:
        with target.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if target.read_bytes() != payload:
            raise TardisLakehouseError("existing lakehouse manifest differs") from None
    return target


def _write_parquet(
    connection: duckdb.DuckDBPyConnection,
    source_path: Path,
    target_path: Path,
    data_type: str,
) -> None:
    select_sql = _select_sql(data_type)
    source_literal = _sql_literal(source_path)
    temporary = target_path.with_suffix(".parquet.partial")
    temporary_literal = _sql_literal(temporary)
    if temporary.exists():
        temporary.unlink()
    sql = (
        f"COPY (SELECT {select_sql} FROM read_csv({source_literal}, "
        "header=true, all_varchar=true)) "
        f"TO {temporary_literal} (FORMAT PARQUET, COMPRESSION {PARQUET_COMPRESSION}, "
        f"ROW_GROUP_SIZE {ROW_GROUP_SIZE})"
    )
    connection.execute(sql)
    if target_path.exists():
        if _sha256_file(target_path) != _sha256_file(temporary):
            temporary.unlink()
            raise TardisLakehouseError(f"existing parquet differs: {target_path}")
        temporary.unlink()
        return
    temporary.replace(target_path)


def _select_sql(data_type: str) -> str:
    prefix = (
        "row_number() OVER () - 1 AS source_row_number,"
        "CAST(exchange AS VARCHAR) AS exchange,"
        "CAST(symbol AS VARCHAR) AS symbol,"
        "CAST(timestamp AS BIGINT) AS exchange_timestamp_us,"
        "CAST(local_timestamp AS BIGINT) AS local_timestamp_us"
    )
    if data_type == "book_snapshot_5":
        columns: list[str] = [prefix]
        for index in range(5):
            columns.extend(
                (
                    f'CAST("asks[{index}].price" AS {DECIMAL_SQL}) AS ask_price_{index}',
                    f'CAST("asks[{index}].amount" AS {DECIMAL_SQL}) AS ask_amount_{index}',
                    f'CAST("bids[{index}].price" AS {DECIMAL_SQL}) AS bid_price_{index}',
                    f'CAST("bids[{index}].amount" AS {DECIMAL_SQL}) AS bid_amount_{index}',
                )
            )
        return ",".join(columns)
    if data_type == "quotes":
        return ",".join(
            (
                prefix,
                f"CAST(ask_amount AS {DECIMAL_SQL}) AS ask_amount",
                f"CAST(ask_price AS {DECIMAL_SQL}) AS ask_price",
                f"CAST(bid_price AS {DECIMAL_SQL}) AS bid_price",
                f"CAST(bid_amount AS {DECIMAL_SQL}) AS bid_amount",
            )
        )
    if data_type == "trades":
        return ",".join(
            (
                prefix,
                "CAST(id AS VARCHAR) AS trade_id",
                "CAST(side AS VARCHAR) AS side",
                f"CAST(price AS {DECIMAL_SQL}) AS price",
                f"CAST(amount AS {DECIMAL_SQL}) AS amount",
            )
        )
    raise TardisLakehouseError(f"unsupported Tardis data type: {data_type}")


def _parquet_stats(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
) -> tuple[int, int, int, int]:
    literal = _sql_literal(path)
    query = f"""
        WITH ordered AS (
            SELECT
                source_row_number,
                local_timestamp_us,
                lag(local_timestamp_us) OVER (ORDER BY source_row_number) AS previous_ts
            FROM read_parquet({literal})
        )
        SELECT
            count(*)::BIGINT,
            min(local_timestamp_us)::BIGINT,
            max(local_timestamp_us)::BIGINT,
            sum(
                CASE WHEN previous_ts IS NOT NULL AND local_timestamp_us < previous_ts
                THEN 1 ELSE 0 END
            )::BIGINT
        FROM ordered
    """
    row = connection.execute(query).fetchone()
    if row is None or any(value is None for value in row):
        raise TardisLakehouseError(f"cannot derive parquet stats: {path}")
    return int(row[0]), int(row[1]), int(row[2]), int(row[3])


def _validate_day_range(day_text: str, minimum: int, maximum: int) -> None:
    start = datetime.fromisoformat(day_text).replace(tzinfo=UTC)
    end = start + timedelta(days=1)
    start_us = int(start.timestamp() * 1_000_000)
    end_us = int(end.timestamp() * 1_000_000)
    if minimum < start_us or maximum >= end_us:
        raise TardisLakehouseError(
            f"local timestamp escapes frozen UTC day {day_text}: {minimum}..{maximum}"
        )


def _build_catalog(output_root: Path, files: list[LakehouseFile]) -> None:
    catalog_path = output_root / "catalog" / "historical.duckdb"
    if catalog_path.exists():
        catalog_path.unlink()
    connection = duckdb.connect(str(catalog_path))
    try:
        connection.execute(
            "CREATE TABLE corpus_files(relative_path VARCHAR, sha256 VARCHAR, row_count BIGINT)"
        )
        connection.executemany(
            "INSERT INTO corpus_files VALUES (?, ?, ?)",
            [(item.relative_path, item.sha256, item.row_count) for item in files],
        )
        for view_name, exchange, data_type in (
            ("hl_book_snapshot_5", "hyperliquid", "book_snapshot_5"),
            ("hl_trades", "hyperliquid", "trades"),
            ("binance_quotes", "binance-futures", "quotes"),
            ("binance_trades", "binance-futures", "trades"),
        ):
            glob_path = output_root / "parquet" / exchange / data_type / "*" / "*.parquet"
            connection.execute(
                f"CREATE VIEW {view_name} AS SELECT * FROM read_parquet({_sql_literal(glob_path)})"
            )
        connection.execute("CREATE TABLE lakehouse_meta(key VARCHAR PRIMARY KEY, value VARCHAR)")
        connection.executemany(
            "INSERT INTO lakehouse_meta VALUES (?, ?)",
            [
                ("lakehouse_version", LAKEHOUSE_VERSION),
                ("duckdb_version", DUCKDB_VERSION),
                ("parquet_compression", PARQUET_COMPRESSION),
                ("economic_outcomes_materialized", "false"),
                ("source_of_truth", "TASK028_IMMUTABLE_RAW_PLUS_MANIFESTS"),
            ],
        )
        connection.execute("CHECKPOINT")
    finally:
        connection.close()


def _manifest(
    output_root: Path,
    corpus_sha256: str,
    files: list[LakehouseFile],
) -> dict[str, object]:
    file_dicts = [item.as_dict() for item in files]
    aggregate = hashlib.sha256(_json_bytes({"files": file_dicts})).hexdigest()
    return {
        "schema_version": 1,
        "report_version": LAKEHOUSE_VERSION,
        "source_corpus_manifest_sha256": corpus_sha256,
        "duckdb_version": DUCKDB_VERSION,
        "parquet_compression": PARQUET_COMPRESSION,
        "parquet_file_count": len(files),
        "total_row_count": sum(item.row_count for item in files),
        "parquet_set_sha256": aggregate,
        "catalog_relative_path": (
            (output_root / "catalog" / "historical.duckdb").relative_to(output_root).as_posix()
        ),
        "files": file_dicts,
        "economic_outcomes_materialized": False,
        "model_fitted": False,
        "source_of_truth": "TASK028_IMMUTABLE_RAW_PLUS_MANIFESTS",
        "derived_layer_rebuildable": True,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _sql_literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"
