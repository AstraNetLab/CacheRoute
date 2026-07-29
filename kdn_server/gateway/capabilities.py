"""Immutable, provenance-bearing gateway capability discovery."""
from datetime import datetime, timedelta
from pydantic import AwareDatetime, Field, field_validator, model_validator

from kdn_server.contracts.common import ContractModel, ENDPOINT_ID_PATTERN, GATEWAY_CONTRACT_VERSION, SupportState, utc_now
from kdn_server.domain import RuntimeProfile
from .profiles import GatewayAdapterBinding, GatewayTransportKind, LMCacheCompatibilityProfile


class CapabilitySnapshot(ContractModel):
    """Immutable discovery result for one composed, runtime-isolated endpoint."""
    contract_version: str = GATEWAY_CONTRACT_VERSION
    runtime_profile: RuntimeProfile
    adapter_bindings: tuple[GatewayAdapterBinding, ...]
    compatibility_profile: LMCacheCompatibilityProfile
    endpoint_id: str = Field(pattern=ENDPOINT_ID_PATTERN)
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
    artifact_lookup: SupportState = SupportState.UNKNOWN
    cache_observation: SupportState = SupportState.UNKNOWN

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

    @field_validator("observed_at")
    @classmethod
    def utc_only(cls, value: datetime):
        if value.utcoffset() != timedelta(0): raise ValueError("observed_at must use UTC")
        return value

    @field_validator("loaded_adapters", "l1_tiers", "l2_tiers")
    @classmethod
    def ordered_unique_names(cls, value):
        if any(not item.strip() for item in value) or len(set(value)) != len(value):
            raise ValueError("adapter and tier names must be non-empty and unique")
        return value

    @model_validator(mode="after")
    def coherent_profile(self):
        # Composition is ordered, but a transport cannot be bound twice.
        kinds = tuple(binding.transport_kind for binding in self.adapter_bindings)
        if not kinds or len(set(kinds)) != len(kinds):
            raise ValueError("adapter_bindings must be non-empty and unique by transport kind")
        mp = {GatewayTransportKind.MP_HTTP_API, GatewayTransportKind.MP_COORDINATOR,
              GatewayTransportKind.MP_SDK, GatewayTransportKind.MP_METRICS_EVENTS,
              GatewayTransportKind.MP_L2_PLUGIN, GatewayTransportKind.UNKNOWN_FUTURE}
        allowed = (set(kinds) <= mp if self.runtime_profile is RuntimeProfile.V1 else
                   set(kinds) == {GatewayTransportKind.LEGACY_REDIS} if self.runtime_profile is RuntimeProfile.LEGACY else
                   set(kinds) == {GatewayTransportKind.MOCK})
        if not allowed:
            # Runtime isolation prevents Mock or Legacy behavior leaking into v1.
            raise ValueError("adapter bindings are incompatible with runtime profile")
        if self.runtime_profile is not RuntimeProfile.LEGACY and self.endpoint_generation == 0:
            raise ValueError("endpoint_generation=0 is only valid for Legacy capabilities")
        return self

    def supports_adapter(self, kind: GatewayTransportKind | str) -> bool:
        requested = GatewayTransportKind(kind)
        return any(item.transport_kind is requested for item in self.adapter_bindings)
