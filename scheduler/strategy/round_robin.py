# scheduler/strategy/round_robin.py
from __future__ import annotations

import threading

from typing import Any, Dict, List, Optional
from .base import ProxySelectionStrategy



class RoundRobinStrategy(ProxySelectionStrategy):
    """
    最简单的 round-robin：
    - 在“当前存活 proxy 列表”上做循环取模
    - 用 asyncio.Lock 保护 index，避免并发请求打乱顺序
    """

    name: str = "round_robin"

    def __init__(self):
        self._lock = threading.Lock()
        self._cursor = 0

    def select(self, proxies: List[Dict[str, Any]], payload: Dict[str, Any], url_path: str, user_addr: str) -> Optional[Dict[str, Any]]:
        if not proxies:
            return None
        with self._lock:
            idx = self._cursor % len(proxies)
            self._cursor += 1
        return proxies[idx]
