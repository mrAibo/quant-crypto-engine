from __future__ import annotations

import json
from pathlib import Path

import pytest

import cryptobot.cli as cli
from cryptobot.cli import main
from cryptobot.research.tardis_historical_training import FeatureCacheBuildReport


def test_validate_recorder_runtime_cli_is_network_free_and_machine_readable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(
        [
            "validate-recorder-runtime",
            "--queue-capacity",
            "128",
            "--sync-every-frames",
            "32",
            "--shutdown-drain-timeout-seconds",
            "5",
            "--seal-on-shutdown",
            "--reconnect-base-seconds",
            "2",
            "--reconnect-max-seconds",
            "30",
            "--reconnect-jitter-fraction",
            "0.2",
            "--heartbeat-idle-seconds",
            "50",
            "--max-message-bytes",
            "1048576",
            "--receive-queue-high-water",
            "16",
            "--open-timeout-seconds",
            "10",
            "--close-timeout-seconds",
            "5",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["recorder"]["queue_capacity"] == 128
    assert payload["recorder"]["rollover_mode"] == "DISABLED"
    assert payload["reconnect"]["base_delay_seconds"] == 2.0
    assert payload["transport"]["heartbeat_idle_seconds"] == 50.0


def test_plan_retrospective_data_cli_is_non_gating(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "retrospective-plan.json"
    result = main(
        [
            "plan-retrospective-data",
            "--start-date",
            "2026-09-01",
            "--end-date",
            "2026-09-01",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    plan = json.loads(output.read_text(encoding="utf-8"))
    assert result == 0
    assert payload["status"] == "SUCCESS"
    assert payload["task_018_gate_eligibility"] == "EXCLUDED_FROM_TASK_018_FRONTIER_GATE"
    assert plan["task_018_gate_eligibility"] == "EXCLUDED_FROM_TASK_018_FRONTIER_GATE"


def test_development_campaign_cli_initializes_without_network(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "development"
    result = main(
        [
            "init-development-campaign",
            "--campaign-root",
            str(root),
            "--protocol",
            "artifacts/stage_2/development_campaign_protocol.json",
            "--runtime-config",
            "config/runtime/stage2-development-public.json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["status"] == "SUCCESS"
    assert payload["protocol_sha256"] == (
        "1ab9a735f512dd301392ba568b49ebd0f1e80d676f073b3d502bf73d111bc1d3"
    )

    result = main(["status-development-campaign", "--campaign-root", str(root)])
    status = json.loads(capsys.readouterr().out)
    assert result == 0
    assert status["campaign_state"] == "PRESTART"
    assert status["model_fitted"] is False


def test_tardis_feature_build_cli_reports_frozen_cache_digests(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = FeatureCacheBuildReport(
        protocol_sha256="p" * 64,
        lakehouse_manifest_sha256="l" * 64,
        parquet_set_sha256="q" * 64,
        cache_50s_sha256="a" * 64,
        cache_300s_sha256="b" * 64,
        row_count_50s=123,
        row_count_300s=45,
        day_counts_50s=(("2025-01-01", 123),),
        day_counts_300s=(("2025-01-01", 45),),
    )
    output = tmp_path / "feature-build.json"
    monkeypatch.setattr(cli, "build_feature_caches", lambda **kwargs: report)
    monkeypatch.setattr(
        cli,
        "write_feature_build_report",
        lambda received, path: Path(path),
    )

    result = main(
        [
            "build-tardis-training-features",
            "--catalog",
            "catalog.duckdb",
            "--lakehouse-manifest",
            "lakehouse.json",
            "--output-root",
            str(tmp_path / "features"),
            "--report-output",
            str(output),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["status"] == "SUCCESS"
    assert payload["cache_50s_sha256"] == "a" * 64
    assert payload["cache_300s_sha256"] == "b" * 64
    assert payload["row_count_50s"] == 123
    assert payload["row_count_300s"] == 45


def test_tardis_evaluate_cli_binds_feature_build_report_sha(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        cli,
        "load_feature_build_report",
        lambda path, expected_sha256: ("f" * 64, "a" * 64, "b" * 64),
    )

    class _Report:
        sha256 = "r" * 64
        decision = "STOP_HISTORICAL_MICROSTRUCTURE_DEVELOPMENT"
        selected_horizon_seconds = None

    def _evaluate(**kwargs: object) -> _Report:
        captured.update(kwargs)
        return _Report()

    monkeypatch.setattr(cli, "evaluate_historical_development", _evaluate)
    monkeypatch.setattr(
        cli,
        "write_development_report",
        lambda report, path: Path(path),
    )
    output = tmp_path / "development.json"

    result = main(
        [
            "evaluate-tardis-historical-development",
            "--feature-root",
            str(tmp_path / "features"),
            "--feature-build-report",
            str(tmp_path / "feature-build.json"),
            "--feature-build-report-sha256",
            "f" * 64,
            "--output",
            str(output),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert captured["feature_build_report_sha256"] == "f" * 64
    assert captured["expected_cache_50s_sha256"] == "a" * 64
    assert captured["expected_cache_300s_sha256"] == "b" * 64
    assert payload["feature_build_report_sha256"] == "f" * 64
    assert payload["decision"] == "STOP_HISTORICAL_MICROSTRUCTURE_DEVELOPMENT"


def test_development_closeout_cli_is_support_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "closeout"
    monkeypatch.setattr(
        cli,
        "closeout_development_campaign",
        lambda *args, **kwargs: {
            "report_path": str(output / "development-closeout-report.json"),
            "report_sha256": "r" * 64,
            "cache_50s_sha256": "a" * 64,
            "cache_300s_sha256": "b" * 64,
            "report": {
                "published_capture_coverage_fraction": "0.5",
                "published_segment_count": 100,
                "model_fitted": False,
            },
        },
    )

    result = main(
        [
            "closeout-development-campaign",
            "--campaign-root",
            str(tmp_path / "campaign"),
            "--output-root",
            str(output),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["status"] == "SUCCESS"
    assert payload["published_capture_coverage_fraction"] == "0.5"
    assert payload["published_segment_count"] == 100
    assert payload["model_fitted"] is False