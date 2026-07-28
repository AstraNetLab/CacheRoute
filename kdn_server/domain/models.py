"""Versioned, storage-neutral domain values used by the KDN control plane.

These models deliberately describe identities, observations, and work.  They do
not describe the bytes or backend-private addressing used to store a KV cache.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, ClassVar, Mapping
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stable_id(kind: str, *parts: object) -> str:
    value = "|".join(str(part) for part in parts)
    return f"{kind}_{uuid5(NAMESPACE_URL, f'cacheroute:v1:{kind}:{value}').hex}"


class _StringEnum(str, Enum):
    pass


class RuntimeProfile(_StringEnum):
    V1 = "v1"
    LEGACY = "legacy"
    TEST_MOCK = "test/mock"
    AUTO = "auto"

    @classmethod
    def resolve_auto(
        cls, value: "RuntimeProfile | str", *, v1_available: bool = False
    ) -> "RuntimeProfile":
        """Resolve the startup-only ``auto`` value to a persistable profile."""
        profile = cls(value)
        if profile is cls.AUTO:
            return cls.V1 if v1_available else cls.LEGACY
        return profile

    @property
    def persistable(self) -> bool:
        return self is not self.AUTO


class LMCacheProfile(_StringEnum):
    MP_HTTP_API = "mp_http_api"
    MP_COORDINATOR = "mp_coordinator"
    MP_SDK = "mp_sdk"
    MP_METRICS_EVENTS = "mp_metrics_events"
    LEGACY_GATEWAY = "legacy_gateway"
    MOCK = "mock"
    UNKNOWN_FUTURE = "unknown_future"


class ObservationSource(_StringEnum):
    HTTP_API = "http_api"
    COORDINATOR = "coordinator"
    SDK = "sdk"
    METRICS_EVENT = "metrics_event"
    LEGACY_GATEWAY = "legacy_gateway"
    MOCK = "mock"


class ObservationConfidence(_StringEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CacheOperationType(_StringEnum):
    LOOKUP = "lookup"
    PREFETCH = "prefetch"
    PIN = "pin"
    UNPIN = "unpin"
    CLEAR = "clear"
    REBUILD = "rebuild"
    OBSERVE = "observe"


class CacheOperationState(_StringEnum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.CANCELLED}

    @property
    def retryable(self) -> bool:
        return self in {self.PENDING, self.RETRY_WAIT}


class QueueState(_StringEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {self.COMPLETED, self.FAILED, self.CANCELLED}


class StateTransitionError(ValueError):
    """Machine-readable rejection of a domain state transition."""

    def __init__(self, model: str, current: Enum, requested: Enum, allowed: set[Enum]):
        self.model = model
        self.current_state = current.value
        self.requested_state = requested.value
        self.allowed_states = tuple(sorted(item.value for item in allowed))
        super().__init__(
            f"invalid {model} transition {current.value!r} -> {requested.value!r}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "invalid_state_transition",
            "model": self.model,
            "current_state": self.current_state,
            "requested_state": self.requested_state,
            "allowed_states": list(self.allowed_states),
        }


class _Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", use_enum_values=False)

    @field_validator("runtime_profile", check_fields=False)
    @classmethod
    def _reject_auto(cls, value: RuntimeProfile) -> RuntimeProfile:
        if value is RuntimeProfile.AUTO:
            raise ValueError("runtime_profile 'auto' is startup-only and cannot persist")
        return value

    def to_json(self) -> str:
        return self.model_dump_json()


class CacheArtifact(_Snapshot):
    """Logical cache artifact identity; contains no cache bytes or storage keys."""

    artifact_id: str | None = None
    knowledge_id: str
    model_id: str
    runtime_profile: RuntimeProfile
    format_version: str = "v1"
    created_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def _derive_id(self) -> "CacheArtifact":
        expected = _stable_id(
            "artifact", self.knowledge_id, self.model_id, self.runtime_profile.value,
            self.format_version,
        )
        if self.artifact_id is None:
            object.__setattr__(self, "artifact_id", expected)
        return self


class LMCacheEndpoint(_Snapshot):
    endpoint_id: str | None = None
    name: str
    generation: int = Field(default=1, ge=1)
    runtime_profile: RuntimeProfile
    lmcache_profile: LMCacheProfile
    adapter: str | None = None
    tier: str | None = None

    @model_validator(mode="after")
    def _derive_id(self) -> "LMCacheEndpoint":
        if self.endpoint_id is None:
            object.__setattr__(self, "endpoint_id", _stable_id("endpoint", self.name))
        return self

    def next_generation(self) -> "LMCacheEndpoint":
        return self.model_copy(update={"generation": self.generation + 1})


class CacheReplicaObservation(_Snapshot):
    observation_id: str | None = None
    artifact_id: str
    available: bool
    source: ObservationSource
    endpoint_id: str
    endpoint_generation: int = Field(ge=1)
    runtime_profile: RuntimeProfile
    lmcache_profile: LMCacheProfile
    adapter: str | None = None
    tier: str | None = None
    observed_at: datetime = Field(default_factory=_utc_now)
    expires_at: datetime
    confidence: ObservationConfidence = ObservationConfidence.MEDIUM

    @model_validator(mode="after")
    def _validate_observation(self) -> "CacheReplicaObservation":
        if self.expires_at <= self.observed_at:
            raise ValueError("expires_at must be later than observed_at")
        if self.observation_id is None:
            object.__setattr__(self, "observation_id", _stable_id(
                "observation", self.artifact_id, self.endpoint_id,
                self.endpoint_generation, self.observed_at.isoformat(),
            ))
        return self

    @classmethod
    def with_ttl(cls, *, ttl: timedelta, **values: Any) -> "CacheReplicaObservation":
        observed_at = values.pop("observed_at", _utc_now())
        return cls(observed_at=observed_at, expires_at=observed_at + ttl, **values)

    def is_fresh(self, at: datetime | None = None) -> bool:
        return (at or _utc_now()) < self.expires_at

    def applies_to(self, endpoint: LMCacheEndpoint, at: datetime | None = None) -> bool:
        return (
            self.endpoint_id == endpoint.endpoint_id
            and self.endpoint_generation == endpoint.generation
            and self.is_fresh(at)
        )

    @property
    def kv_ready(self) -> int:
        """Read-only compatibility projection; never persisted as source state."""
        return int(self.available and self.is_fresh())


class CacheOperationTask(_Snapshot):
    _TRANSITIONS: ClassVar[Mapping[CacheOperationState, set[CacheOperationState]]] = {
        CacheOperationState.PENDING: {CacheOperationState.RUNNING, CacheOperationState.CANCELLED},
        CacheOperationState.RUNNING: {CacheOperationState.SUCCEEDED, CacheOperationState.RETRY_WAIT, CacheOperationState.FAILED, CacheOperationState.CANCELLED},
        CacheOperationState.RETRY_WAIT: {CacheOperationState.RUNNING, CacheOperationState.CANCELLED, CacheOperationState.FAILED},
        CacheOperationState.SUCCEEDED: set(), CacheOperationState.FAILED: set(), CacheOperationState.CANCELLED: set(),
    }
    task_id: str = Field(default_factory=lambda: f"cacheop_{uuid4().hex}")
    operation: CacheOperationType
    artifact_id: str
    endpoint_id: str | None = None
    state: CacheOperationState = CacheOperationState.PENDING
    attempt: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    def transition(self, state: CacheOperationState | str, *, at: datetime | None = None) -> "CacheOperationTask":
        requested = CacheOperationState(state)
        if requested is self.state:
            return self
        allowed = self._TRANSITIONS[self.state]
        if requested not in allowed:
            raise StateTransitionError("CacheOperationTask", self.state, requested, allowed)
        attempt = self.attempt + int(requested is CacheOperationState.RUNNING)
        return self.model_copy(update={"state": requested, "attempt": attempt, "updated_at": at or _utc_now()})

    @property
    def terminal(self) -> bool:
        return self.state.terminal

    @property
    def retryable(self) -> bool:
        return self.state.retryable


class QueueWork(_Snapshot):
    _TRANSITIONS: ClassVar[Mapping[QueueState, set[QueueState]]] = {
        QueueState.QUEUED: {QueueState.CLAIMED, QueueState.CANCELLED},
        QueueState.CLAIMED: {QueueState.EXECUTING, QueueState.QUEUED, QueueState.CANCELLED},
        QueueState.EXECUTING: {QueueState.COMPLETED, QueueState.FAILED, QueueState.CANCELLED},
        QueueState.COMPLETED: set(), QueueState.FAILED: {QueueState.QUEUED}, QueueState.CANCELLED: set(),
    }
    work_id: str = Field(default_factory=lambda: f"queuework_{uuid4().hex}")
    cache_task_id: str
    state: QueueState = QueueState.QUEUED
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    def transition(self, state: QueueState | str, *, at: datetime | None = None) -> "QueueWork":
        requested = QueueState(state)
        if requested is self.state:
            return self
        allowed = self._TRANSITIONS[self.state]
        if requested not in allowed:
            raise StateTransitionError("QueueWork", self.state, requested, allowed)
        return self.model_copy(update={"state": requested, "updated_at": at or _utc_now()})

    @property
    def terminal(self) -> bool:
        return self.state.terminal
