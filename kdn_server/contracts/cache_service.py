"""Versioned Cache Service Facade contracts; no physical cache vocabulary."""
from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import ClassVar

from pydantic import AwareDatetime, Field, field_validator, model_validator

from cacheroute.runtime import RuntimeProfile
from kdn_server.domain import CacheArtifact, CacheOperationState, CacheOperationTask, CacheReplicaObservation, LMCacheEndpoint, CacheOperationType
from cacheroute.contracts.v1.common import ContractModel, GatewayTargetedRequest, SupportState, TokenInput, VersionedMessage, utc_now
from cacheroute.contracts.v1.errors import ContractErrorDetail, OutcomeCode


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
    """Separates whole-request hit state from capability-gated range detail."""
    whole_request_hit: bool
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


class SummaryBase(ContractModel):
    """Common provenance that binds summaries to an endpoint generation."""
    source: str = Field(min_length=1)
    observed_at: AwareDatetime = Field(default_factory=utc_now)
    runtime_profile: RuntimeProfile
    compatibility_profile_id: str = Field(min_length=1)
    endpoint_id: str = Field(pattern=r"^endpoint_[0-9a-f]{32}$")
    endpoint_generation: int = Field(ge=0)
    support: SupportState
    partial: bool = False

    @field_validator("observed_at")
    @classmethod
    def utc_only(cls, value: datetime):
        if value.utcoffset() != timedelta(0): raise ValueError("observed_at must use UTC")
        return value

    @model_validator(mode="after")
    def data_semantics(self):
        if self.runtime_profile is not RuntimeProfile.LEGACY and self.endpoint_generation == 0:
            raise ValueError("unknown generation is Legacy-only")
        return self


class AdapterSummary(SummaryBase):
    loaded_adapters: tuple[str, ...] = ()

    @field_validator("loaded_adapters")
    @classmethod
    def valid_adapters(cls, value):
        if any(not item.strip() for item in value) or len(set(value)) != len(value):
            raise ValueError("loaded adapters must be non-empty and unique")
        return value

    @model_validator(mode="after")
    def supported_has_data(self):
        if self.support is not SupportState.SUPPORTED and self.loaded_adapters:
            raise ValueError("unsupported or unknown summaries cannot carry adapter data")
        return self


class TierLevel(str, Enum):
    L1 = "l1"
    L2 = "l2"


class CapacityUsageObservation(SummaryBase):
    tier_name: str = Field(min_length=1)
    tier_level: TierLevel
    capacity_bytes: int | None = Field(default=None, ge=0)
    used_bytes: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def bounded(self):
        if self.capacity_bytes is not None and self.used_bytes is not None and self.used_bytes > self.capacity_bytes:
            raise ValueError("used_bytes cannot exceed capacity_bytes")
        if self.support is not SupportState.SUPPORTED and (self.capacity_bytes is not None or self.used_bytes is not None):
            raise ValueError("unsupported or unknown capacity cannot carry measurements")
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

    @model_validator(mode="after")
    def tier_consistency(self):
        if self.support is not SupportState.SUPPORTED and (self.l1_tiers or self.l2_tiers or self.capacity):
            raise ValueError("unsupported or unknown summaries cannot carry tier data")
        known = {(name, TierLevel.L1) for name in self.l1_tiers} | {(name, TierLevel.L2) for name in self.l2_tiers}
        if any((item.tier_name, item.tier_level) not in known for item in self.capacity):
            raise ValueError("capacity observations must identify a listed tier and level")
        for item in self.capacity:
            if any((item.runtime_profile is not self.runtime_profile,
                    item.compatibility_profile_id != self.compatibility_profile_id,
                    item.endpoint_id != self.endpoint_id,
                    item.endpoint_generation != self.endpoint_generation)):
                raise ValueError("capacity provenance must match its tier summary")
        return self


class MaintenanceSummary(SummaryBase):
    active: bool | None = None
    eviction_observable: bool | None = None
    detail: str | None = None

    @model_validator(mode="after")
    def maintenance_semantics(self):
        if self.support is not SupportState.SUPPORTED and (self.active is not None or self.eviction_observable is not None):
            raise ValueError("unsupported or unknown maintenance cannot carry observations")
        return self


class CacheServiceResponse(VersionedMessage):
    """Internal response base enforcing outcome and nested provenance consistency."""
    compatibility_profile_id: str | None = None
    endpoint_id: str | None = None
    endpoint_generation: int | None = Field(default=None, ge=0)
    outcome: OutcomeCode = OutcomeCode.SUCCESS
    artifact: CacheArtifact | None = None
    observation: CacheReplicaObservation | None = None
    operation: CacheOperationTask | None = None
    endpoints: tuple[LMCacheEndpoint, ...] | None = None
    token_coverage: TokenCoverage | None = None
    adapter_summary: AdapterSummary | None = None
    tier_summary: TierSummary | None = None
    maintenance_summary: MaintenanceSummary | None = None
    error: ContractErrorDetail | None = None

    @model_validator(mode="after")
    def consistent_outcome(self):
        # Generic construction must not bypass the targeted response envelope.
        targeted_payload = any(value is not None for value in (
            self.artifact, self.observation, self.operation, self.token_coverage,
            self.adapter_summary, self.tier_summary, self.maintenance_summary))
        if targeted_payload and any(value is None for value in (
                self.compatibility_profile_id, self.endpoint_id, self.endpoint_generation)):
            raise ValueError("targeted payloads require complete target metadata")
        if self.runtime_profile is not RuntimeProfile.LEGACY and self.endpoint_generation == 0:
            raise ValueError("endpoint_generation=0 is only valid for Legacy responses")
        if self.outcome is OutcomeCode.SUCCESS and self.error is not None:
            raise ValueError("successful responses cannot carry an error")
        if self.outcome is not OutcomeCode.SUCCESS and (self.error is None or self.error.code is not self.outcome):
            raise ValueError("non-success responses require a matching error detail")
        if self.outcome is OutcomeCode.CANCELLED and (self.operation is None or self.operation.state is not CacheOperationState.CANCELLED):
            raise ValueError("cancelled responses require a cancelled operation")
        if self.outcome is OutcomeCode.STALE and self.observation is not None and self.observation.is_fresh(at=self.timestamp):
            raise ValueError("stale responses cannot carry an observation fresh at response timestamp")
        if self.outcome is OutcomeCode.TEXT_FALLBACK and not self.error.fallback_eligible:
            raise ValueError("text fallback must be explicitly fallback eligible")
        for summary in (self.adapter_summary, self.tier_summary, self.maintenance_summary):
            if summary is not None and any((summary.runtime_profile is not self.runtime_profile,
                    summary.compatibility_profile_id != self.compatibility_profile_id,
                    summary.endpoint_id != self.endpoint_id, summary.endpoint_generation != self.endpoint_generation)):
                raise ValueError("summary provenance must match response envelope")
        if self.observation is not None and self.observation.endpoint_generation != self.endpoint_generation:
            raise ValueError("observation generation must match response envelope")
        if self.artifact is not None and self.compatibility_profile_id is not None and any((
                self.artifact.runtime_profile is not self.runtime_profile,
                self.artifact.compatibility_profile_id != self.compatibility_profile_id)):
            raise ValueError("artifact provenance must match response envelope")
        if self.observation is not None and self.compatibility_profile_id is not None and any((
                self.observation.runtime_profile is not self.runtime_profile,
                self.observation.compatibility_profile_id != self.compatibility_profile_id,
                self.observation.endpoint_id != self.endpoint_id,
                self.observation.endpoint_generation != self.endpoint_generation)):
            raise ValueError("observation provenance must match response envelope")
        if self.operation is not None and self.compatibility_profile_id is not None and any((
                self.operation.runtime_profile is not self.runtime_profile,
                self.operation.compatibility_profile_id != self.compatibility_profile_id,
                self.operation.endpoint_id != self.endpoint_id,
                self.operation.endpoint_generation != self.endpoint_generation)):
            raise ValueError("operation provenance must match response envelope")
        if self.endpoints is not None and any(endpoint.runtime_profile is not self.runtime_profile for endpoint in self.endpoints):
            raise ValueError("endpoint runtime profile must match response envelope")
        return self


class GatewayTargetedResponse(CacheServiceResponse):
    compatibility_profile_id: str = Field(min_length=1)
    endpoint_id: str = Field(pattern=r"^endpoint_[0-9a-f]{32}$")
    endpoint_generation: int = Field(ge=0)


class GetCacheObservationResponse(GatewayTargetedResponse):
    """Observation result whose successful payload is fresh at response time."""
    @model_validator(mode="after")
    def success_payload(self):
        if self.outcome is OutcomeCode.SUCCESS and (
                self.observation is None or not self.observation.is_fresh(at=self.timestamp)):
            raise ValueError("successful observation response requires a fresh observation")
        return self

class LookupArtifactResponse(GatewayTargetedResponse):
    @model_validator(mode="after")
    def success_payload(self):
        if self.outcome is OutcomeCode.SUCCESS and self.artifact is None: raise ValueError("successful artifact response requires artifact")
        return self

class LookupTokensResponse(GatewayTargetedResponse):
    @model_validator(mode="after")
    def success_payload(self):
        if self.outcome is OutcomeCode.SUCCESS and self.token_coverage is None: raise ValueError("successful token response requires coverage")
        return self

class OperationResponse(GatewayTargetedResponse):
    @model_validator(mode="after")
    def success_payload(self):
        if self.outcome is OutcomeCode.SUCCESS and self.operation is None: raise ValueError("successful operation response requires operation")
        return self

class _TypedOperationResponse(OperationResponse):
    """Prevents a successful intent response from carrying another operation kind."""
    expected_operation: ClassVar[CacheOperationType]

    @model_validator(mode="after")
    def correct_operation(self):
        if self.outcome is OutcomeCode.SUCCESS and self.operation.operation is not self.expected_operation:
            raise ValueError(f"successful response requires {self.expected_operation.value} operation")
        return self

class CreatePrefetchIntentResponse(_TypedOperationResponse): expected_operation = CacheOperationType.PREFETCH
class CreatePinIntentResponse(_TypedOperationResponse): expected_operation = CacheOperationType.PIN
class CreateUnpinIntentResponse(_TypedOperationResponse): expected_operation = CacheOperationType.UNPIN
class CreateClearIntentResponse(_TypedOperationResponse): expected_operation = CacheOperationType.CLEAR
class CreateRebuildIntentResponse(_TypedOperationResponse): expected_operation = CacheOperationType.REBUILD
class GetOperationStatusResponse(OperationResponse): pass
class CancelOperationResponse(OperationResponse):
    """Allows success only when cancellation is already a terminal no-op."""
    @model_validator(mode="after")
    def cancellation_state(self):
        if self.outcome is OutcomeCode.SUCCESS and not self.operation.terminal:
            raise ValueError("successful cancellation no-op requires an already-terminal operation")
        return self

class GetLMCacheEndpointsResponse(CacheServiceResponse):
    @model_validator(mode="after")
    def success_payload(self):
        if self.outcome is OutcomeCode.SUCCESS and self.endpoints is None: raise ValueError("successful endpoint response requires endpoints")
        return self

class GetTierAndAdapterSummaryResponse(GatewayTargetedResponse):
    @model_validator(mode="after")
    def success_payload(self):
        if self.outcome is OutcomeCode.SUCCESS and (self.adapter_summary is None or self.tier_summary is None): raise ValueError("successful tier response requires both summaries")
        return self

class GetMaintenanceStatusResponse(GatewayTargetedResponse):
    @model_validator(mode="after")
    def success_payload(self):
        if self.outcome is OutcomeCode.SUCCESS and self.maintenance_summary is None: raise ValueError("successful maintenance response requires summary")
        return self

INTENT_OPERATION_TYPES = {
    CreatePrefetchIntentRequest: CacheOperationType.PREFETCH,
    CreatePinIntentRequest: CacheOperationType.PIN,
    CreateUnpinIntentRequest: CacheOperationType.UNPIN,
    CreateClearIntentRequest: CacheOperationType.CLEAR,
    CreateRebuildIntentRequest: CacheOperationType.REBUILD,
}
