from datetime import datetime, timedelta, timezone
import itertools

import pytest

from cacheroute.observability import ManualTraceClock, TraceCollector
from cacheroute.observability.v1 import TraceContext, TraceMeasurement, TraceProvenance, TraceStageName

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def setup(*, sampled=True, enabled=True):
    clock = ManualTraceClock(NOW, 10)
    context = TraceContext(trace_id="t", request_id="r", runtime_profile="test/mock", sampled=sampled, created_at=NOW)
    provenance = TraceProvenance(source_component="test", runtime_profile="test/mock", captured_at=NOW)
    ids = (f"stage_{n}" for n in itertools.count())
    return clock, provenance, TraceCollector(context, clock=clock, id_factory=ids.__next__, enabled=enabled)


def test_deterministic_repeated_stages_and_monotonic_duration():
    clock, provenance, collector = setup()
    for elapsed in (5, 8):
        stage_id = collector.start_stage(TraceStageName.GATEWAY_REQUEST, provenance)
        collector.append_measurement(stage_id, TraceMeasurement(code="attempt", value_kind="measured", count=1))
        clock.advance(nanoseconds=elapsed, wall_time=timedelta(seconds=20))
        collector.finish_stage(stage_id, outcome="success")
    trace = collector.export(cache_operation_ids=("op1",))
    assert [stage.sequence for stage in trace.stages] == [0, 1]
    assert [stage.elapsed_ns for stage in trace.stages] == [5, 8]
    assert trace.stages[0].finished_at - trace.stages[0].started_at == timedelta(seconds=20)


def test_invalid_lifecycle_duplicate_unknown_and_parent():
    clock, provenance, collector = setup()
    first = collector.start_stage("decode", provenance, stage_id="same")
    with pytest.raises(ValueError): collector.start_stage("decode", provenance, stage_id="same")
    with pytest.raises(ValueError): collector.append_measurement("unknown", TraceMeasurement(code="x", value_kind="actual", count=1))
    with pytest.raises(ValueError): collector.start_stage("decode", provenance, parent_stage_id="unknown")
    clock.advance(nanoseconds=1); collector.finish_stage(first, outcome="success")
    with pytest.raises(ValueError): collector.finish_stage(first, outcome="success")
    with pytest.raises(ValueError): collector.append_measurement(first, TraceMeasurement(code="x", value_kind="actual", count=1))


@pytest.mark.parametrize("sampled,enabled", [(False, True), (True, False)])
def test_disabled_and_unsampled_are_noops(sampled, enabled):
    _, provenance, collector = setup(sampled=sampled, enabled=enabled)
    assert collector.start_stage("decode", provenance) is None
    collector.append_measurement(None, TraceMeasurement(code="x", value_kind="actual", count=1))
    collector.finish_stage(None, outcome="success")
    assert collector.export().stages == ()


def test_manual_clock_rejects_negative_movement():
    clock = ManualTraceClock(NOW)
    with pytest.raises(ValueError): clock.advance(nanoseconds=-1)


def test_collector_rejects_a_backwards_monotonic_source():
    class BackwardsClock:
        def __init__(self): self.value = 10
        def utc_now(self): return NOW
        def monotonic_ns(self): return self.value

    clock = BackwardsClock()
    context = TraceContext(trace_id="t", request_id="r", runtime_profile="test/mock", created_at=NOW)
    provenance = TraceProvenance(source_component="test", runtime_profile="test/mock", captured_at=NOW)
    collector = TraceCollector(context, clock=clock, id_factory=lambda: "stage")
    stage = collector.start_stage("decode", provenance)
    clock.value = 9
    with pytest.raises(ValueError, match="backwards"):
        collector.finish_stage(stage, outcome="success")
