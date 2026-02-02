# proxy/strategy/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Protocol, Any


class InstanceLike(Protocol):
    instance_id: str
    host: str
    port: int
    weight: float  # 预留，RR 暂不使用


class BaseInstanceStrategy(ABC):
    """
    Proxy 侧 Instance 选择策略基类。

    约束：
    - 输入：当前存活实例列表（由 InstancePool.list(include_dead=False) 提供）
    - 输出：选择出的一个实例（host/port 等）
    - 不直接依赖 FastAPI / request，上层可把 req_obj 作为 hint 传进来
    """
    name: str = "base"

    @abstractmethod
    def select(self, instances: List[InstanceLike], hint: Optional[Any] = None) -> InstanceLike:
        raise NotImplementedError
