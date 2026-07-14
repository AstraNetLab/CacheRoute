"""Defines strategy interfaces for resource selection."""
# proxy/strategy/base.py
from __future__ import annotations

"""Defines the base strategy interfaces used by Scheduler or proxy selection policies."""

from abc import ABC, abstractmethod
from typing import List, Optional, Protocol, Any


class InstanceLike(Protocol):
    instance_id: str
    host: str
    port: int
    weight: float  # Reserved for future extension.


class BaseInstanceStrategy(ABC):
    """Defines the base strategy interfaces used by Scheduler or proxy selection policies."""
    name: str = "base"

    @abstractmethod
    def select(self, instances: List[InstanceLike], hint: Optional[Any] = None) -> InstanceLike:
        raise NotImplementedError
