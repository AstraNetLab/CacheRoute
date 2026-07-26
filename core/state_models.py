"""Versioned, immutable lifecycle contracts for cache and data-plane work."""

from __future__ import annotations

import hashlib
import json
import uuid
from enum import Enum
from typing import ClassVar, Dict, Mapping, Optional, Set, Tuple, Type, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1"


class ArtifactState(str, Enum):
    PENDING = "pending"
    BUILDING = "building"
    STAGING = "staging"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"


class ReplicaState(str, Enum):
    PENDING = "pending"
    STAGING = "staging"
    READY = "ready"
    FAILED = "failed"
    EVICTING = "evicting"
    DELETED = "deleted"


class ReplicaHealth(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class DataPlaneTaskState(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class QueueWorkState(str, Enum):
    PENDING = "pending"
    BLOCKED = "blocked"
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


LifecycleState = ArtifactState | ReplicaState | DataPlaneTaskState | QueueWorkState

ARTIFACT_TRANSITIONS = {
    ArtifactState.PENDING: {ArtifactState.BUILDING, ArtifactState.FAILED, ArtifactState.DELETING},
    ArtifactState.BUILDING: {ArtifactState.STAGING, ArtifactState.FAILED, ArtifactState.DELETING},
    ArtifactState.STAGING: {ArtifactState.READY, ArtifactState.FAILED, ArtifactState.DELETING},
    ArtifactState.READY: {ArtifactState.BUILDING, ArtifactState.FAILED, ArtifactState.DELETING},
    ArtifactState.FAILED: {ArtifactState.BUILDING, ArtifactState.DELETING},
    ArtifactState.DELETING: {ArtifactState.DELETED, ArtifactState.FAILED},
    ArtifactState.DELETED: set(),
}
REPLICA_TRANSITIONS = {
    ReplicaState.PENDING: {ReplicaState.STAGING, ReplicaState.FAILED, ReplicaState.EVICTING},
    ReplicaState.STAGING: {ReplicaState.READY, ReplicaState.FAILED, ReplicaState.EVICTING},
    ReplicaState.READY: {ReplicaState.STAGING, ReplicaState.FAILED, ReplicaState.EVICTING},
    ReplicaState.FAILED: {ReplicaState.STAGING, ReplicaState.EVICTING},
    ReplicaState.EVICTING: {ReplicaState.DELETED, ReplicaState.FAILED},
    ReplicaState.DELETED: set(),
}
TASK_TRANSITIONS = {
    DataPlaneTaskState.PENDING: {DataPlaneTaskState.QUEUED, DataPlaneTaskState.CANCELLED},
    DataPlaneTaskState.QUEUED: {DataPlaneTaskState.LEASED, DataPlaneTaskState.RUNNING, DataPlaneTaskState.CANCELLED, DataPlaneTaskState.EXPIRED},
    DataPlaneTaskState.LEASED: {DataPlaneTaskState.RUNNING, DataPlaneTaskState.QUEUED, DataPlaneTaskState.CANCELLED, DataPlaneTaskState.EXPIRED},
    DataPlaneTaskState.RUNNING: {DataPlaneTaskState.SUCCEEDED, DataPlaneTaskState.FAILED, DataPlaneTaskState.CANCELLED},
    DataPlaneTaskState.FAILED: {DataPlaneTaskState.QUEUED, DataPlaneTaskState.CANCELLED},
    DataPlaneTaskState.SUCCEEDED: set(), DataPlaneTaskState.CANCELLED: set(), DataPlaneTaskState.EXPIRED: set(),
}
WORK_TRANSITIONS = {
    QueueWorkState.PENDING: {QueueWorkState.BLOCKED, QueueWorkState.READY, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED},
    QueueWorkState.BLOCKED: {QueueWorkState.READY, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED},
    QueueWorkState.READY: {QueueWorkState.QUEUED, QueueWorkState.RUNNING, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED},
    QueueWorkState.QUEUED: {QueueWorkState.RUNNING, QueueWorkState.CANCELLED},
    QueueWorkState.RUNNING: {QueueWorkState.SUCCEEDED, QueueWorkState.FAILED, QueueWorkState.CANCELLED},
    QueueWorkState.FAILED: {QueueWorkState.READY, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED},
    QueueWorkState.SUCCEEDED: set(), QueueWorkState.CANCELLED: set(), QueueWorkState.SKIPPED: set(),
}
TRANSITIONS: Mapping[Type[Enum], Mapping[Enum, Set[Enum]]] = {
    ArtifactState: ARTIFACT_TRANSITIONS, ReplicaState: REPLICA_TRANSITIONS,
    DataPlaneTaskState: TASK_TRANSITIONS, QueueWorkState: WORK_TRANSITIONS,
}
TERMINAL_STATES = {
    ArtifactState.DELETED, ReplicaState.DELETED,
    DataPlaneTaskState.SUCCEEDED, DataPlaneTaskState.CANCELLED, DataPlaneTaskState.EXPIRED,
    QueueWorkState.SUCCEEDED, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED,
}
RETRYABLE_STATES = {
    ArtifactState.FAILED, ReplicaState.FAILED, DataPlaneTaskState.FAILED, QueueWorkState.FAILED,
}


def allowed_target_states(state: LifecycleState) -> Tuple[LifecycleState, ...]:
    table = TRANSITIONS.get(type(state))
    if table is None:
        raise TypeError("state must be a lifecycle state enum")
    return tuple(sorted(table[state], key=lambda item: item.value))


def is_terminal_state(state: LifecycleState) -> bool:
    return state in TERMINAL_STATES


def is_retryable_state(state: LifecycleState) -> bool:
    return state in RETRYABLE_STATES


class InvalidStateTransitionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str = "invalid_state_transition"
    entity_type: str
    entity_id: str
    current_state: str
    target_state: str
    allowed_targets: Tuple[str, ...]
    reason: str
    terminal: bool
    retryable: bool


class InvalidStateTransition(ValueError):
    def __init__(self, detail: InvalidStateTransitionDetail):
        self.detail = detail
        super().__init__(detail.model_dump_json())


def validate_state_transition(
    current: LifecycleState, target: LifecycleState, *, entity_type: str, entity_id: str,
) -> bool:
    allowed = allowed_target_states(current)
    if type(target) is not type(current) or target not in allowed:
        target_value = target.value if isinstance(target, Enum) else str(target)
        raise InvalidStateTransition(InvalidStateTransitionDetail(
            entity_type=entity_type, entity_id=entity_id, current_state=current.value,
            target_state=target_value, allowed_targets=tuple(item.value for item in allowed),
            reason="terminal_state" if is_terminal_state(current) else "transition_not_allowed",
            terminal=is_terminal_state(current), retryable=is_retryable_state(current),
        ))
    return True


class TransitionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    previous_state: str
    state: str
    changed: bool


class _StateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = SCHEMA_VERSION
    _entity_type: ClassVar[str]
    _id_field: ClassVar[str]

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != SCHEMA_VERSION:
            raise ValueError("unsupported schema_version")
        return value

    def transition_to(self, target_state: LifecycleState):
        current = self.state
        if type(target_state) is type(current) and target_state == current:
            return self, TransitionResult(previous_state=current.value, state=current.value, changed=False)
        validate_state_transition(current, target_state, entity_type=self._entity_type, entity_id=getattr(self, self._id_field))
        return self.model_copy(update={"state": target_state}), TransitionResult(
            previous_state=current.value, state=target_state.value, changed=True,
        )


def _non_empty(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("identifier must not be empty")
    return value


class CacheArtifact(_StateModel):
    artifact_id: str
    knowledge_id: str
    capability_fingerprint: Optional[str] = None
    artifact_variant: str = "default"
    state: ArtifactState = ArtifactState.PENDING
    _entity_type = "cache_artifact"
    _id_field = "artifact_id"
    _ids = field_validator("artifact_id", "knowledge_id", "artifact_variant")(_non_empty)


class CacheReplica(_StateModel):
    replica_id: str
    artifact_id: str
    data_plane_id: Optional[str] = None
    backend_type: Optional[str] = None
    location_key: Optional[str] = None
    state: ReplicaState = ReplicaState.PENDING
    health: ReplicaHealth = ReplicaHealth.UNKNOWN
    _entity_type = "cache_replica"
    _id_field = "replica_id"
    _ids = field_validator("replica_id", "artifact_id")(_non_empty)


def _task_id() -> str:
    return f"dpt:{uuid.uuid4().hex}"


def _work_id() -> str:
    return f"qwork:{uuid.uuid4().hex}"


class DataPlaneTask(_StateModel):
    task_id: str = Field(default_factory=_task_id)
    operation: Optional[str] = None
    artifact_id: Optional[str] = None
    source_replica_id: Optional[str] = None
    target_replica_id: Optional[str] = None
    state: DataPlaneTaskState = DataPlaneTaskState.PENDING
    _entity_type = "data_plane_task"
    _id_field = "task_id"
    _id = field_validator("task_id")(_non_empty)


class QueueWork(_StateModel):
    work_id: str = Field(default_factory=_work_id)
    work_type: Optional[str] = None
    resource_class: Optional[str] = None
    state: QueueWorkState = QueueWorkState.PENDING
    _entity_type = "queue_work"
    _id_field = "work_id"
    _id = field_validator("work_id")(_non_empty)


def _digest(prefix: str, identity: Dict[str, Optional[str]]) -> str:
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}:sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def artifact_id(
    knowledge_id: str, capability_fingerprint: Optional[str] = None,
    artifact_variant: str = "default", schema_version: str = SCHEMA_VERSION,
) -> str:
    normalized = _non_empty(knowledge_id).strip()
    return _digest("artifact", {"schema_version": schema_version, "knowledge_id": normalized,
        "capability_fingerprint": capability_fingerprint, "artifact_variant": _non_empty(artifact_variant)})


def legacy_artifact_id(knowledge_id: str) -> str:
    return artifact_id(knowledge_id, capability_fingerprint=None)


def replica_id(
    artifact_id_value: str, data_plane_id: Optional[str] = None,
    backend_type: Optional[str] = None, location_key: Optional[str] = None,
) -> str:
    return _digest("replica", {"artifact_id": _non_empty(artifact_id_value),
        "data_plane_id": data_plane_id, "backend_type": backend_type, "location_key": location_key})
