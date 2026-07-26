"""Shared lifecycle contracts for cache and data-plane work."""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any, ClassVar, Mapping

from pydantic import BaseModel, ConfigDict


class ArtifactState(str, Enum):
    PENDING = "pending"
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"


class ReplicaState(str, Enum):
    PENDING = "pending"
    COPYING = "copying"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"


class DataPlaneTaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class QueueWorkState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class TransitionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    previous_state: str
    state: str
    changed: bool


class InvalidStateTransition(ValueError):
    """Raised when a lifecycle transition is outside the declared contract."""

    def __init__(self, current_state: Enum, target_state: Enum, allowed_targets: set[Enum]):
        self.detail = {
            "code": "invalid_state_transition",
            "current_state": current_state.value,
            "target_state": target_state.value,
            "allowed_targets": sorted(state.value for state in allowed_targets),
        }
        super().__init__(str(self.detail))


class _StateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    _transitions: ClassVar[Mapping[Enum, set[Enum]]]

    def transition_to(self, target_state: Enum) -> tuple["_StateModel", TransitionResult]:
        state = self.state
        target = type(state)(target_state)
        if target == state:
            return self, TransitionResult(previous_state=state.value, state=state.value, changed=False)
        allowed = self._transitions.get(state, set())
        if target not in allowed:
            raise InvalidStateTransition(state, target, allowed)
        changed = self.model_copy(update={"state": target})
        return changed, TransitionResult(previous_state=state.value, state=target.value, changed=True)


ARTIFACT_TRANSITIONS = {
    ArtifactState.PENDING: {ArtifactState.BUILDING, ArtifactState.FAILED, ArtifactState.DELETING},
    ArtifactState.BUILDING: {ArtifactState.READY, ArtifactState.FAILED, ArtifactState.DELETING},
    ArtifactState.READY: {ArtifactState.FAILED, ArtifactState.DELETING},
    ArtifactState.FAILED: {ArtifactState.BUILDING, ArtifactState.DELETING},
    ArtifactState.DELETING: {ArtifactState.DELETED, ArtifactState.FAILED},
    ArtifactState.DELETED: set(),
}

REPLICA_TRANSITIONS = {
    ReplicaState.PENDING: {ReplicaState.COPYING, ReplicaState.FAILED, ReplicaState.DELETING},
    ReplicaState.COPYING: {ReplicaState.READY, ReplicaState.FAILED, ReplicaState.DELETING},
    ReplicaState.READY: {ReplicaState.FAILED, ReplicaState.DELETING},
    ReplicaState.FAILED: {ReplicaState.COPYING, ReplicaState.DELETING},
    ReplicaState.DELETING: {ReplicaState.DELETED, ReplicaState.FAILED},
    ReplicaState.DELETED: set(),
}

TASK_TRANSITIONS = {
    DataPlaneTaskState.PENDING: {DataPlaneTaskState.RUNNING, DataPlaneTaskState.CANCELLED, DataPlaneTaskState.EXPIRED},
    DataPlaneTaskState.RUNNING: {DataPlaneTaskState.SUCCEEDED, DataPlaneTaskState.FAILED, DataPlaneTaskState.CANCELLED, DataPlaneTaskState.EXPIRED},
    DataPlaneTaskState.FAILED: {DataPlaneTaskState.PENDING, DataPlaneTaskState.RUNNING, DataPlaneTaskState.CANCELLED, DataPlaneTaskState.EXPIRED},
    DataPlaneTaskState.SUCCEEDED: set(), DataPlaneTaskState.CANCELLED: set(), DataPlaneTaskState.EXPIRED: set(),
}

WORK_TRANSITIONS = {
    QueueWorkState.PENDING: {QueueWorkState.RUNNING, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED},
    QueueWorkState.RUNNING: {QueueWorkState.SUCCEEDED, QueueWorkState.FAILED, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED},
    QueueWorkState.FAILED: {QueueWorkState.PENDING, QueueWorkState.RUNNING, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED},
    QueueWorkState.SUCCEEDED: set(), QueueWorkState.CANCELLED: set(), QueueWorkState.SKIPPED: set(),
}


class CacheArtifact(_StateModel):
    artifact_id: str
    kid: str
    state: ArtifactState = ArtifactState.PENDING
    _transitions = ARTIFACT_TRANSITIONS


class CacheReplica(_StateModel):
    replica_id: str
    artifact_id: str
    location_key: str
    state: ReplicaState = ReplicaState.PENDING
    _transitions = REPLICA_TRANSITIONS


class DataPlaneTask(_StateModel):
    task_id: str
    state: DataPlaneTaskState = DataPlaneTaskState.PENDING
    _transitions = TASK_TRANSITIONS


class QueueWork(_StateModel):
    work_id: str
    state: QueueWorkState = QueueWorkState.PENDING
    _transitions = WORK_TRANSITIONS


def stable_id(kind: str, *identity: Any) -> str:
    """Return a deterministic identifier from an explicitly ordered identity tuple."""
    material = "\x1f".join([kind, *(str(value) for value in identity)])
    return f"{kind}_{hashlib.sha256(material.encode()).hexdigest()[:24]}"


def artifact_id(kid: str) -> str:
    return stable_id("artifact", kid)


def replica_id(artifact: str, location_key: str) -> str:
    return stable_id("replica", artifact, location_key)
