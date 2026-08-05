from datetime import datetime, timezone
from types import SimpleNamespace
import pytest

from cacheroute.contracts.v1 import OutcomeCode
from cacheroute.observability import ManualTraceClock, TraceCollector, create_trace_context, encode_trace_headers
from cacheroute.observability.propagation import RESERVED_TRACE_HEADERS, TRACE_ID_HEADER
from cacheroute.observability.v1 import TraceComponent, TraceProvenance, TraceStageName
from cacheroute.runtime import RuntimeProfile
from proxy.queue.manager import QueueManager, _EMPTY_STREAM, _DOWNSTREAM_FAILED, _REQUEST_CANCELLED
from proxy.queue.task import ProxyTask
from proxy.proxy import build_cacheroute_meta, build_proxy_trace
from scheduler.scheduler import build_proxy_headers, resolve_scheduler_observability_startup

NOW = datetime(2026, 8, 4, 12, tzinfo=timezone.utc)
TRACE_ID = "trace_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _app(profile=RuntimeProfile.LEGACY, rate=1.0):
    return SimpleNamespace(state=SimpleNamespace(runtime_profile=profile, trace_sample_rate=rate, trace_clock=ManualTraceClock(NOW)))


def _request(headers, app=None):
    return SimpleNamespace(headers=headers, app=app or _app())


def _req_obj(rid=42, injection="text"):
    return SimpleNamespace(
        Request_ID=rid,
        Prompt=SimpleNamespace(token_length=1, model="m", user_prompt="prompt", stream=True),
        Service=SimpleNamespace(Knowledge_length=0, Injection_type=injection, Enable_know_injection=False, Knowledge_List=[]),
        Task=SimpleNamespace(KDN_server_addr="kdn"),
    )


def _task(clock=None, sampled=True):
    clock = clock or ManualTraceClock(NOW)
    ctx = create_trace_context("42", RuntimeProfile.LEGACY, sample_rate=1.0 if sampled else 0.0, clock=clock, trace_id=TRACE_ID)
    collector = TraceCollector(ctx, clock=clock, id_factory=iter(["stage_prepare", "stage_ready", "stage_completion", "stage_first", "stage_decode"]).__next__)
    provenance = TraceProvenance(source_component=TraceComponent.PROXY, runtime_profile=ctx.runtime_profile, captured_at=clock.utc_now())
    return ProxyTask(42, _req_obj(), {}, "inst", "127.0.0.1", 9001, "/v1/chat/completions", trace_context=ctx, trace_collector=collector, trace_provenance=provenance)


def test_scheduler_headers_overwrite_authorization_and_payload_boundary():
    app = _app()
    raw = {"authorization": "Bearer kept", **{name: "client" for name in RESERVED_TRACE_HEADERS}}
    headers = build_proxy_headers(app, raw, 99)
    assert headers["authorization"] == "Bearer kept"
    assert headers["scheduler-request-id"] == "99"
    assert all(headers[name] != "client" for name in RESERVED_TRACE_HEADERS)
    assert set(headers) == set(RESERVED_TRACE_HEADERS) | {"authorization"}
    payload = {"Request_ID": 99, "Prompt": {"user_prompt": "secret"}}
    assert not (set(payload) & set(RESERVED_TRACE_HEADERS))
    assert resolve_scheduler_observability_startup("auto", 1.0).runtime_profile is RuntimeProfile.LEGACY


def test_proxy_acceptance_and_fallback_reasons():
    headers = encode_trace_headers(create_trace_context("42", RuntimeProfile.LEGACY, sample_rate=1.0, clock=ManualTraceClock(NOW), trace_id=TRACE_ID))
    ctx, collector, provenance = build_proxy_trace(_request(headers), 42)
    assert ctx.trace_id == TRACE_ID
    assert collector.context is ctx
    assert provenance.source_component is TraceComponent.PROXY
    assert provenance.runtime_profile is RuntimeProfile.LEGACY

    malformed = dict(headers)
    malformed[TRACE_ID_HEADER] = "bad"
    fallback, _, _ = build_proxy_trace(_request(malformed), 42)
    assert fallback.request_id == "42" and fallback.trace_id != TRACE_ID

    mismatch, _, _ = build_proxy_trace(_request(headers), 43)
    assert mismatch.request_id == "43" and mismatch.trace_id != TRACE_ID

    profile_mismatch, _, _ = build_proxy_trace(_request(headers, _app(RuntimeProfile.TEST_MOCK)), 42)
    assert profile_mismatch.runtime_profile is RuntimeProfile.TEST_MOCK
    assert profile_mismatch.trace_id != TRACE_ID


def test_unsampled_context_produces_no_stages_and_legacy_meta_keys_unchanged():
    task = _task(sampled=False)
    manager = QueueManager()
    task.prepare_queue_stage_id = manager._start_stage(task, TraceStageName.PROXY_PREPARE_QUEUE)
    manager._finish_stage(task, task.prepare_queue_stage_id, OutcomeCode.SUCCESS)
    manager._finalize_trace(task, OutcomeCode.SUCCESS)
    assert task.request_trace is not None
    assert task.request_trace.stages == ()
    task.trace["proxy_enqueue_ms"] = 1
    assert list(build_cacheroute_meta(task)) == ["trace", "kv_ack", "kv_ready_kids", "text_only_kids", "miss_kids", "error"]
    assert build_cacheroute_meta(task)["trace"] == {"proxy_enqueue_ms": 1}


def test_ready_stage_excludes_reservation_time_and_prepare_is_monotonic():
    clock = ManualTraceClock(NOW)
    task = _task(clock)
    manager = QueueManager()
    task.prepare_queue_stage_id = manager._start_stage(task, TraceStageName.PROXY_PREPARE_QUEUE)
    clock.advance(nanoseconds=5_000_000)
    manager._finish_stage(task, task.prepare_queue_stage_id, OutcomeCode.SUCCESS)
    clock.advance(nanoseconds=100_000_000)  # reservation/prediction time before canonical ready queue
    task.ready_queue_stage_id = manager._start_stage(task, TraceStageName.PROXY_READY_QUEUE)
    clock.advance(nanoseconds=7_000_000)
    manager._finish_stage(task, task.ready_queue_stage_id, OutcomeCode.SUCCESS)
    manager._finalize_trace(task, OutcomeCode.SUCCESS)
    stages = {stage.name: stage for stage in task.request_trace.stages}
    assert stages[TraceStageName.PROXY_PREPARE_QUEUE].elapsed_ns == 5_000_000
    assert stages[TraceStageName.PROXY_READY_QUEUE].elapsed_ns == 7_000_000


def test_streaming_nonstreaming_empty_failure_and_safe_errors_have_valid_hierarchy():
    clock = ManualTraceClock(NOW)
    task = _task(clock)
    manager = QueueManager()
    task.completion_stage_id = manager._start_stage(task, TraceStageName.COMPLETION)
    task.first_token_stage_id = manager._start_stage(task, TraceStageName.FIRST_TOKEN, parent=task.completion_stage_id)
    clock.advance(nanoseconds=3)
    manager._finish_stage(task, task.first_token_stage_id, OutcomeCode.FAILED, _EMPTY_STREAM)
    task.trace_collector.skip_stage(TraceStageName.DECODE, task.trace_provenance, reason="stream_ended_before_decode", parent_stage_id=task.completion_stage_id)
    manager._finish_stage(task, task.completion_stage_id, OutcomeCode.FAILED, _EMPTY_STREAM)
    manager._finalize_trace(task, OutcomeCode.FAILED, _EMPTY_STREAM)
    assert task.request_trace.outcome is OutcomeCode.FAILED
    assert task.request_trace.error == _EMPTY_STREAM
    assert all(stage.state.value != "running" for stage in task.request_trace.stages)
    assert [stage.sequence for stage in task.request_trace.stages] == [0, 1, 2]
    assert all("prompt" not in task.request_trace.model_dump_json().lower() for _ in [0])

    for error in (_EMPTY_STREAM, _DOWNSTREAM_FAILED, _REQUEST_CANCELLED):
        assert "exception" not in error.message
        assert "authorization" not in error.message


def test_no_reserved_header_sent_to_instance_contract():
    task = _task()
    task.instance_body = {"model": "m", "messages": [{"role": "user", "content": "prompt"}], "stream": True}
    assert not (set(task.instance_body) & set(RESERVED_TRACE_HEADERS))
