from __future__ import annotations

import pytest

from cryptobot.data.clock import (
    ClockSample,
    ClockValidationError,
    SystemClock,
    apparent_exchange_lag_ns,
    elapsed_ns,
)


def test_system_clock_returns_paired_sample_for_supplied_identity() -> None:
    sample = SystemClock(host_id="host-a", boot_id="boot-a").sample()

    assert sample.host_id == "host-a"
    assert sample.boot_id == "boot-a"
    assert sample.wall_ns > 0
    assert sample.mono_ns > 0


def test_elapsed_ns_uses_monotonic_clock_only_with_same_host_and_boot() -> None:
    start = ClockSample(wall_ns=1000, mono_ns=10, host_id="host", boot_id="boot")
    end = ClockSample(wall_ns=500, mono_ns=25, host_id="host", boot_id="boot")

    assert elapsed_ns(start, end) == 15


def test_elapsed_ns_rejects_different_boots() -> None:
    start = ClockSample(wall_ns=1000, mono_ns=10, host_id="host", boot_id="boot-a")
    end = ClockSample(wall_ns=1100, mono_ns=20, host_id="host", boot_id="boot-b")

    with pytest.raises(ClockValidationError, match="different host/boot"):
        elapsed_ns(start, end)


def test_elapsed_ns_rejects_backwards_monotonic_time() -> None:
    start = ClockSample(wall_ns=1000, mono_ns=20, host_id="host", boot_id="boot")
    end = ClockSample(wall_ns=1100, mono_ns=10, host_id="host", boot_id="boot")

    with pytest.raises(ClockValidationError, match="moved backwards"):
        elapsed_ns(start, end)


def test_apparent_exchange_lag_is_unknown_without_exchange_timestamp() -> None:
    assert apparent_exchange_lag_ns(None, 1_000_000) is None


def test_apparent_exchange_lag_may_be_negative_due_to_clock_offset() -> None:
    assert apparent_exchange_lag_ns(1_100, 1_000) == -100


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("wall_ns", {"wall_ns": -1, "mono_ns": 1, "host_id": "h", "boot_id": "b"}),
        ("mono_ns", {"wall_ns": 1, "mono_ns": -1, "host_id": "h", "boot_id": "b"}),
        ("host_id", {"wall_ns": 1, "mono_ns": 1, "host_id": "", "boot_id": "b"}),
        ("boot_id", {"wall_ns": 1, "mono_ns": 1, "host_id": "h", "boot_id": ""}),
    ],
)
def test_clock_sample_validation(field: str, kwargs: dict[str, object]) -> None:
    with pytest.raises(ClockValidationError, match=field):
        ClockSample(**kwargs)  # type: ignore[arg-type]
