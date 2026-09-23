from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import time


class ClockValidationError(ValueError):
    """Raised when clock samples cannot be compared safely."""


@dataclass(frozen=True, slots=True)
class ClockSample:
    wall_ns: int
    mono_ns: int
    host_id: str
    boot_id: str

    def __post_init__(self) -> None:
        if isinstance(self.wall_ns, bool) or not isinstance(self.wall_ns, int) or self.wall_ns < 0:
            raise ClockValidationError("wall_ns must be a non-negative integer")
        if isinstance(self.mono_ns, bool) or not isinstance(self.mono_ns, int) or self.mono_ns < 0:
            raise ClockValidationError("mono_ns must be a non-negative integer")
        if not self.host_id.strip():
            raise ClockValidationError("host_id must be non-empty")
        if not self.boot_id.strip():
            raise ClockValidationError("boot_id must be non-empty")


class Clock(Protocol):
    def sample(self) -> ClockSample:
        """Return paired wall/monotonic readings for one host/boot."""


@dataclass(frozen=True, slots=True)
class SystemClock:
    host_id: str
    boot_id: str

    def __post_init__(self) -> None:
        if not self.host_id.strip():
            raise ClockValidationError("host_id must be non-empty")
        if not self.boot_id.strip():
            raise ClockValidationError("boot_id must be non-empty")

    def sample(self) -> ClockSample:
        mono_before = time.monotonic_ns()
        wall_ns = time.time_ns()
        mono_after = time.monotonic_ns()
        mono_ns = mono_before + ((mono_after - mono_before) // 2)
        return ClockSample(
            wall_ns=wall_ns,
            mono_ns=mono_ns,
            host_id=self.host_id,
            boot_id=self.boot_id,
        )


def elapsed_ns(start: ClockSample, end: ClockSample) -> int:
    if start.host_id != end.host_id or start.boot_id != end.boot_id:
        raise ClockValidationError("monotonic samples from different host/boot cannot be compared")
    if end.mono_ns < start.mono_ns:
        raise ClockValidationError("monotonic clock moved backwards")
    return end.mono_ns - start.mono_ns


def apparent_exchange_lag_ns(exchange_ts_ns: int | None, recv_wall_ns: int) -> int | None:
    if isinstance(recv_wall_ns, bool) or not isinstance(recv_wall_ns, int) or recv_wall_ns < 0:
        raise ClockValidationError("recv_wall_ns must be a non-negative integer")
    if exchange_ts_ns is None:
        return None
    if (
        isinstance(exchange_ts_ns, bool)
        or not isinstance(exchange_ts_ns, int)
        or exchange_ts_ns < 0
    ):
        raise ClockValidationError("exchange_ts_ns must be null or a non-negative integer")
    return recv_wall_ns - exchange_ts_ns
