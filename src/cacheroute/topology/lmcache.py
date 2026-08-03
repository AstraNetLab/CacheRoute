"""LMCache topology identity models."""
from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from cacheroute.runtime import RuntimeProfile
from cacheroute.runtime.state import Snapshot, StrEnum, canonical_id, nonempty


class LMCacheGatewayProfile(StrEnum):
    MP_HTTP_API = "mp_http_api"
    MP_COORDINATOR = "mp_coordinator"
    MP_SDK = "mp_sdk"
    MP_METRICS_EVENTS = "mp_metrics_events"
    LEGACY_GATEWAY = "legacy_gateway"
    MOCK = "mock"
    UNKNOWN_FUTURE = "unknown_future"

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
        return nonempty(value)

    @model_validator(mode="after")
    def canonicalize_id(self):
        expected = canonical_id("endpoint", {"name": self.name})
        if self.endpoint_id is not None and self.endpoint_id != expected:
            raise ValueError("endpoint_id does not match canonical identity")
        object.__setattr__(self, "endpoint_id", expected)
        return self

    def next_generation(self):
        return self.model_copy(update={"generation": self.generation + 1})

__all__ = ["LMCacheEndpoint", "LMCacheGatewayProfile"]
