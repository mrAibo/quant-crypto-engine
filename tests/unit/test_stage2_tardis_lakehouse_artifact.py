from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast


def test_task029_lakehouse_manifest_is_frozen() -> None:
    path = Path("artifacts/stage_2/tardis_lakehouse_manifest.json")
    raw = path.read_bytes()
    payload = cast(dict[str, object], json.loads(raw))
    files = cast(list[dict[str, object]], payload["files"])

    assert hashlib.sha256(raw).hexdigest() == (
        "c5032eda1f33421a6d71560e42e0f3e042b1ccd78647e358ea8b0390b4fc0e5f"
    )
    assert payload["report_version"] == "stage2-task029-tardis-lakehouse-v1"
    assert payload["source_corpus_manifest_sha256"] == (
        "9696dca5f57fe160a8438236f1af82947a1588d2476a882fdf627f4cbd26e5e8"
    )
    assert payload["duckdb_version"] == "1.5.5"
    assert payload["parquet_file_count"] == 80
    assert payload["total_row_count"] == 103817053
    assert payload["parquet_set_sha256"] == (
        "4d451076c74fa706d57b3565a16cc5aa78875664c68fb934ab72c687257a7a2b"
    )
    assert payload["economic_outcomes_materialized"] is False
    assert payload["model_fitted"] is False
    assert payload["derived_layer_rebuildable"] is True
    assert len(files) == 80
    assert sum(cast(int, item["row_count"]) for item in files) == 103817053


def test_task029_lakehouse_row_breakdown_is_frozen() -> None:
    payload = cast(
        dict[str, object],
        json.loads(Path("artifacts/stage_2/tardis_lakehouse_manifest.json").read_bytes()),
    )
    files = cast(list[dict[str, object]], payload["files"])

    def total(prefix: str) -> int:
        return sum(
            cast(int, item["row_count"])
            for item in files
            if cast(str, item["relative_path"]).startswith(prefix)
        )

    assert total("parquet/hyperliquid/book_snapshot_5/") == 3030252
    assert total("parquet/hyperliquid/trades/") == 7170696
    assert total("parquet/binance-futures/quotes/") == 25002943
    assert total("parquet/binance-futures/trades/") == 68613162
