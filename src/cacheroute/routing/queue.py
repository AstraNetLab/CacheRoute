"""Dependency-light queue lifecycle models."""
from __future__ import annotations

from typing import ClassVar
from uuid import uuid4

from pydantic import AwareDatetime, Field, model_validator

from cacheroute.runtime import Snapshot, StateTransitionError, StrEnum
from cacheroute.runtime.state import nonempty, require_utc, utc_now


class QueueState(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    EXECUTING = "executing"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in (self.COMPLETED, self.FAILED, self.CANCELLED)

    @property
    def retryable(self) -> bool:
        return self is self.RETRY_WAIT

class QueueWork(Snapshot):
    _TRANSITIONS: ClassVar = {
        QueueState.QUEUED: {QueueState.CLAIMED, QueueState.CANCELLED},
        QueueState.CLAIMED: {QueueState.EXECUTING, QueueState.RETRY_WAIT, QueueState.CANCELLED},
        QueueState.EXECUTING: {QueueState.COMPLETED, QueueState.RETRY_WAIT, QueueState.FAILED, QueueState.CANCELLED},
        QueueState.RETRY_WAIT: {QueueState.QUEUED, QueueState.FAILED, QueueState.CANCELLED},
        QueueState.COMPLETED: set(), QueueState.FAILED: set(), QueueState.CANCELLED: set(),
    }
    work_id: str = Field(default_factory=lambda: f"queuework_{uuid4().hex}", pattern=r"^queuework_[0-9a-f]{32}$")
    idempotency_key: str
    cache_task_id: str = Field(pattern=r"^cacheop_[0-9a-f]{32}$")
    state: QueueState = QueueState.QUEUED
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def timestamp_order(self):
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")
        nonempty(self.idempotency_key)
        if self.updated_at < self.created_at: raise ValueError("updated_at must not precede created_at")
        return self

    def transition(self, state, *, at=None):
        requested = QueueState(state)
        if requested is self.state: return self
        allowed = self._TRANSITIONS[self.state]
        if requested not in allowed: raise StateTransitionError(type(self).__name__, self.state, requested, allowed)
        stamp = at or utc_now()
        require_utc(stamp, "transition timestamp")
        if stamp < self.updated_at: raise ValueError("transition timestamp must not move backwards")
        return type(self).model_validate(self.model_dump() | {"state": requested, "updated_at": stamp})

    @property
    def terminal(self): return self.state.terminal
    @property
    def retryable(self): return self.state.retryable

__all__ = ["QueueState", "QueueWork"]
