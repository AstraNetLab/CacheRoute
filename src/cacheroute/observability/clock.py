"""Clock boundary separating correlation timestamps from elapsed time."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol
import time


class TraceClock(Protocol):
    def utc_now(self) -> datetime: ...
    def monotonic_ns(self) -> int: ...


class SystemTraceClock:
    def utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic_ns(self) -> int:
        return time.perf_counter_ns()


class ManualTraceClock:
    """Deterministic test clock whose two time domains move explicitly."""

    def __init__(self, wall_time: datetime, monotonic_ns: int = 0):
        if wall_time.utcoffset() != timedelta(0):
            raise ValueError("wall_time must use UTC")
        if monotonic_ns < 0:
            raise ValueError("monotonic_ns must be non-negative")
        self._wall_time = wall_time
        self._monotonic_ns = monotonic_ns

    def utc_now(self) -> datetime:
        return self._wall_time

    def monotonic_ns(self) -> int:
        return self._monotonic_ns

    def advance(self, *, nanoseconds: int = 0, wall_time: timedelta | None = None) -> None:
        if nanoseconds < 0 or (wall_time is not None and wall_time < timedelta(0)):
            raise ValueError("clock movement must not be negative")
        self._monotonic_ns += nanoseconds
        self._wall_time += wall_time if wall_time is not None else timedelta(0)


__all__ = ["TraceClock", "SystemTraceClock", "ManualTraceClock"]
