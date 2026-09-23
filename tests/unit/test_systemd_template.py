from __future__ import annotations

from pathlib import Path


def test_systemd_template_is_public_only_and_graceful() -> None:
    unit = Path("deploy/systemd/quant-crypto-recorder.service").read_text(encoding="utf-8")

    assert "User=quantcrypto" in unit
    assert "Group=quantcrypto" in unit
    assert "WorkingDirectory=/opt/quant-crypto-engine" in unit
    assert "run-public-recorder --config /etc/quant-crypto-engine/public-recorder.json" in unit
    assert "Restart=on-failure" in unit
    assert "KillSignal=SIGTERM" in unit
    assert "TimeoutStopSec=30s" in unit
    assert "ProtectSystem=strict" in unit
    assert "ReadWritePaths=/var/lib/quant-crypto-engine" in unit
    assert "api_key" not in unit.lower()
    assert "private_key" not in unit.lower()
    assert "wallet" not in unit.lower()


def test_systemd_restart_delay_respects_adapter_connection_floor() -> None:
    unit = Path("deploy/systemd/quant-crypto-recorder.service").read_text(encoding="utf-8")
    line = next(value for value in unit.splitlines() if value.startswith("RestartSec="))
    seconds = float(line.removeprefix("RestartSec=").removesuffix("s"))

    assert seconds >= 2.0
