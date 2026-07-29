"""Versioned Cache Service Facade contracts; no physical cache vocabulary."""
from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from pydantic import AwareDatetime, Field, field_validator, model_validator

from kdn_server.domain import CacheArtifact, CacheOperationState, CacheOperationTask, CacheReplicaObservation, LMCacheEndpoint, CacheOperationType
from .common import ContractModel, GatewayTargetedRequest, TokenInput, VersionedMessage, utc_now
from .errors import ContractErrorDetail, OutcomeCode


class ArtifactRequest(GatewayTargetedRequest):
    artifact_id: str = Field(pattern=r"^artifact_[0-9a-f]{32}$")

class GetCacheObservationRequest(ArtifactRequest): pass
class LookupArtifactRequest(ArtifactRequest): pass
class LookupTokensRequest(GatewayTargetedRequest): tokens: TokenInput

class OperationIntentRequest(ArtifactRequest):
    idempotency_key: str = Field(min_length=1)

class CreatePrefetchIntentRequest(OperationIntentRequest): pass
class CreatePinIntentRequest(OperationIntentRequest): pass
class CreateUnpinIntentRequest(OperationIntentRequest): pass
class CreateClearIntentRequest(OperationIntentRequest): pass
class CreateRebuildIntentRequest(OperationIntentRequest): pass
class GetOperationStatusRequest(GatewayTargetedRequest): task_id: str = Field(pattern=r"^cacheop_[0-9a-f]{32}$")
class CancelOperationRequest(GetOperationStatusRequest): pass
class GetLMCacheEndpointsRequest(VersionedMessage): pass
class GetTierAndAdapterSummaryRequest(GatewayTargetedRequest): pass
class GetMaintenanceStatusRequest(GatewayTargetedRequest): pass


class TokenCoverage(ContractModel):
    covered_ranges: tuple[tuple[int, int], ...] = ()
    total_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_ranges(self):
        previous_end = 0
        for index, (start, end) in enumerate(self.covered_ranges):
            if start < 0 or start >= end or end > self.total_tokens:
                raise ValueError("coverage ranges require 0 <= start < end <= total_tokens")
            if index and start < previous_end:
                raise ValueError("coverage ranges must be ordered and non-overlapping")
            previous_end = end
        return self


class SummarySupport(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class SummaryBase(ContractModel):
    source: str = Field(min_length=1)
    observed_at: AwareDatetime = Field(default_factory=utc_now)
    endpoint_generation: int = Field(ge=1)
    support: SummarySupport
    partial: bool = False

    @field_validator("observed_at")
    @classmethod
    def utc_only(cls, value: datetime):
        if value.utcoffset() != timedelta(0): raise ValueError("observed_at must use UTC")
        return value


class AdapterSummary(SummaryBase):
    loaded_adapters: tuple[str, ...] = ()

    @field_validator("loaded_adapters")
    @classmethod
    def valid_adapters(cls, value):
        if any(not item.strip() for item in value) or len(set(value)) != len(value):
            raise ValueError("loaded adapters must be non-empty and unique")
        return value

class CapacityUsageObservation(SummaryBase):
    capacity_bytes: int | None = Field(default=None, ge=0)
    used_bytes: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def bounded(self):
        if self.capacity_bytes is not None and self.used_bytes is not None and self.used_bytes > self.capacity_bytes:
            raise ValueError("used_bytes cannot exceed capacity_bytes")
        return self

class TierSummary(SummaryBase):
    l1_tiers: tuple[str, ...] = ()
    l2_tiers: tuple[str, ...] = ()
    capacity: tuple[CapacityUsageObservation, ...] = ()

    @field_validator("l1_tiers", "l2_tiers")
    @classmethod
    def valid_tiers(cls, value):
        if any(not item.strip() for item in value) or len(set(value)) != len(value):
            raise ValueError("tier names must be non-empty and unique")
        return value

class MaintenanceSummary(SummaryBase):
    active: bool | None = None
    eviction_observable: bool | None = None
    detail: str | None = None


class CacheServiceResponse(VersionedMessage):
    compatibility_profile_id: str | None = None
    endpoint_id: str | None = None
    endpoint_generation: int | None = Field(default=None, ge=1)
    outcome: OutcomeCode = OutcomeCode.SUCCESS
    artifact: CacheArtifact | None = None
    artifacts: tuple[CacheArtifact, ...] = ()
    observation: CacheReplicaObservation | None = None
    observations: tuple[CacheReplicaObservation, ...] = ()
    operation: CacheOperationTask | None = None
    endpoints: tuple[LMCacheEndpoint, ...] = ()
    token_coverage: TokenCoverage | None = None
    adapter_summary: AdapterSummary | None = None
    tier_summary: TierSummary | None = None
    maintenance_summary: MaintenanceSummary | None = None
    error: ContractErrorDetail | None = None

    @model_validator(mode="after")
    def consistent_outcome(self):
        if self.outcome is OutcomeCode.SUCCESS and self.error is not None:
            raise ValueError("successful responses cannot carry an error")
        if self.outcome is not OutcomeCode.SUCCESS:
            if self.error is None or self.error.code is not self.outcome:
                raise ValueError("non-success responses require a matching error detail")
        if self.outcome is OutcomeCode.CANCELLED and (
            self.operation is None or self.operation.state is not CacheOperationState.CANCELLED
        ):
            raise ValueError("cancelled responses require a cancelled operation")
        if self.outcome is OutcomeCode.STALE and self.observation is not None and self.observation.is_fresh():
            raise ValueError("stale responses cannot carry a fresh observation")
        if self.outcome is OutcomeCode.TEXT_FALLBACK and not self.error.fallback_eligible:
            raise ValueError("text fallback must be explicitly fallback eligible")
        return self


GetCacheObservationResponse = CacheServiceResponse
LookupArtifactResponse = CacheServiceResponse
LookupTokensResponse = CacheServiceResponse
CreatePrefetchIntentResponse = CacheServiceResponse
CreatePinIntentResponse = CacheServiceResponse
CreateUnpinIntentResponse = CacheServiceResponse
CreateClearIntentResponse = CacheServiceResponse
CreateRebuildIntentResponse = CacheServiceResponse
GetOperationStatusResponse = CacheServiceResponse
CancelOperationResponse = CacheServiceResponse
GetLMCacheEndpointsResponse = CacheServiceResponse
GetTierAndAdapterSummaryResponse = CacheServiceResponse
GetMaintenanceStatusResponse = CacheServiceResponse

INTENT_OPERATION_TYPES = {
    CreatePrefetchIntentRequest: CacheOperationType.PREFETCH,
    CreatePinIntentRequest: CacheOperationType.PIN,
    CreateUnpinIntentRequest: CacheOperationType.UNPIN,
    CreateClearIntentRequest: CacheOperationType.CLEAR,
    CreateRebuildIntentRequest: CacheOperationType.REBUILD,
}
