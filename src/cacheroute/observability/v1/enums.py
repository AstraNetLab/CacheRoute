"""Stable string vocabulary for observability schema v1."""
from enum import Enum


class TraceComponent(str, Enum):
    CLIENT = "client"; SCHEDULER = "scheduler"; PROXY = "proxy"; KDN = "kdn"
    GATEWAY = "gateway"; INSTANCE = "instance"; VLLM = "vllm"; LMCACHE = "lmcache"
    LEGACY_ADAPTER = "legacy_adapter"; TEST = "test"


class TraceStageState(str, Enum):
    PENDING = "pending"; RUNNING = "running"; COMPLETED = "completed"; SKIPPED = "skipped"


class TraceValueKind(str, Enum):
    PREDICTED = "predicted"; DESIRED = "desired"; OBSERVED = "observed"
    MEASURED = "measured"; ACTUAL = "actual"; INFERRED = "inferred"
    LEGACY_PROJECTED = "legacy_projected"


class OperationWaiterState(str, Enum):
    WAITING = "waiting"; COMPLETED = "completed"; CANCELLED = "cancelled"
    DETACHED = "detached"; EXPIRED = "expired"


class TraceStageName(str, Enum):
    RUNTIME_PROFILE_RESOLUTION = "runtime_profile_resolution"
    KNOWLEDGE_LOOKUP = "knowledge_lookup"
    SEMANTIC_RESOLUTION = "semantic_resolution"
    ARTIFACT_COMPATIBILITY = "artifact_compatibility"
    CAPABILITY_SNAPSHOT_DISCOVERY = "capability_snapshot_discovery"
    TOKEN_LOOKUP = "token_lookup"
    ARTIFACT_LOOKUP = "artifact_lookup"
    CACHE_OBSERVATION = "cache_observation"
    CACHE_OPERATION_QUEUE = "cache_operation_queue"
    PREFETCH_EXECUTION = "prefetch_execution"
    PIN_EXECUTION = "pin_execution"
    UNPIN_EXECUTION = "unpin_execution"
    CLEAR_EXECUTION = "clear_execution"
    REBUILD_EXECUTION = "rebuild_execution"
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


__all__ = ["TraceComponent", "TraceStageName", "TraceStageState", "TraceValueKind", "OperationWaiterState"]
