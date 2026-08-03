"""Shared dependency-light state model foundations."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, field_validator

from .profiles import RuntimeProfile


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_id(kind: str, identity: Mapping[str, Any]) -> str:
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{kind}_{uuid5(NAMESPACE_URL, 'cacheroute:v1:' + kind + ':' + encoded).hex}"


def nonempty(value: str) -> str:
    if not value.strip():
        raise ValueError("identity fields must not be empty")
    return value


def require_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must use UTC")
    return value


class StrEnum(str, Enum):
    pass


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


__all__ = ["Snapshot", "StateTransitionError", "StrEnum"]
