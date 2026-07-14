# proxy/resource/hb_log.py
from __future__ import annotations

"""Aggregates heartbeat and refresh outcomes into compact periodic status logs."""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class HBWindow:
    total: int = 0
    ok: int = 0
    fail: int = 0
    last_err: Optional[str] = None


class HeartbeatReporter:
    """Aggregates heartbeat and refresh outcomes into compact periodic status logs."""

    def __init__(self, interval_s: float = 30.0):
        self.interval_s = float(interval_s)
        self._lock = asyncio.Lock()
        self._win = HBWindow()
        self._t0 = time.time()

    async def record(self, ok: bool, err: Optional[str] = None) -> None:
        async with self._lock:
            self._win.total += 1
            if ok:
                self._win.ok += 1
            else:
                self._win.fail += 1
                if err:
                    self._win.last_err = err[:200]  # Maintains the existing proxy/scheduler experiment flow.

    async def snapshot_and_reset(self) -> tuple[float, HBWindow]:
        async with self._lock:
            now = time.time()
            dur = now - self._t0
            w = self._win
            self._win = HBWindow()
            self._t0 = now
            return dur, w


async def hb_report_loop(
    reporter: HeartbeatReporter,
    logger,
    proxy_id: str,
    stop_event: asyncio.Event,
) -> None:
    """Aggregates heartbeat and refresh outcomes into compact periodic status logs."""
    while not stop_event.is_set():
        await asyncio.sleep(reporter.interval_s)
        dur, w = await reporter.snapshot_and_reset()

        # Heartbeat-related bookkeeping.
        if w.total == 0:
            continue

        # Maintains the existing proxy/scheduler experiment flow.
        if w.fail <= 0:
            continue

        lines = []
        lines.append("------ [Proxy HBReport] ------")
        lines.append(f"proxy_id={proxy_id} window_s={dur:.1f}")
        lines.append(f"heartbeat ok/total={w.ok}/{w.total} fail={w.fail}")
        if w.last_err:
            lines.append(f"last_err={w.last_err}")
        lines.append("------------------------------")

        logger.warning("\n".join(lines))
