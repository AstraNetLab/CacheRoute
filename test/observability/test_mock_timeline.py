"""Deterministic CPU-only Phase 4A demonstration; performs no external I/O."""
from datetime import datetime, timezone
import itertools

from cacheroute.observability import ManualTraceClock, TraceCollector
from cacheroute.observability.v1 import (
    CacheOperationTrace, OperationWaiterLink, TraceContext, TraceProvenance,
    TraceStageName,
)


def test_deterministic_mock_request_and_operation_timeline():
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    clock = ManualTraceClock(now, monotonic_ns=100)
    context = TraceContext(
        trace_id="mock_trace", request_id="mock_request",
        runtime_profile="test/mock", created_at=now,
    )
    provenance = TraceProvenance(
        source_component="test", runtime_profile="test/mock", captured_at=now,
        gateway_profile="mock", gateway_adapter="mock_adapter",
    )
    identifiers = (f"mock_stage_{index}" for index in itertools.count())
    collector = TraceCollector(context, clock=clock, id_factory=identifiers.__next__)
    for name, elapsed in (
        (TraceStageName.CAPABILITY_SNAPSHOT_DISCOVERY, 10),
        (TraceStageName.GATEWAY_REQUEST, 20),
        (TraceStageName.GATEWAY_ASYNC_OPERATION, 30),
        (TraceStageName.INSTANCE_LMCACHE_LOAD, 40),
        (TraceStageName.COMPLETION, 50),
    ):
        stage_id = collector.start_stage(name, provenance)
        clock.advance(nanoseconds=elapsed)
        collector.finish_stage(stage_id, outcome="success")

    operation_ids = ("cacheop_" + "1" * 32, "cacheop_" + "2" * 32)
    request = collector.export(cache_operation_ids=operation_ids, outcome="success")
    waiters = (
        OperationWaiterLink(request_trace_id=request.context.trace_id, request_id=request.context.request_id, linked_at=now),
        OperationWaiterLink(request_trace_id="second_trace", request_id="second_request", linked_at=now),
    )
    operation = CacheOperationTrace(
        operation_id=operation_ids[0], operation_type="prefetch",
        stages=request.stages[1:3], waiters=waiters,
    )

    assert [stage.sequence for stage in request.stages] == list(range(5))
    assert [stage.elapsed_ns for stage in request.stages] == [10, 20, 30, 40, 50]
    assert request.cache_operation_ids == operation_ids
    assert len(operation.waiters) == 2
