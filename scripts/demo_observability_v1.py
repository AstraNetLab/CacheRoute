#!/usr/bin/env python3
"""Deterministic, CPU-only demonstration of CacheRoute observability v1."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cacheroute_observability import (  # noqa: E402
    CacheOperationTrace, ManualTraceClock, OperationWaiterLink, OperationWaiterState,
    TraceCollector, TraceComponent, TraceContext, TraceMeasurement, TraceProvenance,
    TraceStageName, TraceStageOutcome, TraceValueKind, project_legacy_proxy_trace,
)


def main() -> int:
    clock = ManualTraceClock(datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc), 1_000)
    context = TraceContext(
        trace_id="trace_00000000000000000000000000000001", request_id="req-demo-1",
        correlation_id="corr-demo", legacy_request_id=42, sampled=True,
        created_at=clock.utc_now(), expires_at=clock.utc_now() + timedelta(minutes=5),
    )
    provenance = TraceProvenance(source_component=TraceComponent.TEST,
                                 runtime_profile="test.mock", captured_at=clock.utc_now())
    stage_ids = iter(f"stage_{number:032x}" for number in range(1, 20))
    collector = TraceCollector(context, clock=clock, id_factory=lambda: next(stage_ids))

    ordered = [
        (TraceStageName.RUNTIME_PROFILE_RESOLUTION, TraceStageOutcome.SUCCESS),
        (TraceStageName.GATEWAY_REQUEST, TraceStageOutcome.UNSUPPORTED),
        (TraceStageName.FALLBACK, TraceStageOutcome.TEXT_FALLBACK),
        (TraceStageName.GATEWAY_REQUEST, TraceStageOutcome.SUCCESS),
        (TraceStageName.PROXY_PREPARE_QUEUE, TraceStageOutcome.SUCCESS),
        (TraceStageName.PROXY_READY_QUEUE, TraceStageOutcome.SUCCESS),
        (TraceStageName.FIRST_TOKEN, TraceStageOutcome.SUCCESS),
        (TraceStageName.DECODE, TraceStageOutcome.SUCCESS),
        (TraceStageName.COMPLETION, TraceStageOutcome.SUCCESS),
    ]
    for index, (name, outcome) in enumerate(ordered):
        stage_id = collector.start_stage(name, provenance)
        if name is TraceStageName.PROXY_READY_QUEUE:
            collector.append_measurement(stage_id, TraceMeasurement(
                name="queue_wait", kind=TraceValueKind.PREDICTED, provenance=provenance,
                duration_ns=2_000_000,
            ))
            collector.append_measurement(stage_id, TraceMeasurement(
                name="queue_wait", kind=TraceValueKind.ACTUAL, provenance=provenance,
                duration_ns=3_000_000,
            ))
        clock.advance_ns(100 + index)
        clock.advance_time(timedelta(microseconds=1))
        collector.finish_stage(stage_id, outcome)

    request_trace = collector.export(complete=True)
    operation = CacheOperationTrace(
        operation_id="cacheop-demo", trace_id=context.trace_id, operation="prefetch",
        state="succeeded", stages=request_trace.stages[1:4], provenance=provenance,
        artifact_id="artifact-demo", endpoint_id="endpoint-demo", endpoint_generation=1,
        created_at=context.created_at, updated_at=clock.utc_now(), completed_at=clock.utc_now(),
    )
    waiters = tuple(OperationWaiterLink(
        operation_id=operation.operation_id, trace_id=f"trace_{number:032x}",
        request_id=f"req-waiter-{number}", correlation_id="corr-demo",
        attach_sequence=number - 2, attached_at=clock.utc_now(),
        state=OperationWaiterState.COMPLETED,
    ) for number in (2, 3))
    legacy = project_legacy_proxy_trace(
        request_id="req-legacy", correlation_id="corr-legacy", legacy_request_id=7,
        trace={
            "predict_prepare_ms": 12, "actual_vllm_internal_ms": 8,
            "first_token_ms": 1760000000000, "kvcache_actual_path": "kv_inject_failed_fallback_text",
            "error": "raw exception must be omitted", "unknown_secretish_result": "omitted",
        },
        kv_ack={"payload_bytes": 1024, "raw": "omitted"}, exported_at=clock.utc_now(),
        runtime_profile="legacy",
    )

    output = {
        "request_trace": request_trace.model_dump(mode="json"),
        "stage_sequence": [stage.name.value for stage in request_trace.stages],
        "value_kinds": [
            measurement.kind.value for stage in request_trace.stages
            for measurement in stage.measurements
        ],
        "cache_operation": operation.model_dump(mode="json"),
        "shared_operation_waiter_ids": [waiter.request_id for waiter in waiters],
        "legacy_projection": legacy.model_dump(mode="json"),
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    print("observability v1 demo: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
