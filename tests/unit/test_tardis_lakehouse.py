from __future__ import annotations

import gzip
from pathlib import Path

import duckdb

from cryptobot.research import tardis_lakehouse as lake


def _write_gzip(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as stream:
        stream.write(text)


def test_book_snapshot_parquet_preserves_exact_values_and_row_order(tmp_path: Path) -> None:
    source = tmp_path / "BTC.csv.gz"
    target = tmp_path / "BTC.parquet"
    _write_gzip(
        source,
        (
            "exchange,symbol,timestamp,local_timestamp,"
            "asks[0].price,asks[0].amount,bids[0].price,bids[0].amount,"
            "asks[1].price,asks[1].amount,bids[1].price,bids[1].amount,"
            "asks[2].price,asks[2].amount,bids[2].price,bids[2].amount,"
            "asks[3].price,asks[3].amount,bids[3].price,bids[3].amount,"
            "asks[4].price,asks[4].amount,bids[4].price,bids[4].amount\n"
            "hyperliquid,BTC,1730419200000000,1730419200000100,"
            "70001.1,1.01,70000.9,2.02,70002,3,70000,4,70003,5,69999,6,"
            "70004,7,69998,8,70005,9,69997,10\n"
            "hyperliquid,BTC,1730419201000000,1730419201000100,"
            "70001.2,1.11,70001.0,2.12,70002,3,70000,4,70003,5,69999,6,"
            "70004,7,69998,8,70005,9,69997,10\n"
        ),
    )

    connection = duckdb.connect(":memory:")
    try:
        lake._write_parquet(connection, source, target, "book_snapshot_5")
        rows = connection.execute(
            "SELECT source_row_number, ask_price_0, bid_amount_4 "
            "FROM read_parquet(?) ORDER BY source_row_number",
            [str(target)],
        ).fetchall()
    finally:
        connection.close()

    assert rows[0][0] == 0
    assert str(rows[0][1]) == "70001.100000000000000000"
    assert str(rows[1][1]) == "70001.200000000000000000"
    assert str(rows[0][2]) == "10.000000000000000000"


def test_local_timestamp_day_validation_rejects_cross_day() -> None:
    lake._validate_day_range(
        "2024-11-01",
        1730419200000000,
        1730505599999999,
    )

    try:
        lake._validate_day_range(
            "2024-11-01",
            1730419200000000,
            1730505600000000,
        )
    except lake.TardisLakehouseError as exc:
        assert "escapes frozen UTC day" in str(exc)
    else:
        raise AssertionError("cross-day local timestamp must fail")
