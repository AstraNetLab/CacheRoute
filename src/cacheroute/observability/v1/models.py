"""Immutable, JSON-serializable observability schema v1."""
from __future__ import annotations

from datetime import datetime, timedelta
import math
import re

from pydantic import AwareDatetime, Field, StrictFloat, StrictInt, StrictStr, model_validator

from cacheroute.cache import CacheOperationState, CacheOperationTask, CacheOperationType
from cacheroute.contracts.v1.common import ContractModel
from cacheroute.contracts.v1.errors import ContractErrorDetail, OutcomeCode
from cacheroute.runtime import RuntimeProfile
from cacheroute.topology import LMCacheEndpoint, LMCacheGatewayProfile
from .enums import OperationWaiterState, TraceComponent, TraceStageName, TraceStageState, TraceValueKind

OBSERVABILITY_SCHEMA_VERSION = "observability.v1"
_CACHE_OPERATION_ID_PATTERN = r"^cacheop_[0-9a-f]{32}$"
_MAX_MEASUREMENT_INTEGER = 2**63 - 1
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+ -]*$")
_METRIC_CODE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_SENSITIVE = re.compile(
    r"(?i)(physical[_ -]?path|file[_ -]?path|filesystem[_ -]?path|raw[_ -]?exception|"
    r"exception|traceback|stack[_ -]?trace|api[_ -]?key|access[_ -]?token|authorization|"
    r"bearer|cookie|password|credential|secret|request[_ -]?body|http[_ -]?header|"
    r"redis[_ -]?key|kv[_ -]?bytes|tensor|device[_ -]?pointer|private.*lmcache|chunk[_ -]?index|"
    r"prompt|generated[_ -]?text)"
)
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_FILE_SUFFIX = re.compile(r"(?i)\.(?:bin|cache|ckpt|json|log|npy|pt|pth|safetensors|tmp|yaml|yml)$")
_LOGICAL_SCALARS = {
    "injection_mode": frozenset({"text", "kvcache"}),
    "kvcache_actual_path": frozenset({
        "kv_inject", "kv_inject_failed_fallback_text", "no_kv_ready_fallback_text",
    }),
    "text_actual_path": frozenset({"text_inject", "no_rag_or_empty_knowledge"}),
}


def _safe_label(value: str, field: str, limit: int = 256) -> str:
    if not value or len(value) > limit or "\n" in value or "\r" in value:
        raise ValueError(f"{field} must be a bounded single-line value")
    if not _SAFE.fullmatch(value) or _SENSITIVE.search(value):
        raise ValueError(f"{field} contains unsafe data")
    return value


def _metric_code(value: str) -> str:
    if _METRIC_CODE.fullmatch(value) is None:
        raise ValueError("measurement code must be a bounded machine identifier")
    return value


def _logical_scalar(code: str, value: str) -> str:
    allowed = _LOGICAL_SCALARS.get(code)
    if allowed is None or value not in allowed:
        raise ValueError("string scalar is not an allowed logical code value")
    # Retain the physical-path defense independently of the allowlist so future
    # additions cannot accidentally turn this field into a payload channel.
    if (
        value.startswith(("/", "\\", "~"))
        or _WINDOWS_PATH.match(value)
        or "/" in value
        or "\\" in value
        or any(part == ".." for part in re.split(r"[\\/]", value))
        or _FILE_SUFFIX.search(value)
    ):
        raise ValueError("scalar must not contain a physical path")
    return value


def _safe_message(value: str) -> str:
    if not value or len(value) > 512 or "\n" in value or "\r" in value or _SENSITIVE.search(value):
        raise ValueError("error message must be bounded, single-line, and sanitized")
    return value


def _legacy_label(value: str | None) -> bool:
    return value is not None and bool(re.search(r"(?i)(?:^|[_ ./-])(legacy|redis)(?:$|[_ ./-])", value))


def _cache_operation_id(value: str) -> str:
    if re.fullmatch(_CACHE_OPERATION_ID_PATTERN, value) is None:
        raise ValueError("cache operation ID must use canonical CacheOperationTask format")
    return value


def _utc(value: datetime, field: str) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must use UTC")
    return value


class TraceModel(ContractModel):
    """Contract model with validated-copy semantics inherited from canonical contracts."""


class TraceContext(TraceModel):
    schema_version: str = OBSERVABILITY_SCHEMA_VERSION
    trace_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    correlation_id: str | None = Field(default=None, max_length=128)
    runtime_profile: RuntimeProfile
    sampled: bool = True
    created_at: AwareDatetime
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.schema_version != OBSERVABILITY_SCHEMA_VERSION:
            raise ValueError("unsupported observability schema version")
        if self.runtime_profile is RuntimeProfile.AUTO:
            raise ValueError("runtime_profile 'auto' is startup-only")
        _utc(self.created_at, "created_at")
        if self.expires_at is not None:
            _utc(self.expires_at, "expires_at")
            if self.expires_at <= self.created_at:
                raise ValueError("expires_at must follow created_at")
        for name in ("trace_id", "request_id", "correlation_id"):
            value = getattr(self, name)
            if value is not None: _safe_label(value, name, 128)
        return self


class TraceProvenance(TraceModel):
    source_component: TraceComponent
    runtime_profile: RuntimeProfile
    captured_at: AwareDatetime
    source_endpoint: str | None = Field(default=None, max_length=256)
    compatibility_profile_id: str | None = Field(default=None, max_length=128)
    endpoint_id: str | None = Field(default=None, pattern=r"^endpoint_[0-9a-f]{32}$")
    endpoint_generation: int | None = Field(default=None, ge=0)
    gateway_profile: LMCacheGatewayProfile | None = None
    gateway_adapter: str | None = Field(default=None, max_length=128)
    storage_adapter: str | None = Field(default=None, max_length=128)
    tier: str | None = Field(default=None, max_length=128)
    source_version: str | None = Field(default=None, max_length=128)
    fresh_until: AwareDatetime | None = None
    legacy_projected: bool = False

    @model_validator(mode="after")
    def valid(self):
        if self.runtime_profile is RuntimeProfile.AUTO:
            raise ValueError("runtime_profile 'auto' is startup-only")
        _utc(self.captured_at, "captured_at")
        if (self.endpoint_id is None) != (self.endpoint_generation is None):
            raise ValueError("endpoint_id and endpoint_generation must appear together")
        if self.endpoint_generation == 0 and not self.legacy_projected:
            raise ValueError("endpoint generation zero is Legacy-only")
        if self.legacy_projected and self.runtime_profile is not RuntimeProfile.LEGACY:
            raise ValueError("Legacy projection requires Legacy runtime")
        if self.legacy_projected and self.source_component is not TraceComponent.LEGACY_ADAPTER:
            raise ValueError("Legacy projection requires the Legacy adapter component")
        if self.runtime_profile is not RuntimeProfile.LEGACY and self.source_component is TraceComponent.LEGACY_ADAPTER:
            raise ValueError("non-Legacy provenance cannot use the Legacy adapter component")
        if self.runtime_profile is not RuntimeProfile.LEGACY and self.gateway_profile is LMCacheGatewayProfile.LEGACY_GATEWAY:
            raise ValueError("non-Legacy provenance cannot use the Legacy Gateway profile")
        if self.runtime_profile is not RuntimeProfile.LEGACY and any(
            _legacy_label(value) for value in (self.gateway_adapter, self.storage_adapter)
        ):
            raise ValueError("non-Legacy provenance cannot claim a Legacy adapter label")
        if self.fresh_until is not None:
            _utc(self.fresh_until, "fresh_until")
            if self.fresh_until <= self.captured_at: raise ValueError("fresh_until must follow captured_at")
        for name in ("source_endpoint", "compatibility_profile_id", "gateway_adapter", "storage_adapter", "tier", "source_version"):
            value = getattr(self, name)
            if value is not None: _safe_label(value, name)
        return self


class TraceMeasurement(TraceModel):
    code: str = Field(min_length=1, max_length=128)
    value_kind: TraceValueKind
    duration_ns: int | None = Field(default=None, ge=0, le=_MAX_MEASUREMENT_INTEGER)
    count: int | None = Field(default=None, ge=0, le=_MAX_MEASUREMENT_INTEGER)
    bytes: int | None = Field(default=None, ge=0, le=_MAX_MEASUREMENT_INTEGER)
    tokens: int | None = Field(default=None, ge=0, le=_MAX_MEASUREMENT_INTEGER)
    ratio: float | None = None
    boolean: bool | None = None
    timestamp: AwareDatetime | None = None
    scalar: StrictStr | StrictInt | StrictFloat | None = None

    @model_validator(mode="after")
    def exactly_one_safe_value(self):
        names = ("duration_ns", "count", "bytes", "tokens", "ratio", "boolean", "timestamp", "scalar")
        if sum(getattr(self, name) is not None for name in names) != 1:
            raise ValueError("provide exactly one measurement value")
        _metric_code(self.code)
        if self.ratio is not None and (not math.isfinite(self.ratio) or not 0 <= self.ratio <= 1):
            raise ValueError("ratio must be finite and between zero and one")
        if self.timestamp is not None: _utc(self.timestamp, "timestamp")
        if isinstance(self.scalar, (int, float)) and (
            not math.isfinite(self.scalar)
            or not -_MAX_MEASUREMENT_INTEGER <= self.scalar <= _MAX_MEASUREMENT_INTEGER
        ):
            raise ValueError("numeric scalar must be finite and within safe bounds")
        if isinstance(self.scalar, str): _logical_scalar(self.code, self.scalar)
        if isinstance(self.scalar, bool):
            raise ValueError("invalid safe scalar")
        return self


class TraceStage(TraceModel):
    stage_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=0)
    name: TraceStageName
    state: TraceStageState
    provenance: TraceProvenance
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    elapsed_ns: int | None = Field(default=None, ge=0)
    outcome: OutcomeCode | None = None
    error: ContractErrorDetail | None = None
    skip_reason: str | None = Field(default=None, max_length=256)
    parent_stage_id: str | None = Field(default=None, max_length=128)
    fallback_stage_id: str | None = Field(default=None, max_length=128)
    logical_operation_id: str | None = Field(default=None, max_length=128)
    artifact_id: str | None = Field(default=None, max_length=128)
    measurements: tuple[TraceMeasurement, ...] = ()

    @model_validator(mode="after")
    def lifecycle(self):
        for stamp, name in ((self.started_at, "started_at"), (self.finished_at, "finished_at")):
            if stamp is not None: _utc(stamp, name)
        if self.state is TraceStageState.PENDING:
            if any(value is not None for value in (
                self.started_at, self.finished_at, self.elapsed_ns, self.outcome,
                self.error, self.skip_reason,
            )):
                raise ValueError("pending stage cannot contain lifecycle timestamps or completion state")
        elif self.state is TraceStageState.RUNNING:
            if self.started_at is None:
                raise ValueError("running stage requires started_at")
            if any(value is not None for value in (
                self.finished_at, self.elapsed_ns, self.outcome, self.error, self.skip_reason,
            )):
                raise ValueError("running stage cannot contain completion state")
        elif self.state is TraceStageState.COMPLETED:
            if self.started_at is None or self.finished_at is None or self.elapsed_ns is None or self.outcome is None or self.skip_reason is not None:
                raise ValueError("completed stage requires timing and canonical outcome")
        elif self.state is TraceStageState.SKIPPED:
            if self.skip_reason is None or any(value is not None for value in (
                self.started_at, self.finished_at, self.elapsed_ns, self.outcome, self.error,
            )):
                raise ValueError("skipped stage requires only a safe skip reason")
            _safe_label(self.skip_reason, "skip_reason")
        if self.error is not None and self.outcome is not self.error.code:
            raise ValueError("error detail must match stage outcome")
        if self.error is not None: _safe_message(self.error.message)
        for name in ("stage_id", "parent_stage_id", "fallback_stage_id", "logical_operation_id", "artifact_id"):
            value = getattr(self, name)
            if value is not None: _safe_label(value, name, 128)
        return self


def _ordered(stages: tuple[TraceStage, ...]) -> tuple[TraceStage, ...]:
    sequences = tuple(stage.sequence for stage in stages)
    if sequences != tuple(sorted(sequences)) or len(sequences) != len(set(sequences)):
        raise ValueError("stage sequence must be unique and monotonically increasing")
    ids = {stage.stage_id for stage in stages}
    if len(ids) != len(stages): raise ValueError("stage IDs must be unique")
    for stage in stages:
        if stage.parent_stage_id is not None and stage.parent_stage_id not in ids: raise ValueError("unknown parent stage")
        if stage.fallback_stage_id is not None and stage.fallback_stage_id not in ids: raise ValueError("unknown fallback stage")
        if stage.parent_stage_id == stage.stage_id: raise ValueError("stage cannot be its own parent")
        if stage.fallback_stage_id == stage.stage_id: raise ValueError("stage cannot be its own fallback")
    for attribute in ("parent_stage_id", "fallback_stage_id"):
        references = {stage.stage_id: getattr(stage, attribute) for stage in stages}
        for identifier in references:
            seen: set[str] = set()
            current: str | None = identifier
            while current is not None:
                if current in seen: raise ValueError(f"{attribute} cycle")
                seen.add(current)
                current = references[current]
    return stages


class OperationWaiterLink(TraceModel):
    request_trace_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    state: OperationWaiterState = OperationWaiterState.WAITING
    linked_at: AwareDatetime
    updated_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def valid(self):
        _safe_label(self.request_trace_id, "request_trace_id", 128); _safe_label(self.request_id, "request_id", 128)
        _utc(self.linked_at, "linked_at")
        if self.updated_at is not None:
            _utc(self.updated_at, "updated_at")
            if self.updated_at < self.linked_at: raise ValueError("updated_at must not precede linked_at")
        return self


class RequestTrace(TraceModel):
    context: TraceContext
    stages: tuple[TraceStage, ...] = ()
    cache_operation_ids: tuple[str, ...] = ()
    outcome: OutcomeCode | None = None
    error: ContractErrorDetail | None = None

    @model_validator(mode="after")
    def valid(self):
        _ordered(self.stages)
        if len(set(self.cache_operation_ids)) != len(self.cache_operation_ids): raise ValueError("cache operation IDs must be unique")
        for value in self.cache_operation_ids: _cache_operation_id(value)
        if self.error is not None:
            if self.outcome is not self.error.code: raise ValueError("error must match outcome")
            _safe_message(self.error.message)
        return self


class CacheOperationTrace(TraceModel):
    operation_id: str = Field(pattern=_CACHE_OPERATION_ID_PATTERN)
    operation_type: CacheOperationType
    operation_state: CacheOperationState | None = None
    stages: tuple[TraceStage, ...] = ()
    waiters: tuple[OperationWaiterLink, ...] = ()

    @model_validator(mode="after")
    def valid(self):
        _cache_operation_id(self.operation_id); _ordered(self.stages)
        pairs = {(item.request_trace_id, item.request_id) for item in self.waiters}
        if len(pairs) != len(self.waiters): raise ValueError("waiter links must be unique")
        return self


__all__ = [
    "TraceContext", "TraceProvenance", "TraceMeasurement", "TraceStage", "RequestTrace",
    "CacheOperationTrace", "OperationWaiterLink",
]
