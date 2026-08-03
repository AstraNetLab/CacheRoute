"""Cache artifact, observation, and operation state models."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar, Mapping
from uuid import uuid4

from pydantic import AwareDatetime, Field, field_validator, model_validator

from cacheroute.runtime import RuntimeProfile, Snapshot, StateTransitionError, StrEnum
from cacheroute.runtime.state import canonical_id, nonempty, require_utc, utc_now
from cacheroute.topology import LMCacheEndpoint, LMCacheGatewayProfile


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
        return nonempty(value)

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
        expected = canonical_id("artifact", self.identity())
        if self.artifact_id is not None and self.artifact_id != expected:
            raise ValueError("artifact_id does not match canonical identity")
        object.__setattr__(self, "artifact_id", expected)
        return self

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
    source_observed_at: AwareDatetime | None = None
    projected_at: AwareDatetime = Field(default_factory=utc_now)
    expires_at: AwareDatetime | None = None
    confidence: ObservationConfidence = ObservationConfidence.MEDIUM
    legacy_projection: bool = False
    compatibility_uncertain: bool = False
    legacy_kv_rel_dir: str | None = None
    legacy_kv_dumped_keys: int | None = Field(default=None, ge=0)

    @field_validator("artifact_id", "endpoint_id", "compatibility_profile_id")
    @classmethod
    def nonempty(cls, value: str) -> str:
        return nonempty(value)

    @model_validator(mode="after")
    def validate_and_id(self):
        require_utc(self.projected_at, "projected_at")
        if self.source_observed_at is not None:
            require_utc(self.source_observed_at, "source_observed_at")
            if self.source_observed_at > self.projected_at:
                raise ValueError("source_observed_at must not be later than projected_at")
        if self.expires_at is not None:
            require_utc(self.expires_at, "expires_at")
        if self.source_observed_at is None and not self.legacy_projection:
            raise ValueError("non-Legacy observations require source_observed_at")
        if self.source_observed_at is not None and (
            self.expires_at is None or self.expires_at <= self.source_observed_at
        ):
            raise ValueError("expires_at must be later than source_observed_at")
        legacy_values = (
            self.runtime_profile is RuntimeProfile.LEGACY,
            self.gateway_profile is LMCacheGatewayProfile.LEGACY_GATEWAY,
            self.source is ObservationSource.LEGACY_PROJECTION,
            self.compatibility_uncertain,
        )
        if self.legacy_projection and not all(legacy_values):
            raise ValueError("legacy_projection requires Legacy runtime, Gateway, source, and uncertainty")
        if self.source is ObservationSource.LEGACY_PROJECTION and not self.legacy_projection:
            raise ValueError("legacy_projection source requires legacy_projection=True")
        if not self.legacy_projection and (
            self.legacy_kv_rel_dir is not None or self.legacy_kv_dumped_keys is not None
        ):
            raise ValueError("Legacy metadata is only valid on Legacy projections")
        if self.endpoint_generation == 0 and not self.legacy_projection:
            raise ValueError("unknown endpoint generation is only valid for Legacy projections")
        if self.legacy_projection and self.endpoint_generation != 0:
            raise ValueError("Legacy projections must use unknown endpoint_generation=0")
        identity = self.model_dump(mode="json", exclude={"observation_id"})
        expected = canonical_id("observation", identity)
        if self.observation_id is not None and self.observation_id != expected:
            raise ValueError("observation_id does not match canonical observation")
        object.__setattr__(self, "observation_id", expected)
        return self

    @property
    def stale(self) -> bool:
        return not self.is_fresh()

    def is_fresh(self, at: datetime | None = None) -> bool:
        at = at or utc_now()
        require_utc(at, "freshness timestamp")
        return (
            self.source_observed_at is not None
            and self.expires_at is not None
            and self.source_observed_at <= at < self.expires_at
        )

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
        missing = object()
        raw = get("kv_ready", missing)
        malformed = raw is missing or raw not in (0, 1, False, True)
        if freshness <= timedelta(0):
            raise ValueError("freshness must be positive")
        stamp = get("kv_updated_at")
        projected = now or utc_now()
        require_utc(projected, "projected_at")
        try:
            observed = datetime.fromtimestamp(stamp, timezone.utc) if stamp is not None else None
        except (TypeError, ValueError, OSError):
            observed = None
            malformed = True
        if observed is not None and observed > projected:
            observed = None
            malformed = True
        state = ObservationState.UNKNOWN if malformed else (
            ObservationState.AVAILABLE if int(raw) else ObservationState.PENDING
        )
        return cls(
            artifact_id=artifact_id, state=state,
            source=ObservationSource.LEGACY_PROJECTION, endpoint_id=endpoint_id, endpoint_generation=0,
            runtime_profile=RuntimeProfile.LEGACY, gateway_profile=LMCacheGatewayProfile.LEGACY_GATEWAY,
            compatibility_profile_id=compatibility_profile_id, source_observed_at=observed,
            projected_at=projected, expires_at=observed + freshness if observed else None,
            confidence=ObservationConfidence.LOW,
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
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")
        nonempty(self.idempotency_key)
        nonempty(self.compatibility_profile_id)
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
        require_utc(stamp, "transition timestamp")
        if stamp < self.updated_at: raise ValueError("transition timestamp must not move backwards")
        return type(self).model_validate(self.model_dump() | {"state": requested, "attempt": self.attempt + int(requested is CacheOperationState.RUNNING), "updated_at": stamp})

    @property
    def terminal(self): return self.state.terminal
    @property
    def retryable(self): return self.state.retryable

__all__ = [
    "CacheArtifact", "CacheOperationState", "CacheOperationTask", "CacheOperationType",
    "CacheReplicaObservation", "ObservationConfidence", "ObservationSource", "ObservationState",
]
