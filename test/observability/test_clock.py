from datetime import timedelta

import pytest

from cacheroute_observability import ManualTraceClock, SystemTraceClock


def test_manual_clock_advances_independently(now):
    clock = ManualTraceClock(now, 10)
    clock.advance_ns(0)
    assert clock.monotonic_ns() == 10
    clock.advance_ns(5)
    clock.advance_time(timedelta(seconds=2))
    assert clock.monotonic_ns() == 15
    assert clock.utc_now() == now + timedelta(seconds=2)


def test_clock_rejects_invalid_values(now):
    with pytest.raises(ValueError):
        ManualTraceClock(now.replace(tzinfo=None))
    clock = ManualTraceClock(now)
    with pytest.raises(ValueError):
        clock.advance_ns(-1)
    assert SystemTraceClock().monotonic_ns() >= 0
