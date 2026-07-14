"""Defines strategy interfaces for resource selection."""
# scheduler/strategy/base.py
from __future__ import annotations

"""Defines the base strategy interfaces used by Scheduler or proxy selection policies."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class ProxySelectionStrategy(ABC):
    """Defines the base strategy interfaces used by Scheduler or proxy selection policies."""

    name: str = "base"

    @abstractmethod
    def select(
            self,
            kdns: List[Dict[str, Any]],
            proxies: List[Dict[str, Any]],
            payload: Dict[str, Any],
            url_path: str,
            user_addr: str,
            request_ctx: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        raise NotImplementedError
