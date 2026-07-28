"""Immutable, storage-neutral KDN v1 domain contracts."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, ClassVar, Mapping
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from core.runtime_compat import normalize_runtime_profile


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_id(kind: str, identity: Mapping[str, Any]) -> str:
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{kind}_{uuid5(NAMESPACE_URL, 'cacheroute:v1:' + kind + ':' + encoded).hex}"


def _nonempty(value: str) -> str:
    if not value.strip():
        raise ValueError("identity fields must not be empty")
    return value


class StrEnum(str, Enum):
    pass


class RuntimeProfile(StrEnum):
    V1 = "v1"
    LEGACY = "legacy"
    TEST_MOCK = "test/mock"
    AUTO = "auto"  # accepted only by resolve_startup

    @classmethod
    def normalize(cls, value: "RuntimeProfile | str") -> "RuntimeProfile":
        return cls(normalize_runtime_profile(value.value if isinstance(value, cls) else value))

    @classmethod
    def resolve_startup(cls, value: "RuntimeProfile | str | None" = None, *, v1_available: bool = True) -> "RuntimeProfile":
        normalized = cls(normalize_runtime_profile(value))
        if normalized is cls.AUTO:
            return cls.V1 if v1_available else cls.LEGACY
        return normalized

    resolve_auto = resolve_startup


class LMCacheGatewayProfile(StrEnum):
    MP_HTTP_API = "mp_http_api"
    MP_COORDINATOR = "mp_coordinator"
    MP_SDK = "mp_sdk"
    MP_METRICS_EVENTS = "mp_metrics_events"
    LEGACY_GATEWAY = "legacy_gateway"
    MOCK = "mock"
    UNKNOWN_FUTURE = "unknown_future"


class ObservationSource(StrEnum):
    HTTP_API = "http_api"
    COORDINATOR = "coordinator"
    SDK = "sdk"
    METRICS_EVENT = "metrics_event"
    LEGACY_PROJECTION = "legacy_projection"
    MOCK = "mock"


class ObservationConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ObservationState(StrEnum):
    PENDING = "pending"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    PARTIAL = "partial"


class CacheOperationType(StrEnum):
    LOOKUP = "lookup"
    PREFETCH = "prefetch"
    PIN = "pin"
    UNPIN = "unpin"
    CLEAR = "clear"
    REBUILD = "rebuild"
    OBSERVE = "observe"


class CacheOperationState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in (self.SUCCEEDED, self.FAILED, self.CANCELLED)

    @property
    def retryable(self) -> bool:
        return self is self.RETRY_WAIT


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


class StateTransitionError(ValueError):
    def __init__(self, model: str, current: Enum, requested: Enum, allowed: set[Enum]):
        self.details = {
            "error": "invalid_state_transition", "model": model,
            "current_state": current.value, "requested_state": requested.value,
            "allowed_states": sorted(x.value for x in allowed),
        }
        super().__init__(f"invalid {model} transition {current.value!r} -> {requested.value!r}")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.details)


class Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("runtime_profile", check_fields=False, mode="before")
    @classmethod
    def resolved_runtime(cls, value: Any) -> RuntimeProfile:
        profile = RuntimeProfile.normalize(value)
        if profile is RuntimeProfile.AUTO:
            raise ValueError("runtime_profile 'auto' is startup-only; resolve it before persistence")
        return profile

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False):
        """Copy through full validation so protected fields cannot be bypassed."""
        data = self.model_dump(mode="python")
        data.update(update or {})
        return type(self).model_validate(data)

    def to_json(self) -> str:
        return self.model_dump_json()


class CacheArtifact(Snapshot):
    artifact_id: str | None = None
    knowledge_id: str
    artifact_version: str = "1"
    model_profile: str
    tokenizer_profile: str
    adapters: tuple[str, ...] = ()
    cache_data_profile: str
    compatibility_profile_id: str
    runtime_profile: RuntimeProfile = RuntimeProfile.V1
    schema_version: str = "v1"
    created_at: AwareDatetime = Field(default_factory=utc_now)

    @field_validator("knowledge_id", "artifact_version", "model_profile", "tokenizer_profile", "cache_data_profile", "compatibility_profile_id", "schema_version")
    @classmethod
    def nonempty(cls, value: str) -> str:
        return _nonempty(value)

    @field_validator("adapters")
    @classmethod
    def canonical_adapters(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not x.strip() for x in value) or len(set(value)) != len(value):
            raise ValueError("adapters must be non-empty and unique; tuple order is canonical")
        return value

    def identity(self) -> dict[str, Any]:
        return {k: self.model_dump(mode="json")[k] for k in (
            "knowledge_id", "artifact_version", "model_profile", "tokenizer_profile",
            "adapters", "cache_data_profile", "compatibility_profile_id", "runtime_profile", "schema_version")}

    @model_validator(mode="after")
    def canonicalize_id(self):
        expected = _canonical_id("artifact", self.identity())
        if self.artifact_id is not None and self.artifact_id != expected:
            raise ValueError("artifact_id does not match canonical identity")
        object.__setattr__(self, "artifact_id", expected)
        return self


class LMCacheEndpoint(Snapshot):
    endpoint_id: str | None = None
    name: str
    runtime_profile: RuntimeProfile = RuntimeProfile.V1
    gateway_profile: LMCacheGatewayProfile
    compatibility_profile_id: str
    generation: int = Field(default=1, ge=1)
    adapter: str | None = None
    tier: str | None = None

    @field_validator("name", "compatibility_profile_id")
    @classmethod
    def nonempty(cls, value: str) -> str:
        return _nonempty(value)

    @model_validator(mode="after")
    def canonicalize_id(self):
        expected = _canonical_id("endpoint", {"name": self.name})
        if self.endpoint_id is not None and self.endpoint_id != expected:
            raise ValueError("endpoint_id does not match canonical identity")
        object.__setattr__(self, "endpoint_id", expected)
        return self

    def next_generation(self):
        return self.model_copy(update={"generation": self.generation + 1})


class CacheReplicaObservation(Snapshot):
    observation_id: str | None = None
    artifact_id: str = Field(pattern=r"^artifact_[0-9a-f]{32}$")
    state: ObservationState
    source: ObservationSource
    endpoint_id: str = Field(pattern=r"^endpoint_[0-9a-f]{32}$")
    endpoint_generation: int = Field(ge=0)  # zero explicitly means unknown
    runtime_profile: RuntimeProfile = RuntimeProfile.V1
    gateway_profile: LMCacheGatewayProfile
    compatibility_profile_id: str
    adapter: str | None = None
    tier: str | None = None
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    confidence: ObservationConfidence = ObservationConfidence.MEDIUM
    legacy_projection: bool = False
    compatibility_uncertain: bool = False
    legacy_kv_rel_dir: str | None = None
    legacy_kv_dumped_keys: int | None = Field(default=None, ge=0)

    @field_validator("artifact_id", "endpoint_id", "compatibility_profile_id")
    @classmethod
    def nonempty(cls, value: str) -> str:
        return _nonempty(value)

    @model_validator(mode="after")
    def validate_and_id(self):
        if self.observed_at.utcoffset() != timedelta(0) or self.expires_at.utcoffset() != timedelta(0):
            raise ValueError("timestamps must be UTC")
        if self.expires_at <= self.observed_at:
            raise ValueError("expires_at must be later than observed_at")
        identity = self.model_dump(mode="json", exclude={"observation_id"})
        expected = _canonical_id("observation", identity)
        if self.observation_id is not None and self.observation_id != expected:
            raise ValueError("observation_id does not match canonical observation")
        object.__setattr__(self, "observation_id", expected)
        return self

    @property
    def stale(self) -> bool:
        return not self.is_fresh()

    def is_fresh(self, at: datetime | None = None) -> bool:
        at = at or utc_now()
        if at.tzinfo is None:
            raise ValueError("freshness timestamp must be timezone-aware")
        return at.astimezone(timezone.utc) < self.expires_at

    def applies_to(self, endpoint: LMCacheEndpoint, at: datetime | None = None) -> bool:
        return self.is_fresh(at) and all((
            self.endpoint_id == endpoint.endpoint_id,
            self.endpoint_generation == endpoint.generation,
            self.runtime_profile is endpoint.runtime_profile,
            self.compatibility_profile_id == endpoint.compatibility_profile_id,
            self.gateway_profile is endpoint.gateway_profile,
        ))

    @classmethod
    def from_legacy_kv_ready(cls, record: Any, *, artifact_id: str, endpoint_id: str,
                             compatibility_profile_id: str = "legacy-unknown",
                             freshness: timedelta = timedelta(minutes=5),
                             now: datetime | None = None):
        """Read-only projection of a KBItem/dict; this method performs no I/O."""
        get = record.get if isinstance(record, Mapping) else lambda key, default=None: getattr(record, key, default)
        raw = get("kv_ready", 0)
        if raw not in (0, 1, False, True):
            raise ValueError("legacy kv_ready must be 0 or 1")
        if freshness <= timedelta(0):
            raise ValueError("freshness must be positive")
        stamp = get("kv_updated_at")
        observed = datetime.fromtimestamp(stamp, timezone.utc) if stamp is not None else (now or utc_now())
        return cls(
            artifact_id=artifact_id, state=ObservationState.AVAILABLE if int(raw) else ObservationState.UNKNOWN,
            source=ObservationSource.LEGACY_PROJECTION, endpoint_id=endpoint_id, endpoint_generation=0,
            runtime_profile=RuntimeProfile.LEGACY, gateway_profile=LMCacheGatewayProfile.LEGACY_GATEWAY,
            compatibility_profile_id=compatibility_profile_id, observed_at=observed,
            expires_at=observed + freshness, confidence=ObservationConfidence.LOW,
            legacy_projection=True, compatibility_uncertain=True,
            legacy_kv_rel_dir=get("kv_rel_dir"), legacy_kv_dumped_keys=get("kv_dumped_keys"),
        )


class CacheOperationTask(Snapshot):
    _TRANSITIONS: ClassVar = {
        CacheOperationState.PENDING: {CacheOperationState.RUNNING, CacheOperationState.CANCELLED},
        CacheOperationState.RUNNING: {CacheOperationState.SUCCEEDED, CacheOperationState.RETRY_WAIT, CacheOperationState.FAILED, CacheOperationState.CANCELLED},
        CacheOperationState.RETRY_WAIT: {CacheOperationState.RUNNING, CacheOperationState.FAILED, CacheOperationState.CANCELLED},
        CacheOperationState.SUCCEEDED: set(), CacheOperationState.FAILED: set(), CacheOperationState.CANCELLED: set(),
    }
    task_id: str = Field(default_factory=lambda: f"cacheop_{uuid4().hex}", pattern=r"^cacheop_[0-9a-f]{32}$")
    idempotency_key: str
    operation: CacheOperationType
    artifact_id: str = Field(pattern=r"^artifact_[0-9a-f]{32}$")
    runtime_profile: RuntimeProfile = RuntimeProfile.V1
    compatibility_profile_id: str
    gateway_profile: LMCacheGatewayProfile
    endpoint_id: str | None = Field(default=None, pattern=r"^endpoint_[0-9a-f]{32}$")
    endpoint_generation: int | None = Field(default=None, ge=1)
    state: CacheOperationState = CacheOperationState.PENDING
    attempt: int = Field(default=0, ge=0)
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def consistency(self):
        _nonempty(self.idempotency_key)
        _nonempty(self.compatibility_profile_id)
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        writes = {CacheOperationType.PREFETCH, CacheOperationType.PIN, CacheOperationType.UNPIN, CacheOperationType.CLEAR, CacheOperationType.REBUILD}
        if self.runtime_profile is RuntimeProfile.V1 and self.operation in writes and self.gateway_profile is LMCacheGatewayProfile.LEGACY_GATEWAY:
            raise ValueError("v1 write operations cannot implicitly target legacy_gateway")
        if (self.endpoint_id is None) != (self.endpoint_generation is None):
            raise ValueError("endpoint_id and endpoint_generation must be supplied together")
        return self

    def transition(self, state, *, at=None):
        requested = CacheOperationState(state)
        if requested is self.state: return self
        allowed = self._TRANSITIONS[self.state]
        if requested not in allowed: raise StateTransitionError(type(self).__name__, self.state, requested, allowed)
        stamp = at or utc_now()
        if stamp < self.updated_at: raise ValueError("transition timestamp must not move backwards")
        return type(self).model_validate(self.model_dump() | {"state": requested, "attempt": self.attempt + int(requested is CacheOperationState.RUNNING), "updated_at": stamp})

    @property
    def terminal(self): return self.state.terminal
    @property
    def retryable(self): return self.state.retryable


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
        _nonempty(self.idempotency_key)
        if self.updated_at < self.created_at: raise ValueError("updated_at must not precede created_at")
        return self

    def transition(self, state, *, at=None):
        requested = QueueState(state)
        if requested is self.state: return self
        allowed = self._TRANSITIONS[self.state]
        if requested not in allowed: raise StateTransitionError(type(self).__name__, self.state, requested, allowed)
        stamp = at or utc_now()
        if stamp < self.updated_at: raise ValueError("transition timestamp must not move backwards")
        return type(self).model_validate(self.model_dump() | {"state": requested, "updated_at": stamp})

    @property
    def terminal(self): return self.state.terminal
    @property
    def retryable(self): return self.state.retryable
