"""Implements round-robin resource selection."""
# proxy/strategy/round_robin.py
from __future__ import annotations

"""Implements a round-robin selection strategy over currently available resources."""

import threading
from typing import List, Optional, Any

from .base import BaseInstanceStrategy, InstanceLike


class RoundRobinStrategy(BaseInstanceStrategy):
    name = "round_robin"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._idx = 0

    def select(self, instances: List[InstanceLike], hint: Optional[Any] = None) -> InstanceLike:
        if not instances:
            raise RuntimeError("no instances")
        with self._lock:
            # Keep logs and state updates bounded for experiments.
            i = self._idx % len(instances)
            self._idx += 1
            return instances[i]
