from __future__ import annotations

import json
from pathlib import Path

import pytest

from cryptobot.cli import main


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
