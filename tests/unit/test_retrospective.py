from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from cryptobot.research.retrospective import (
    GATE_ELIGIBILITY,
    RetrospectiveDataError,
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
