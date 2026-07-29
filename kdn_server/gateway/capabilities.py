"""Immutable, provenance-bearing gateway capability discovery."""
from datetime import datetime
from enum import Enum

from pydantic import AwareDatetime, Field, field_validator, model_validator

from kdn_server.contracts.common import ContractModel, GATEWAY_CONTRACT_VERSION, utc_now
from kdn_server.domain import RuntimeProfile
from .profiles import GatewayTransportKind, LMCacheCompatibilityProfile


class SupportState(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"

    def __bool__(self):
        return self is SupportState.SUPPORTED


class CapabilitySnapshot(ContractModel):
    contract_version: str = GATEWAY_CONTRACT_VERSION
    runtime_profile: RuntimeProfile
    transport_kind: GatewayTransportKind
    compatibility_profile: LMCacheCompatibilityProfile
    endpoint_id: str
    endpoint_generation: int = Field(ge=0)
    runtime_mode: str | None = None
    observed_at: AwareDatetime = Field(default_factory=utc_now)
    source: str = Field(min_length=1)
    loaded_adapters: tuple[str, ...] = ()
    l1_tiers: tuple[str, ...] = ()
    l2_tiers: tuple[str, ...] = ()
    token_lookup: SupportState = SupportState.UNKNOWN
    range_coverage: SupportState = SupportState.UNKNOWN
    object_listing: SupportState = SupportState.UNKNOWN
    object_deletion: SupportState = SupportState.UNKNOWN
    warm_prefetch: SupportState = SupportState.UNKNOWN
    operation_status: SupportState = SupportState.UNKNOWN
    pin_unpin: SupportState = SupportState.UNKNOWN
    tier_capacity_usage: SupportState = SupportState.UNKNOWN
    maintenance_eviction: SupportState = SupportState.UNKNOWN
    metrics_events: SupportState = SupportState.UNKNOWN
    batching: SupportState = SupportState.UNKNOWN
    lock_lease: SupportState = SupportState.UNKNOWN
    async_completion: SupportState = SupportState.UNKNOWN
    cancellation: SupportState = SupportState.UNKNOWN

    @field_validator("contract_version")
    @classmethod
    def version(cls, value):
        if value != GATEWAY_CONTRACT_VERSION: raise ValueError("unsupported gateway contract version")
        return value

    @field_validator("runtime_profile", mode="before")
    @classmethod
    def resolved(cls, value):
        value = RuntimeProfile.normalize(value)
        if value is RuntimeProfile.AUTO: raise ValueError("runtime_profile 'auto' is startup-only")
        return value

    @model_validator(mode="after")
    def coherent_profile(self):
        if self.transport_kind is GatewayTransportKind.LEGACY_REDIS and self.runtime_profile is not RuntimeProfile.LEGACY:
            raise ValueError("legacy_redis requires the explicit Legacy runtime profile")
        if self.runtime_profile is RuntimeProfile.V1 and self.transport_kind in {
            GatewayTransportKind.LEGACY_REDIS, GatewayTransportKind.MOCK
        }:
            raise ValueError("v1 runtime cannot negotiate Legacy or Mock gateway transports")
        return self
