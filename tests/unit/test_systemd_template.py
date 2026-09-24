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


def test_frontier_split_units_decouple_capture_from_processing() -> None:
    capture = Path("deploy/systemd/quant-frontier-capture.service").read_text(encoding="utf-8")
    processor = Path("deploy/systemd/quant-frontier-process.service").read_text(encoding="utf-8")
    capture_timer = Path("deploy/systemd/quant-frontier-capture.timer").read_text(encoding="utf-8")
    process_timer = Path("deploy/systemd/quant-frontier-process.timer").read_text(encoding="utf-8")

    assert "capture-frontier-segment" in capture
    assert "process-next-frontier-segment" not in capture
    assert "SEGMENT_SECONDS=900" in capture
    assert "process-next-frontier-segment" in processor
    assert "report-frontier-campaign" not in processor
    assert "Nice=10" in processor
    assert "OOMScoreAdjust=250" in processor
    assert "OnUnitInactiveSec=10s" in capture_timer
    assert "OnUnitInactiveSec=1min" in process_timer
    for unit in (capture, processor):
        assert "api_key" not in unit.lower()
        assert "private_key" not in unit.lower()
        assert "wallet" not in unit.lower()


def test_frontier_split_capture_systemd_is_near_continuous_and_public_only() -> None:
    service = Path("deploy/systemd/quant-frontier-capture.service").read_text(encoding="utf-8")
    timer = Path("deploy/systemd/quant-frontier-capture.timer").read_text(encoding="utf-8")

    assert "User=quantcrypto" in service
    assert "capture-frontier-segment" in service
    assert "process-next-frontier-segment" not in service
    assert "OnSuccess=quant-frontier-process.service" in service
    assert "SEGMENT_SECONDS=900" in service
    assert "ReadWritePaths=/var/lib/quant-crypto-engine" in service
    assert "OnUnitInactiveSec=10s" in timer
    assert "Unit=quant-frontier-capture.service" in timer
    assert "api_key" not in service.lower()
    assert "private_key" not in service.lower()
    assert "wallet" not in service.lower()


def test_frontier_split_processor_is_network_independent_from_capture() -> None:
    service = Path("deploy/systemd/quant-frontier-process.service").read_text(encoding="utf-8")

    assert "User=quantcrypto" in service
    assert "process-next-frontier-segment" in service
    assert "capture-frontier-segment" not in service
    assert "--config" not in service
    assert "report-frontier-campaign" not in service
    assert "ReadWritePaths=/var/lib/quant-crypto-engine" in service
