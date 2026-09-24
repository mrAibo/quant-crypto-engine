from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from cryptobot.research.retrospective import (
    GATE_ELIGIBILITY,
    RetrospectiveDataError,
    analyze_binance_retrospective_50s,
    binance_usdm_daily_aggtrades_spec,
    build_retrospective_plan,
    download_binance_archive,
    hyperliquid_hourly_l2book_spec,
    hyperliquid_requester_pays_commands,
)


def test_retrospective_plan_is_explicitly_excluded_from_task_018_gate() -> None:
    plan = build_retrospective_plan(date(2026, 9, 1), date(2026, 9, 1))
    sources = plan["sources"]

    assert plan["task_018_gate_eligibility"] == GATE_ELIGIBILITY
    assert isinstance(sources, list)
    assert len(sources) == 50
    assert all(item["task_018_gate_eligibility"] == GATE_ELIGIBILITY for item in sources)


def test_official_archive_locations_are_deterministic() -> None:
    binance = binance_usdm_daily_aggtrades_spec(date(2026, 9, 1), "BTCUSDT")
    assert binance.location == (
        "https://data.binance.vision/data/futures/um/daily/aggTrades/"
        "BTCUSDT/BTCUSDT-aggTrades-2026-09-01.zip"
    )
    assert binance.checksum_location == f"{binance.location}.CHECKSUM"
    assert binance.access == "PUBLIC_HTTPS_NO_AUTH"

    hyperliquid = hyperliquid_hourly_l2book_spec(date(2026, 9, 1), 7, "BTC")
    assert hyperliquid.location == (
        "s3://hyperliquid-archive/market_data/20260901/7/l2Book/BTC.lz4"
    )
    assert hyperliquid.access == "AWS_S3_REQUESTER_PAYS"


def test_binance_download_verifies_published_checksum(tmp_path: Path) -> None:
    payload = b"verified-archive-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    spec = binance_usdm_daily_aggtrades_spec(date(2026, 9, 1), "ETHUSDT")

    def retrieve(url: str, destination: str) -> object:
        if url.endswith(".CHECKSUM"):
            Path(destination).write_text(f"{digest}  archive.zip\n", encoding="utf-8")
        else:
            Path(destination).write_bytes(payload)
        return destination

    result = download_binance_archive(spec, tmp_path / "retrospective", retrieve=retrieve)

    assert result.archive_path.read_bytes() == payload
    assert result.sha256 == digest
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["archive_sha256"] == digest
    assert manifest["task_018_gate_eligibility"] == GATE_ELIGIBILITY


def test_binance_checksum_mismatch_never_publishes_archive(tmp_path: Path) -> None:
    spec = binance_usdm_daily_aggtrades_spec(date(2026, 9, 1), "BTCUSDT")

    def retrieve(url: str, destination: str) -> object:
        if url.endswith(".CHECKSUM"):
            Path(destination).write_text(f"{'0' * 64}  archive.zip\n", encoding="utf-8")
        else:
            Path(destination).write_bytes(b"tampered")
        return destination

    root = tmp_path / "retrospective"
    with pytest.raises(RetrospectiveDataError, match="checksum mismatch"):
        download_binance_archive(spec, root, retrieve=retrieve)

    assert not tuple(root.rglob("*.zip"))
    assert not tuple(root.rglob("*.manifest.json"))


def test_retrospective_destination_cannot_be_campaign_root(tmp_path: Path) -> None:
    spec = binance_usdm_daily_aggtrades_spec(date(2026, 9, 1), "BTCUSDT")
    with pytest.raises(RetrospectiveDataError, match="must not be stored"):
        download_binance_archive(spec, tmp_path / "frontier-campaign")


def test_hyperliquid_commands_require_requester_pays(tmp_path: Path) -> None:
    spec = hyperliquid_hourly_l2book_spec(date(2026, 9, 1), 7, "BTC")
    commands = hyperliquid_requester_pays_commands((spec,), tmp_path / "retro")

    assert commands == (
        (
            "aws",
            "s3",
            "cp",
            spec.location,
            str(tmp_path / "retro" / "hyperliquid" / "l2book" / "2026-09-01-7-BTC.lz4"),
            "--request-payer",
            "requester",
        ),
    )


def _write_synthetic_aggtrades_archive(
    root: Path,
    symbol: str,
    day: date,
) -> Path:
    spec = binance_usdm_daily_aggtrades_spec(day, symbol)
    target = root / "binance" / spec.dataset.lower() / symbol / day.isoformat()
    target.mkdir(parents=True)
    archive = target / spec.location.rsplit("/", 1)[-1]
    csv_name = archive.name.removesuffix(".zip") + ".csv"
    start_ms = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)
    csv_payload = (
        "agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n"
        f"1,100,1,1,1,{start_ms + 1_000},true\n"
        f"2,101,1,2,2,{start_ms + 49_000},false\n"
        f"3,100,1,3,3,{start_ms + 51_000},true\n"
        f"4,102,1,4,4,{start_ms + 99_000},false\n"
    )
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zipped:
        zipped.writestr(csv_name, csv_payload)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "purpose": "AUXILIARY_RETROSPECTIVE_RESEARCH_ONLY",
        "task_018_gate_eligibility": GATE_ELIGIBILITY,
        "source": spec.as_dict(),
        "archive_sha256": digest,
        "archive_filename": archive.name,
        "checksum_filename": f"{archive.name}.CHECKSUM",
    }
    (target / f"{archive.name}.manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return archive


def test_binance_retrospective_50s_analysis_is_deterministic_and_non_gating(
    tmp_path: Path,
) -> None:
    root = tmp_path / "retrospective"
    day = date(2026, 9, 1)
    _write_synthetic_aggtrades_archive(root, "BTCUSDT", day)
    _write_synthetic_aggtrades_archive(root, "ETHUSDT", day)

    report = analyze_binance_retrospective_50s(root, day, day)

    assert report["task_018_gate_eligibility"] == GATE_ELIGIBILITY
    symbols = report["symbols"]
    assert isinstance(symbols, list)
    assert len(symbols) == 2
    for symbol in symbols:
        assert symbol["window_count"] == 2
        assert symbol["movement_quantiles_bps"]["q50"] == "100.00"
        assert symbol["movement_quantiles_bps"]["q95"] == "200.00"
        assert symbol["per_day"][0]["missing_50s_bucket_count"] == 1726


def test_binance_retrospective_50s_rejects_archive_tamper(tmp_path: Path) -> None:
    root = tmp_path / "retrospective"
    day = date(2026, 9, 1)
    archive = _write_synthetic_aggtrades_archive(root, "BTCUSDT", day)
    _write_synthetic_aggtrades_archive(root, "ETHUSDT", day)
    archive.write_bytes(archive.read_bytes() + b"tamper")

    with pytest.raises(RetrospectiveDataError, match="archive hash mismatch"):
        analyze_binance_retrospective_50s(root, day, day)
