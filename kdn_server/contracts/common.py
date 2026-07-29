"""Common, versioned wire vocabulary for KDN service contracts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from kdn_server.domain import RuntimeProfile

KDN_CONTRACT_VERSION = "kdn.v1"
GATEWAY_CONTRACT_VERSION = "lmcache-gateway.v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ContractModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    def model_copy(self, *, update=None, deep=False):
        data = self.model_dump(mode="python")
        data.update(update or {})
        return type(self).model_validate(data)


class VersionedMessage(ContractModel):
    contract_version: str = KDN_CONTRACT_VERSION
    runtime_profile: RuntimeProfile
    request_id: str = Field(default_factory=lambda: f"req_{uuid4().hex}", min_length=1)
    correlation_id: str | None = None
    compatibility_profile_id: str | None = None
    endpoint_id: str | None = None
    endpoint_generation: int | None = Field(default=None, ge=0)
    timestamp: AwareDatetime = Field(default_factory=utc_now)

    @field_validator("contract_version")
    @classmethod
    def supported_version(cls, value: str) -> str:
        if value != KDN_CONTRACT_VERSION:
            raise ValueError(f"unsupported contract version: {value}")
        return value

    @field_validator("runtime_profile", mode="before")
    @classmethod
    def resolved_profile(cls, value: Any) -> RuntimeProfile:
        profile = RuntimeProfile.normalize(value)
        if profile is RuntimeProfile.AUTO:
            raise ValueError("runtime_profile 'auto' is startup-only")
        return profile

    @field_validator("timestamp")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("timestamp must use UTC")
        return value


class TokenReference(ContractModel):
    reference_id: str = Field(min_length=1)
    token_count: int | None = Field(default=None, ge=0)


class TokenInput(ContractModel):
    token_ids: tuple[int, ...] | None = None
    token_reference: TokenReference | None = None

    @field_validator("token_ids")
    @classmethod
    def valid_ids(cls, value):
        if value is not None and (not value or any(x < 0 for x in value)):
            raise ValueError("token_ids must be a non-empty tuple of non-negative IDs")
        return value

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.token_ids is None) == (self.token_reference is None):
            raise ValueError("provide exactly one of token_ids or token_reference")
        return self
