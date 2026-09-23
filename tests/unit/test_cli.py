from __future__ import annotations

import json

from cryptobot.cli import main


def test_validate_recorder_runtime_cli_is_network_free_and_machine_readable(
    capsys,
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
