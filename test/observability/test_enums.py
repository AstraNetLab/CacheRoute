from cacheroute_observability import (
    TraceComponent, TraceStageName, TraceStageOutcome, TraceStageState, TraceValueKind,
)


def test_exact_enum_wire_values():
    assert [x.value for x in TraceComponent] == [
        "client", "scheduler", "proxy", "kdn", "gateway", "instance", "vllm",
        "lmcache", "legacy_adapter", "test",
    ]
    assert [x.value for x in TraceValueKind] == [
        "predicted", "observed", "actual", "inferred", "legacy_projected",
    ]
    assert [x.value for x in TraceStageState] == ["pending", "running", "completed"]
    assert [x.value for x in TraceStageOutcome] == [
        "success", "unsupported", "incompatible", "stale", "partial", "failed",
        "cancelled", "skipped", "text_fallback", "idempotency_conflict",
    ]
    assert [x.value for x in TraceStageName] == [
        "runtime_profile_resolution", "knowledge_lookup", "semantic_resolution",
        "artifact_compatibility", "capability_snapshot_discovery", "token_lookup",
        "artifact_lookup", "cache_observation", "cache_operation_queue",
        "cache_prefetch_execution", "cache_pin_execution", "cache_unpin_execution",
        "cache_clear_execution", "cache_rebuild_execution", "gateway_request",
        "gateway_async_operation", "tier_adapter_observation", "instance_lmcache_load",
        "proxy_prepare_queue", "proxy_ready_queue", "vllm_prefill", "first_token",
        "decode", "completion", "fallback", "legacy_scan", "legacy_dump",
        "legacy_restore", "legacy_inject",
    ]
