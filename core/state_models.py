"""Shared, policy-neutral lifecycle contracts for cache and execution objects."""
from __future__ import annotations

import hashlib
import json
import uuid
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, Type, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _WireEnum(str, Enum):
    pass


class ArtifactState(_WireEnum):
    PENDING = "pending"
    BUILDING = "building"
    STAGING = "staging"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"


class ReplicaState(_WireEnum):
    PENDING = "pending"
    STAGING = "staging"
    READY = "ready"
    FAILED = "failed"
    EVICTING = "evicting"
    DELETED = "deleted"


class ReplicaHealth(_WireEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class DataPlaneTaskState(_WireEnum):
    PENDING = "pending"
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class QueueWorkState(_WireEnum):
    PENDING = "pending"
    BLOCKED = "blocked"
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


_TRANSITIONS: Dict[Type[_WireEnum], Mapping[_WireEnum, Set[_WireEnum]]] = {
    ArtifactState: {
        ArtifactState.PENDING: {ArtifactState.BUILDING, ArtifactState.FAILED, ArtifactState.DELETING},
        ArtifactState.BUILDING: {ArtifactState.STAGING, ArtifactState.FAILED, ArtifactState.DELETING},
        ArtifactState.STAGING: {ArtifactState.READY, ArtifactState.FAILED, ArtifactState.DELETING},
        ArtifactState.READY: {ArtifactState.BUILDING, ArtifactState.FAILED, ArtifactState.DELETING},
        ArtifactState.FAILED: {ArtifactState.BUILDING, ArtifactState.DELETING},
        ArtifactState.DELETING: {ArtifactState.DELETED, ArtifactState.FAILED},
        ArtifactState.DELETED: set(),
    },
    ReplicaState: {
        ReplicaState.PENDING: {ReplicaState.STAGING, ReplicaState.FAILED, ReplicaState.EVICTING},
        ReplicaState.STAGING: {ReplicaState.READY, ReplicaState.FAILED, ReplicaState.EVICTING},
        ReplicaState.READY: {ReplicaState.STAGING, ReplicaState.FAILED, ReplicaState.EVICTING},
        ReplicaState.FAILED: {ReplicaState.STAGING, ReplicaState.EVICTING},
        ReplicaState.EVICTING: {ReplicaState.DELETED, ReplicaState.FAILED},
        ReplicaState.DELETED: set(),
    },
    DataPlaneTaskState: {
        DataPlaneTaskState.PENDING: {DataPlaneTaskState.QUEUED, DataPlaneTaskState.CANCELLED},
        DataPlaneTaskState.QUEUED: {DataPlaneTaskState.LEASED, DataPlaneTaskState.RUNNING, DataPlaneTaskState.CANCELLED, DataPlaneTaskState.EXPIRED},
        DataPlaneTaskState.LEASED: {DataPlaneTaskState.RUNNING, DataPlaneTaskState.QUEUED, DataPlaneTaskState.CANCELLED, DataPlaneTaskState.EXPIRED},
        DataPlaneTaskState.RUNNING: {DataPlaneTaskState.SUCCEEDED, DataPlaneTaskState.FAILED, DataPlaneTaskState.CANCELLED},
        DataPlaneTaskState.FAILED: {DataPlaneTaskState.QUEUED, DataPlaneTaskState.CANCELLED},
        DataPlaneTaskState.SUCCEEDED: set(), DataPlaneTaskState.CANCELLED: set(), DataPlaneTaskState.EXPIRED: set(),
    },
    QueueWorkState: {
        QueueWorkState.PENDING: {QueueWorkState.BLOCKED, QueueWorkState.READY, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED},
        QueueWorkState.BLOCKED: {QueueWorkState.READY, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED},
        QueueWorkState.READY: {QueueWorkState.QUEUED, QueueWorkState.RUNNING, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED},
        QueueWorkState.QUEUED: {QueueWorkState.RUNNING, QueueWorkState.CANCELLED},
        QueueWorkState.RUNNING: {QueueWorkState.SUCCEEDED, QueueWorkState.FAILED, QueueWorkState.CANCELLED},
        QueueWorkState.FAILED: {QueueWorkState.READY, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED},
        QueueWorkState.SUCCEEDED: set(), QueueWorkState.CANCELLED: set(), QueueWorkState.SKIPPED: set(),
    },
}

_TERMINAL = {
    ArtifactState: {ArtifactState.DELETED}, ReplicaState: {ReplicaState.DELETED},
    DataPlaneTaskState: {DataPlaneTaskState.SUCCEEDED, DataPlaneTaskState.CANCELLED, DataPlaneTaskState.EXPIRED},
    QueueWorkState: {QueueWorkState.SUCCEEDED, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED},
}
_RETRYABLE = {
    ArtifactState: {ArtifactState.FAILED}, ReplicaState: {ReplicaState.FAILED},
    DataPlaneTaskState: {DataPlaneTaskState.FAILED}, QueueWorkState: {QueueWorkState.FAILED},
}


class StateTransitionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = "invalid_state_transition"
    entity_type: str
    entity_id: str
    current_state: str
    target_state: str
    allowed_targets: List[str] = Field(default_factory=list)
    reason: str
    terminal: bool
    retryable: bool


class StateTransitionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changed: bool
    current_state: str
    target_state: str


class InvalidStateTransition(Exception):
    def __init__(self, detail: StateTransitionDetail):
        self.detail = detail
        super().__init__(detail.model_dump_json())


S = TypeVar("S", bound=_WireEnum)


def allowed_target_states(state: S) -> Tuple[S, ...]:
    return tuple(sorted(_TRANSITIONS[type(state)][state], key=lambda item: item.value))  # type: ignore[return-value]


def is_terminal_state(state: _WireEnum) -> bool:
    return state in _TERMINAL[type(state)]


def is_retryable_state(state: _WireEnum) -> bool:
    return state in _RETRYABLE[type(state)]


def validate_state_transition(entity_type: str, entity_id: str, current: S, target: S) -> StateTransitionResult:
    if type(current) is not type(target):
        raise TypeError("current and target states must use the same state enum")
    if current == target:
        return StateTransitionResult(changed=False, current_state=current.value, target_state=target.value)
    if target not in _TRANSITIONS[type(current)][current]:
        raise InvalidStateTransition(StateTransitionDetail(
            entity_type=entity_type, entity_id=entity_id, current_state=current.value,
            target_state=target.value, allowed_targets=[item.value for item in allowed_target_states(current)],
            reason="terminal_state" if is_terminal_state(current) else "transition_not_allowed",
            terminal=is_terminal_state(current), retryable=is_retryable_state(current),
        ))
    return StateTransitionResult(changed=True, current_state=current.value, target_state=target.value)


def _canonical_id(prefix: str, values: Dict[str, Any]) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}:sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _required_text(value: str, name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


def _non_secret_location(value: str) -> str:
    normalized = _required_text(value, "location_key")
    lowered = normalized.lower()
    if "://" in normalized or "password=" in lowered or "credential=" in lowered:
        raise ValueError("location_key must be an opaque, non-secret identity")
    return normalized


def generate_artifact_id(knowledge_id: str, capability_fingerprint: Optional[str], artifact_variant: str = "default", schema_version: str = "1") -> str:
    return _canonical_id("artifact", {
        "artifact_variant": _required_text(artifact_variant, "artifact_variant"),
        "capability_fingerprint": capability_fingerprint.strip() if capability_fingerprint else None,
        "knowledge_id": _required_text(knowledge_id, "knowledge_id").lower(),
        "schema_version": _required_text(schema_version, "schema_version"),
    })


def generate_legacy_artifact_id(knowledge_id: str, artifact_variant: str = "default", schema_version: str = "1") -> str:
    """Generate an ID while explicitly retaining unknown compatibility."""
    return generate_artifact_id(knowledge_id, None, artifact_variant, schema_version)


def generate_replica_id(artifact_id: str, data_plane_id: Optional[str], backend_type: Optional[str], location_key: Optional[str]) -> str:
    return _canonical_id("replica", {
        "artifact_id": _required_text(artifact_id, "artifact_id"),
        "backend_type": backend_type.strip() if backend_type else None,
        "data_plane_id": data_plane_id.strip() if data_plane_id else None,
        "location_key": _non_secret_location(location_key) if location_key else None,
    })


def generate_data_plane_task_id() -> str:
    return f"dpt:{uuid.uuid4().hex}"


def generate_queue_work_id() -> str:
    return f"qwork:{uuid.uuid4().hex}"


class _StateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("schema_version", check_fields=False)
    @classmethod
    def _nonempty_schema(cls, value: str) -> str:
        return _required_text(value, "schema_version")

    def _transition(self, entity_type: str, entity_id: str, target: _WireEnum):
        result = validate_state_transition(entity_type, entity_id, self.state, target)
        return self.model_copy(update={"state": target}), result


class CacheArtifact(_StateModel):
    schema_version: str = "1"
    artifact_id: str
    knowledge_id: str
    capability_fingerprint: Optional[str] = None
    artifact_variant: str = "default"
    state: ArtifactState = ArtifactState.PENDING

    @field_validator("artifact_id", "knowledge_id", "artifact_variant")
    @classmethod
    def _nonempty(cls, value: str) -> str:
        return _required_text(value, "identifier")

    def transition_to(self, target: ArtifactState):
        return self._transition("artifact", self.artifact_id, target)


class CacheReplica(_StateModel):
    schema_version: str = "1"
    replica_id: str
    artifact_id: str
    data_plane_id: Optional[str] = None
    backend_type: Optional[str] = None
    location_key: Optional[str] = None
    state: ReplicaState = ReplicaState.PENDING
    health: ReplicaHealth = ReplicaHealth.UNKNOWN

    @field_validator("replica_id", "artifact_id")
    @classmethod
    def _nonempty(cls, value: str) -> str:
        return _required_text(value, "identifier")

    @field_validator("location_key")
    @classmethod
    def _opaque_location(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _non_secret_location(value)

    def transition_to(self, target: ReplicaState):
        return self._transition("replica", self.replica_id, target)


class DataPlaneTask(_StateModel):
    schema_version: str = "1"
    task_id: str = Field(default_factory=generate_data_plane_task_id)
    operation: Optional[str] = None
    artifact_id: Optional[str] = None
    source_replica_id: Optional[str] = None
    target_replica_id: Optional[str] = None
    state: DataPlaneTaskState = DataPlaneTaskState.PENDING

    @field_validator("task_id")
    @classmethod
    def _nonempty(cls, value: str) -> str:
        return _required_text(value, "task_id")

    def transition_to(self, target: DataPlaneTaskState):
        return self._transition("data_plane_task", self.task_id, target)


class QueueWork(_StateModel):
    schema_version: str = "1"
    work_id: str = Field(default_factory=generate_queue_work_id)
    work_type: Optional[str] = None
    resource_class: Optional[str] = None
    state: QueueWorkState = QueueWorkState.PENDING

    @field_validator("work_id")
    @classmethod
    def _nonempty(cls, value: str) -> str:
        return _required_text(value, "work_id")

    def transition_to(self, target: QueueWorkState):
        return self._transition("queue_work", self.work_id, target)
