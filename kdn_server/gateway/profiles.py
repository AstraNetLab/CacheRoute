"""Gateway adapter and LMCache compatibility profile vocabulary."""
from enum import Enum

from pydantic import Field

from kdn_server.contracts.common import ContractModel


class GatewayTransportKind(str, Enum):
    MP_HTTP_API = "mp_http_api"
    MP_COORDINATOR = "mp_coordinator"
    MP_SDK = "mp_sdk"
    MP_METRICS_EVENTS = "mp_metrics_events"
    MP_L2_PLUGIN = "mp_l2_plugin"
    LEGACY_REDIS = "legacy_redis"
    MOCK = "mock"
    UNKNOWN_FUTURE = "unknown_future"


class GatewayAdapterBinding(ContractModel):
    transport_kind: GatewayTransportKind
    binding_id: str = Field(min_length=1)


class LMCacheCompatibilityProfile(ContractModel):
    compatibility_profile_id: str = Field(min_length=1)
    lmcache_version: str | None = None
    lmcache_build: str | None = None
    config_profile: str | None = None
    layout_profile: str | None = None
    serde_profile: str | None = None
    chunk_size: int | None = Field(default=None, gt=0)
    connector_profile: str | None = None
    key_hash_profile: str | None = None
