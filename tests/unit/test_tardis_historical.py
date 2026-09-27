from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path

import pytest

from cryptobot.research import tardis_historical as th


def _write_fake_gzip(path: Path, header: str) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as stream:
        stream.write(header + "\n")
        stream.write("fake,row\n")


def test_frozen_dates_are_twenty_first_of_month_days_before_fastbook() -> None:
    days = th.frozen_days()

    assert len(days) == 20
    assert days[0] == date(2024, 11, 1)
    assert days[-1] == date(2026, 6, 1)
    assert all(day.day == 1 for day in days)
    assert all(day < th.HYPERLIQUID_FASTBOOK_CUTOFF for day in days)


def test_protocol_freezes_480_hours_and_eighty_archives() -> None:
    protocol = th.build_protocol()

    assert protocol["evidence_role"] == "DEVELOPMENT_ONLY_EXTERNAL_RECEIVE_TIME"
    assert protocol["coverage_hours"] == 480
    assert protocol["expected_archive_count"] == 80
    assert protocol["feature_family"] == "TASK025_EIGHT_FEATURE_MICROSTRUCTURE_V1_UNCHANGED"
    assert protocol["task027_relationship"] == (
        "PARALLEL_DO_NOT_REPLACE_OR_STOP_PROSPECTIVE_CAPTURE"
    )
    assert protocol["old_confirmation"] == "UNOPENED_AND_EXCLUDED"
    assert protocol["model_fitting_allowed_in_task028"] is False
    assert protocol["outcome_dependent_date_exclusion"] is False


def test_source_urls_are_deterministic() -> None:
    specs = th.frozen_specs()
    assert specs[0].url == (
        "https://datasets.tardis.dev/v1/hyperliquid/book_snapshot_5/2024/11/01/BTC.csv.gz"
    )
    assert specs[1].url == (
        "https://datasets.tardis.dev/v1/hyperliquid/trades/2024/11/01/BTC.csv.gz"
    )
    assert specs[2].url == (
        "https://datasets.tardis.dev/v1/binance-futures/quotes/2024/11/01/BTCUSDT.csv.gz"
    )


def test_download_publishes_hash_verified_manifest(tmp_path: Path) -> None:
    spec = th.frozen_specs()[0]

    def retrieve(url: str, destination: Path) -> None:
        assert url == spec.url
        _write_fake_gzip(destination, spec.expected_header)

    result = th.download_archive(spec, tmp_path / "history", retrieve=retrieve)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert result.archive_path.is_file()
    assert len(result.sha256) == 64
    assert manifest["archive_sha256"] == result.sha256
    assert manifest["protocol_sha256"] == th.protocol_sha256()
    assert manifest["gzip_crc_verified"] is True
    assert manifest["old_confirmation_used"] is False
    assert manifest["task027_replaced"] is False


def test_download_is_idempotent_only_when_existing_evidence_verifies(tmp_path: Path) -> None:
    spec = th.frozen_specs()[1]

    def retrieve(url: str, destination: Path) -> None:
        del url
        _write_fake_gzip(destination, spec.expected_header)

    first = th.download_archive(spec, tmp_path / "history", retrieve=retrieve)
    second = th.download_archive(spec, tmp_path / "history", retrieve=retrieve)
    assert second.sha256 == first.sha256

    first.archive_path.write_bytes(b"tamper")
    with pytest.raises(th.TardisHistoricalError, match="SHA-256 mismatch"):
        th.download_archive(spec, tmp_path / "history", retrieve=retrieve)


def test_download_rejects_wrong_csv_schema(tmp_path: Path) -> None:
    spec = th.frozen_specs()[2]

    def retrieve(url: str, destination: Path) -> None:
        del url
        _write_fake_gzip(destination, "wrong,header")

    with pytest.raises(th.TardisHistoricalError, match="unexpected Tardis CSV schema"):
        th.download_archive(spec, tmp_path / "history", retrieve=retrieve)


def test_historical_storage_cannot_enter_prospective_campaign_root(tmp_path: Path) -> None:
    spec = th.frozen_specs()[0]

    with pytest.raises(th.TardisHistoricalError, match="must not be stored"):
        th.download_archive(spec, tmp_path / "stage2-development-campaign")


def test_status_reports_missing_archives_without_outcome_logic(tmp_path: Path) -> None:
    status = th.historical_status(tmp_path / "history")

    assert status["expected_archive_count"] == 80
    assert status["verified_archive_count"] == 0
    assert status["missing_archive_count"] == 80
    assert status["complete"] is False
