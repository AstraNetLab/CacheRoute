from datetime import timedelta

import pytest
from pydantic import ValidationError

from cacheroute_observability import (
    ManualTraceClock, TraceCollector, TraceMeasurement, TraceStageName,
)


def _ids():
    return iter(f"stage_{i:032x}" for i in range(1, 20))


def test_order_repetition_monotonic_and_snapshot(context, provenance, now):
    clock = ManualTraceClock(now, 100)
    ids = _ids()
    collector = TraceCollector(context, clock=clock, id_factory=lambda: next(ids))
    names = ["gateway_request", "fallback", "gateway_request", "completion"]
    first_snapshot = None
    for index, name in enumerate(names):
        stage_id = collector.start_stage(name, provenance)
        if index == 0:
            collector.append_measurement(stage_id, TraceMeasurement(
                name="latency", kind="predicted", provenance=provenance, duration_ns=4))
            collector.append_measurement(stage_id, TraceMeasurement(
                name="latency", kind="actual", provenance=provenance, duration_ns=5))
        clock.advance_ns(index)
        clock.advance_time(timedelta(seconds=20 if index == 0 else 0))
        collector.finish_stage(stage_id, "text_fallback" if name == "fallback" else "success")
        if index == 0:
            first_snapshot = collector.export()
    final = collector.export(complete=True)
    assert [stage.name.value for stage in final.stages] == names
    assert [stage.duration_ns for stage in final.stages] == [0, 1, 2, 3]
    assert len(first_snapshot.stages) == 1
    assert [m.kind.value for m in final.stages[0].measurements] == ["predicted", "actual"]
    with pytest.raises(ValidationError):
        final.stages += ()


def test_finish_errors(context, provenance, now):
    clock = ManualTraceClock(now, 10)
    ids = _ids()
    collector = TraceCollector(context, clock=clock, id_factory=lambda: next(ids))
    with pytest.raises(KeyError):
        collector.finish_stage("stage_" + "9" * 32, "success")
    stage_id = collector.start_stage(TraceStageName.COMPLETION, provenance)
    collector.finish_stage(stage_id, "success")
    with pytest.raises(ValueError):
        collector.finish_stage(stage_id, "success")


def test_disabled_and_unsampled(context, provenance, now):
    disabled = TraceCollector(context, enabled=False)
    assert disabled.start_stage("completion", provenance) is None
    assert disabled.export().stages == ()
    unsampled_context = context.model_copy(update={"sampled": False})
    unsampled = TraceCollector(unsampled_context)
    assert unsampled.start_stage("completion", provenance) is None
    assert unsampled.export().context.sampled is False
    assert unsampled.safely(lambda: 1 / 0, "unchanged") == "unchanged"


def test_negative_monotonic_duration_rejected(context, provenance, now):
    clock = ManualTraceClock(now, 10)
    ids = _ids()
    collector = TraceCollector(context, clock=clock, id_factory=lambda: next(ids))
    stage_id = collector.start_stage("completion", provenance)
    clock._monotonic_value = 9
    with pytest.raises(ValueError):
        collector.finish_stage(stage_id, "success")
