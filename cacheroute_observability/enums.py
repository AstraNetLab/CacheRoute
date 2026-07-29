"""Stable string vocabularies for CacheRoute observability v1."""
from enum import Enum


class _StringEnum(str, Enum):
    pass


class TraceComponent(_StringEnum):
    CLIENT = "client"
    SCHEDULER = "scheduler"
    PROXY = "proxy"
    KDN = "kdn"
    GATEWAY = "gateway"
    INSTANCE = "instance"
    VLLM = "vllm"
    LMCACHE = "lmcache"
    LEGACY_ADAPTER = "legacy_adapter"
    TEST = "test"


class TraceValueKind(_StringEnum):
    PREDICTED = "predicted"
    OBSERVED = "observed"
    ACTUAL = "actual"
    INFERRED = "inferred"
    LEGACY_PROJECTED = "legacy_projected"


class TraceStageState(_StringEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"


class TraceStageOutcome(_StringEnum):
    SUCCESS = "success"
    UNSUPPORTED = "unsupported"
    INCOMPATIBLE = "incompatible"
    STALE = "stale"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TEXT_FALLBACK = "text_fallback"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"


class TraceStageName(_StringEnum):
    RUNTIME_PROFILE_RESOLUTION = "runtime_profile_resolution"
    KNOWLEDGE_LOOKUP = "knowledge_lookup"
    SEMANTIC_RESOLUTION = "semantic_resolution"
    ARTIFACT_COMPATIBILITY = "artifact_compatibility"
    CAPABILITY_SNAPSHOT_DISCOVERY = "capability_snapshot_discovery"
    TOKEN_LOOKUP = "token_lookup"
    ARTIFACT_LOOKUP = "artifact_lookup"
    CACHE_OBSERVATION = "cache_observation"
    CACHE_OPERATION_QUEUE = "cache_operation_queue"
    CACHE_PREFETCH_EXECUTION = "cache_prefetch_execution"
    CACHE_PIN_EXECUTION = "cache_pin_execution"
    CACHE_UNPIN_EXECUTION = "cache_unpin_execution"
    CACHE_CLEAR_EXECUTION = "cache_clear_execution"
    CACHE_REBUILD_EXECUTION = "cache_rebuild_execution"
    GATEWAY_REQUEST = "gateway_request"
    GATEWAY_ASYNC_OPERATION = "gateway_async_operation"
    TIER_ADAPTER_OBSERVATION = "tier_adapter_observation"
    INSTANCE_LMCACHE_LOAD = "instance_lmcache_load"
    PROXY_PREPARE_QUEUE = "proxy_prepare_queue"
    PROXY_READY_QUEUE = "proxy_ready_queue"
    VLLM_PREFILL = "vllm_prefill"
    FIRST_TOKEN = "first_token"
    DECODE = "decode"
    COMPLETION = "completion"
    FALLBACK = "fallback"
    LEGACY_SCAN = "legacy_scan"
    LEGACY_DUMP = "legacy_dump"
    LEGACY_RESTORE = "legacy_restore"
    LEGACY_INJECT = "legacy_inject"


class OperationWaiterState(_StringEnum):
    WAITING = "waiting"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DETACHED = "detached"
    EXPIRED = "expired"


__all__ = [
    "OperationWaiterState", "TraceComponent", "TraceStageName",
    "TraceStageOutcome", "TraceStageState", "TraceValueKind",
]
