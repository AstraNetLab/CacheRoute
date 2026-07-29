from datetime import timedelta

import pytest
from pydantic import ValidationError

from cacheroute_observability import (
    CacheOperationTrace, OperationWaiterLink, OperationWaiterState, RequestTrace,
    TraceComponent, TraceContext, TraceMeasurement, TraceProvenance, TraceStage,
    TraceStageOutcome, TraceValueKind,
)


def test_context_is_frozen_utc_and_round_trips(context):
    with pytest.raises(ValidationError):
        context.request_id = "changed"
    encoded = context.model_dump_json()
    assert '"created_at":"2026-01-01T00:00:00Z"' in encoded
    assert TraceContext.model_validate_json(encoded) == context


def test_context_validation(now):
    with pytest.raises(ValidationError):
        TraceContext(trace_id="bad", request_id="r", correlation_id="c", created_at=now)
    with pytest.raises(ValidationError):
        TraceContext(trace_id="trace_" + "0" * 32, request_id="r", correlation_id="c",
                     created_at=now.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        TraceContext(trace_id="trace_" + "0" * 32, request_id="r", correlation_id="c",
                     created_at=now, expires_at=now)


def test_endpoint_generation_and_freshness(now):
    current = TraceProvenance(source_component="gateway", runtime_profile="v1",
                              captured_at=now, endpoint_id="endpoint-1", endpoint_generation=1,
                              fresh_until=now + timedelta(seconds=1))
    assert current.endpoint_generation == 1
    legacy = TraceProvenance(source_component="legacy_adapter", runtime_profile="legacy",
                             captured_at=now, endpoint_id="endpoint-old", endpoint_generation=0,
                             legacy=True)
    assert legacy.endpoint_generation == 0
    for values in (
        {"endpoint_id": "endpoint-1"},
        {"endpoint_id": "endpoint-1", "endpoint_generation": 0},
        {"fresh_until": now - timedelta(microseconds=1)},
    ):
        with pytest.raises(ValidationError):
            TraceProvenance(source_component="gateway", runtime_profile="v1", captured_at=now, **values)


def test_measurement_exact_value_and_ranges(provenance):
    predicted = TraceMeasurement(name="queue_wait", kind="predicted", provenance=provenance,
                                 duration_ns=0)
    actual = TraceMeasurement(name="queue_wait", kind="actual", provenance=provenance,
                              duration_ns=4)
    assert (predicted.kind, actual.kind) == (TraceValueKind.PREDICTED, TraceValueKind.ACTUAL)
    for values in ({}, {"count": 1, "tokens": 2}, {"duration_ns": -1}, {"ratio": float("nan")}, {"ratio": 1.1}):
        with pytest.raises(ValidationError):
            TraceMeasurement(name="bad", kind="observed", provenance=provenance, **values)


def test_stage_state_outcome_and_time_rules(now, provenance):
    base = dict(stage_id="stage_" + "2" * 32, sequence=0, name="completion",
                provenance=provenance, started_at=now)
    with pytest.raises(ValidationError):
        TraceStage(**base, state="completed", ended_at=now, duration_ns=0)
    with pytest.raises(ValidationError):
        TraceStage(**base, state="running", outcome="success")
    with pytest.raises(ValidationError):
        TraceStage(**base, state="completed", outcome="success",
                   ended_at=now - timedelta(seconds=1), duration_ns=1)
    complete = TraceStage(**base, state="completed", outcome="success", ended_at=now, duration_ns=0)
    assert complete.outcome is TraceStageOutcome.SUCCESS


def test_request_and_shared_operation_models(now, context, provenance):
    stage = TraceStage(stage_id="stage_" + "3" * 32, sequence=0, name="cache_operation_queue",
                       state="completed", outcome="success", provenance=provenance,
                       started_at=now, ended_at=now, duration_ns=0)
    trace = RequestTrace(context=context, stages=(stage,), exported_at=now, complete=True,
                         source_components=(TraceComponent.TEST,))
    assert RequestTrace.model_validate_json(trace.model_dump_json()) == trace
    operation = CacheOperationTrace(
        operation_id="cacheop-1", trace_id=context.trace_id, operation="prefetch",
        state="succeeded", stages=(stage,), provenance=provenance, artifact_id="artifact-1",
        endpoint_id="endpoint-1", endpoint_generation=1, created_at=now, updated_at=now,
        completed_at=now,
    )
    waiters = tuple(OperationWaiterLink(
        operation_id=operation.operation_id, trace_id="trace_" + str(i) * 32,
        request_id=f"req-{i}", correlation_id="corr", attach_sequence=i,
        attached_at=now, state=OperationWaiterState.WAITING,
    ) for i in (1, 2))
    assert [waiter.attach_sequence for waiter in waiters] == [1, 2]
