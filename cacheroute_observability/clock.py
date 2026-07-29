"""Injectable clocks that keep correlation timestamps separate from durations."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable


@runtime_checkable
class TraceClock(Protocol):
    def utc_now(self) -> datetime: ...
    def monotonic_ns(self) -> int: ...


class SystemTraceClock:
    def utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic_ns(self) -> int:
        return time.perf_counter_ns()


class ManualTraceClock:
    def __init__(self, utc_value: datetime, monotonic_value: int = 0):
        if utc_value.tzinfo is None or utc_value.utcoffset() != timedelta(0):
            raise ValueError("utc_value must be timezone-aware UTC")
        if monotonic_value < 0:
            raise ValueError("monotonic_value must be non-negative")
        self._utc_value = utc_value
        self._monotonic_value = monotonic_value

    def utc_now(self) -> datetime:
        return self._utc_value

    def monotonic_ns(self) -> int:
        return self._monotonic_value

    def advance_ns(self, value: int) -> None:
        if value < 0:
            raise ValueError("monotonic advance must be non-negative")
        self._monotonic_value += value

    def advance_time(self, value: timedelta) -> None:
        if value < timedelta(0):
            raise ValueError("wall-clock advance must be non-negative")
        self._utc_value += value


__all__ = ["ManualTraceClock", "SystemTraceClock", "TraceClock"]
