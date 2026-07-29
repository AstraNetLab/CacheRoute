"""Frozen, dependency-light CacheRoute observability contracts."""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    OperationWaiterState, TraceComponent, TraceStageName, TraceStageOutcome,
    TraceStageState, TraceValueKind,
)

_TRACE_RE = re.compile(r"^trace_[0-9a-f]{32}$")
_STAGE_RE = re.compile(r"^stage_[0-9a-f]{32}$")
_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_FORBIDDEN_KEYS = {
    "authorization", "cookie", "credentials", "device_address", "device_pointer",
    "generated_content", "http_headers", "kv_bytes", "password", "physical_kv",
    "physical_path", "prompt", "raw_exception", "redis_key", "request_body",
    "secret", "tensor", "token_value",
}


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value


def _nonempty(value: str, name: str, maximum: int = 256) -> str:
    if not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty and at most {maximum} characters")
    return value


def _safe_code(value: str, name: str) -> str:
    _nonempty(value, name, 128)
    if not _SAFE_CODE_RE.fullmatch(value):
        raise ValueError(f"{name} must be a safe logical code")
    return value


def _scan_forbidden(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                raise ValueError(f"forbidden observability field: {key}")
            _scan_forbidden(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            _scan_forbidden(nested)


class ContractModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_fields(cls, value: Any) -> Any:
        _scan_forbidden(value)
        return value

    def model_copy(self, *, update=None, deep: bool = False):
        """Copy through validation so frozen-contract invariants cannot be bypassed."""
        values = self.model_dump(mode="python")
        values.update(update or {})
        return type(self).model_validate(values)


class TraceContext(ContractModel):
    schema_version: str = "cacheroute.trace-context.v1"
    trace_id: str
    request_id: str
    correlation_id: str
    legacy_request_id: int | None = None
    sampled: bool = True
    created_at: datetime
    expires_at: datetime | None = None

    @field_validator("schema_version")
    @classmethod
    def exact_version(cls, value: str) -> str:
        if value != "cacheroute.trace-context.v1":
            raise ValueError("unsupported trace context schema version")
        return value

    @field_validator("trace_id")
    @classmethod
    def trace_id_format(cls, value: str) -> str:
        if not _TRACE_RE.fullmatch(value):
            raise ValueError("trace_id must use trace_<32 lowercase hex>")
        return value

    @field_validator("request_id", "correlation_id")
    @classmethod
    def bounded_ids(cls, value: str, info) -> str:
        return _nonempty(value, info.field_name, 256)

    @field_validator("created_at", "expires_at")
    @classmethod
    def utc_datetimes(cls, value: datetime | None, info):
        return None if value is None else _utc(value, info.field_name)

    @model_validator(mode="after")
    def expiry_order(self):
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
        return self


class TraceProvenance(ContractModel):
    source_component: TraceComponent
    runtime_profile: str
    captured_at: datetime
    source_endpoint: str | None = None
    endpoint_id: str | None = None
    endpoint_generation: int | None = None
    compatibility_profile_id: str | None = None
    gateway_profile: str | None = None
    adapter: str | None = None
    tier: str | None = None
    source_version: str | None = None
    fresh_until: datetime | None = None
    legacy: bool = False

    @field_validator("runtime_profile")
    @classmethod
    def profile(cls, value: str) -> str:
        return _safe_code(value, "runtime_profile")

    @field_validator(
        "source_endpoint", "endpoint_id", "compatibility_profile_id", "gateway_profile",
        "adapter", "tier", "source_version",
    )
    @classmethod
    def safe_labels(cls, value: str | None, info):
        return None if value is None else _safe_code(value, info.field_name)

    @field_validator("captured_at", "fresh_until")
    @classmethod
    def utc_datetimes(cls, value: datetime | None, info):
        return None if value is None else _utc(value, info.field_name)

    @model_validator(mode="after")
    def endpoint_and_freshness(self):
        if (self.endpoint_id is None) != (self.endpoint_generation is None):
            raise ValueError("endpoint_id and endpoint_generation must appear together")
        if self.endpoint_generation is not None:
            minimum = 0 if self.legacy else 1
            if self.endpoint_generation < minimum:
                raise ValueError("endpoint_generation is invalid for provenance")
            if not self.legacy and self.endpoint_generation == 0:
                raise ValueError("endpoint_generation=0 is Legacy-only")
        if self.fresh_until is not None and self.fresh_until < self.captured_at:
            raise ValueError("fresh_until cannot be earlier than captured_at")
        return self


Scalar = str | int | float | bool


class TraceMeasurement(ContractModel):
    _VALUE_FIELDS: ClassVar[tuple[str, ...]] = (
        "duration_ns", "count", "bytes", "tokens", "ratio", "boolean", "timestamp", "safe_scalar",
    )
    name: str
    kind: TraceValueKind
    provenance: TraceProvenance
    duration_ns: int | None = Field(default=None, ge=0)
    count: int | None = Field(default=None, ge=0)
    bytes: int | None = Field(default=None, ge=0)
    tokens: int | None = Field(default=None, ge=0)
    ratio: float | None = None
    boolean: bool | None = None
    timestamp: datetime | None = None
    safe_scalar: Scalar | None = None
    observed_at: datetime | None = None
    expires_at: datetime | None = None
    uncertainty: float | None = Field(default=None, ge=0)
    sample_count: int | None = Field(default=None, ge=0)
    legacy_name: str | None = None

    @field_validator("name", "legacy_name")
    @classmethod
    def safe_names(cls, value: str | None, info):
        return None if value is None else _safe_code(value, info.field_name)

    @field_validator("timestamp", "observed_at", "expires_at")
    @classmethod
    def utc_datetimes(cls, value: datetime | None, info):
        return None if value is None else _utc(value, info.field_name)

    @field_validator("ratio")
    @classmethod
    def valid_ratio(cls, value: float | None):
        if value is not None and (not math.isfinite(value) or not 0 <= value <= 1):
            raise ValueError("ratio must be finite and between 0 and 1")
        return value

    @field_validator("safe_scalar", mode="before")
    @classmethod
    def scalar_only(cls, value: Any):
        if value is not None and (isinstance(value, (dict, list, set, tuple)) or not isinstance(value, (str, int, float, bool))):
            raise ValueError("safe_scalar must be a scalar")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("safe_scalar float must be finite")
        if isinstance(value, str):
            _nonempty(value, "safe_scalar", 256)
        return value

    @model_validator(mode="after")
    def exactly_one_value(self):
        if sum(getattr(self, field) is not None for field in self._VALUE_FIELDS) != 1:
            raise ValueError("exactly one typed measurement value is required")
        if self.expires_at is not None:
            reference = self.observed_at or self.timestamp or self.provenance.captured_at
            if self.expires_at <= reference:
                raise ValueError("measurement expires_at must be later than its observation")
        return self


class TraceStage(ContractModel):
    stage_id: str
    sequence: int = Field(ge=0)
    name: TraceStageName
    state: TraceStageState
    outcome: TraceStageOutcome | None = None
    provenance: TraceProvenance
    measurements: tuple[TraceMeasurement, ...] = ()
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ns: int | None = Field(default=None, ge=0)
    parent_stage_id: str | None = None
    operation_id: str | None = None
    artifact_id: str | None = None
    outcome_code: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    fallback_eligible: bool = False
    fallback_stage_id: str | None = None
    partial_reason: str | None = None

    @field_validator("stage_id", "parent_stage_id", "fallback_stage_id")
    @classmethod
    def stage_ids(cls, value: str | None):
        if value is not None and not _STAGE_RE.fullmatch(value):
            raise ValueError("stage IDs must use stage_<32 lowercase hex>")
        return value

    @field_validator("operation_id", "artifact_id", "outcome_code", "error_code", "partial_reason")
    @classmethod
    def safe_codes(cls, value: str | None, info):
        return None if value is None else _safe_code(value, info.field_name)

    @field_validator("error_message")
    @classmethod
    def sanitized_message(cls, value: str | None):
        if value is None:
            return None
        _nonempty(value, "error_message", 256)
        if any(char in value for char in ("\n", "\r", "\x00")):
            raise ValueError("error_message must be a sanitized single line")
        return value

    @field_validator("started_at", "ended_at")
    @classmethod
    def utc_datetimes(cls, value: datetime | None, info):
        return None if value is None else _utc(value, info.field_name)

    @model_validator(mode="after")
    def lifecycle(self):
        if self.state is TraceStageState.COMPLETED and self.outcome is None:
            raise ValueError("completed stages require an outcome")
        if self.state is not TraceStageState.COMPLETED and self.outcome is not None:
            raise ValueError("pending/running stages cannot claim a terminal outcome")
        if self.ended_at is not None and self.started_at is None:
            raise ValueError("ended_at requires started_at")
        if self.started_at is not None and self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at cannot precede started_at")
        if self.state is TraceStageState.COMPLETED and (self.ended_at is None or self.duration_ns is None):
            raise ValueError("completed stages require ended_at and duration_ns")
        return self


class RequestTrace(ContractModel):
    schema_version: str = "cacheroute.trace.v1"
    context: TraceContext
    stages: tuple[TraceStage, ...] = ()
    exported_at: datetime
    complete: bool = False
    source_components: tuple[TraceComponent, ...] = ()
    error_code: str | None = None

    @field_validator("schema_version")
    @classmethod
    def exact_version(cls, value: str) -> str:
        if value != "cacheroute.trace.v1":
            raise ValueError("unsupported request trace schema version")
        return value

    @field_validator("exported_at")
    @classmethod
    def exported_utc(cls, value: datetime):
        return _utc(value, "exported_at")

    @field_validator("error_code")
    @classmethod
    def safe_error(cls, value: str | None):
        return None if value is None else _safe_code(value, "error_code")

    @model_validator(mode="after")
    def sequence_order(self):
        sequences = [stage.sequence for stage in self.stages]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ValueError("stages must have unique ascending sequence values")
        expected = tuple(dict.fromkeys(stage.provenance.source_component for stage in self.stages))
        if self.source_components and self.source_components != expected:
            raise ValueError("source_components must follow first stage occurrence")
        return self


class CacheOperationTrace(ContractModel):
    schema_version: str = "cacheroute.cache-operation-trace.v1"
    operation_id: str
    trace_id: str
    operation: str
    state: str
    stages: tuple[TraceStage, ...]
    provenance: TraceProvenance
    artifact_id: str | None = None
    endpoint_id: str | None = None
    endpoint_generation: int | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    error_code: str | None = None
    fallback_code: str | None = None

    @field_validator("operation_id", "operation", "state", "artifact_id", "endpoint_id", "error_code", "fallback_code")
    @classmethod
    def safe_values(cls, value: str | None, info):
        return None if value is None else _safe_code(value, info.field_name)

    @field_validator("trace_id")
    @classmethod
    def trace_id_format(cls, value: str):
        if not _TRACE_RE.fullmatch(value):
            raise ValueError("trace_id must use trace_<32 lowercase hex>")
        return value

    @field_validator("created_at", "updated_at", "completed_at")
    @classmethod
    def utc_datetimes(cls, value: datetime | None, info):
        return None if value is None else _utc(value, info.field_name)

    @model_validator(mode="after")
    def consistency(self):
        if self.updated_at < self.created_at or (self.completed_at is not None and self.completed_at < self.created_at):
            raise ValueError("operation timestamps are out of order")
        if (self.endpoint_id is None) != (self.endpoint_generation is None):
            raise ValueError("endpoint_id and endpoint_generation must appear together")
        if self.endpoint_generation is not None:
            minimum = 0 if self.provenance.legacy else 1
            if self.endpoint_generation < minimum or (not self.provenance.legacy and self.endpoint_generation == 0):
                raise ValueError("endpoint_generation is invalid")
        sequences = [stage.sequence for stage in self.stages]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ValueError("operation stages must have unique ascending sequence values")
        return self


class OperationWaiterLink(ContractModel):
    operation_id: str
    trace_id: str
    request_id: str
    correlation_id: str
    attach_sequence: int = Field(ge=0)
    attached_at: datetime
    state: OperationWaiterState
    detached_at: datetime | None = None
    reason: str | None = None

    @field_validator("operation_id", "request_id", "correlation_id", "reason")
    @classmethod
    def safe_values(cls, value: str | None, info):
        return None if value is None else _safe_code(value, info.field_name) if info.field_name in {"operation_id", "reason"} else _nonempty(value, info.field_name, 256)

    @field_validator("trace_id")
    @classmethod
    def trace_id_format(cls, value: str):
        if not _TRACE_RE.fullmatch(value):
            raise ValueError("trace_id must use trace_<32 lowercase hex>")
        return value

    @field_validator("attached_at", "detached_at")
    @classmethod
    def utc_datetimes(cls, value: datetime | None, info):
        return None if value is None else _utc(value, info.field_name)

    @model_validator(mode="after")
    def detach_order(self):
        if self.detached_at is not None and self.detached_at < self.attached_at:
            raise ValueError("detached_at cannot precede attached_at")
        return self


__all__ = [
    "CacheOperationTrace", "OperationWaiterLink", "RequestTrace", "TraceContext",
    "TraceMeasurement", "TraceProvenance", "TraceStage",
]
