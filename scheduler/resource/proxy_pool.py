# scheduler/resource/proxy_pool.py
# -*- coding: utf-8 -*-
"""Maintains the in-memory Scheduler view of registered proxy resources and their dynamic load state."""

from __future__ import annotations

import time
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProxyLoad:
    """Maintains the in-memory Scheduler view of registered proxy resources and their dynamic load state."""
    # ---- static capability (register-time) ----
    max_capacity: int = 0      # Registration-related bookkeeping.

    instance_count: int = 0     # Registration-related bookkeeping.
    kv_mem_per_instance_gb: float = 0.0  # Registration-related bookkeeping.
    kv_cache_pool_gb: float = 0.0  # Maintains the existing proxy/scheduler experiment flow.

    # ---- dynamic load (heartbeat) ----
    inflight: int = 0          # Maintains the existing proxy/scheduler experiment flow.
    qps_1m: float = 0.0        # Maintains the existing proxy/scheduler experiment flow.
    gpu_util: float = 0.0      # Maintains the existing proxy/scheduler experiment flow.


@dataclass
class ProxyInfo:
    """Maintains the in-memory Scheduler view of registered proxy resources and their dynamic load state."""
    proxy_id: str
    host: str
    port: int
    endpoints: List[str] = field(default_factory=list)

    tags: List[str] = field(default_factory=list)
    weight: float = 1.0
    meta: Dict[str, Any] = field(default_factory=dict)
    kv_cache_update_policy: str = "lru"

    # Load-related state used by scheduling decisions.
    load: ProxyLoad = field(default_factory=ProxyLoad)

    # Heartbeat-related bookkeeping.
    registered_at: float = field(default_factory=lambda: time.time())
    last_seen_at: float = field(default_factory=lambda: time.time())

    def touch(self) -> None:
        """Maintains the in-memory Scheduler view of registered proxy resources and their dynamic load state."""
        self.last_seen_at = time.time()

    def is_alive(self, ttl_s: int, now: Optional[float] = None) -> bool:
        """Maintains the in-memory Scheduler view of registered proxy resources and their dynamic load state."""
        now = now or time.time()
        return (now - self.last_seen_at) <= ttl_s


class ProxyPool:
    """Maintains the in-memory Scheduler view of registered proxy resources and their dynamic load state."""
    def __init__(self, ttl_s: int = 30):
        self.ttl_s = ttl_s
        self._lock = asyncio.Lock()
        self._data: Dict[str, ProxyInfo] = {}

    async def upsert(self, info: ProxyInfo) -> None:
        """Maintains the in-memory Scheduler view of registered proxy resources and their dynamic load state."""
        async with self._lock:
            old = self._data.get(info.proxy_id)
            if old is None:
                self._data[info.proxy_id] = info
                return

            # Registration-related bookkeeping.
            info.registered_at = old.registered_at
            self._data[info.proxy_id] = info

    async def heartbeat(
        self,
        proxy_id: str,
        load: Optional[ProxyLoad] = None,
        meta_patch: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Maintains the in-memory Scheduler view of registered proxy resources and their dynamic load state."""
        async with self._lock:
            p = self._data.get(proxy_id)
            if not p:
                return False

            p.touch()
            if load is not None:
                p.load.inflight = int(load.inflight)
                p.load.qps_1m = float(load.qps_1m)
                p.load.gpu_util = float(load.gpu_util)
            if meta_patch:
                p.meta.update(dict(meta_patch))
            return True

    async def remove(self, proxy_id: str) -> None:
        """Maintains the in-memory Scheduler view of registered proxy resources and their dynamic load state."""
        async with self._lock:
            self._data.pop(proxy_id, None)

    async def get(self, proxy_id: str) -> Optional[ProxyInfo]:
        """Maintains the in-memory Scheduler view of registered proxy resources and their dynamic load state."""
        async with self._lock:
            return self._data.get(proxy_id)

    async def list(self, include_dead: bool = False) -> List[ProxyInfo]:
        """Maintains the in-memory Scheduler view of registered proxy resources and their dynamic load state."""
        async with self._lock:
            now = time.time()
            out: List[ProxyInfo] = []
            for p in self._data.values():
                alive = p.is_alive(self.ttl_s, now=now)
                if (not include_dead) and (not alive):
                    continue
                out.append(p)

            # Heartbeat-related bookkeeping.
            out.sort(key=lambda x: x.last_seen_at, reverse=True)
            return out

    async def inflight_delta(self, proxy_id: str, delta: int) -> bool:
        async with self._lock:
            p = self._data.get(proxy_id)
            if not p:
                return False
            v = int(p.load.inflight) + int(delta)
            if v < 0:
                v = 0
            p.load.inflight = v
            return True
