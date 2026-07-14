"""Implements round-robin resource selection."""
# scheduler/strategy/round_robin.py
from __future__ import annotations

"""Implements a round-robin selection strategy over currently available resources."""

import threading

from typing import Any, Dict, List, Optional, Tuple
from .base import ProxySelectionStrategy


class RoundRobinStrategy(ProxySelectionStrategy):
    """Implements a round-robin selection strategy over currently available resources."""

    name: str = "round_robin"

    def __init__(self):
        self._lock = threading.Lock()
        self._kdn_cursor = 0
        self._proxy_cursor = 0

    def select(
        self,
        kdns: List[Dict[str, Any]],
        proxies: List[Dict[str, Any]],
        payload: Dict[str, Any],
        url_path: str,
        user_addr: str,
        request_ctx: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        chosen_kdn = None
        chosen_proxy = None

        with self._lock:
            if kdns:
                ki = self._kdn_cursor % len(kdns)
                self._kdn_cursor += 1
                chosen_kdn = kdns[ki]

            if proxies:
                pi = self._proxy_cursor % len(proxies)
                self._proxy_cursor += 1
                chosen_proxy = proxies[pi]

        return chosen_kdn, chosen_proxy
