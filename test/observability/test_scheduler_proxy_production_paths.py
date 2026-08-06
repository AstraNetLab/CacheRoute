from contextlib import suppress
from datetime import datetime, timezone
from types import SimpleNamespace
import asyncio
import json
import logging
import importlib

import pytest

from core import Request as SchedulerRequest
from cacheroute.contracts.v1 import OutcomeCode
from cacheroute.observability import ManualTraceClock, TraceCollector, create_trace_context, encode_trace_headers, is_trace_sampled
from cacheroute.observability.propagation import RESERVED_TRACE_HEADERS, TRACE_ID_HEADER
from cacheroute.observability.v1 import TraceComponent, TraceStageName
from cacheroute.runtime import RuntimeProfile
from proxy.queue.manager import QueueManager, _EMPTY_STREAM, _DOWNSTREAM_FAILED, _REQUEST_CANCELLED
from proxy.queue.task import ProxyTask
from proxy.proxy import build_body_for_instance, build_cacheroute_meta, build_proxy_trace, recover_request_from_payload, resolve_proxy_observability_startup
from scheduler.scheduler import build_proxy_headers, resolve_scheduler_observability_startup

NOW = datetime(2026, 8, 4, 12, tzinfo=timezone.utc)
TRACE_ID = "trace_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class _CaseDone(Exception):
    pass


def _app(profile=RuntimeProfile.LEGACY, rate=1.0, clock=None):
    return SimpleNamespace(state=SimpleNamespace(runtime_profile=profile, trace_sample_rate=rate, trace_clock=clock or ManualTraceClock(NOW)))


def _request(headers, app=None):
    return SimpleNamespace(headers=headers, app=app or _app())


def _scheduler_request(rid=42, *, stream=True, endpoint="chat/completions"):
    payload = {
        "model": "unit-model",
        "max_tokens": 4,
        "temperature": 1.0,
        "top_p": 1.0,
        "stream": stream,
    }
    url = "/v1/chat/completions" if endpoint == "chat/completions" else "/v1/completions"
    if endpoint == "chat/completions":
        payload["messages"] = [{"role": "user", "content": "hello"}]
    else:
        payload["prompt"] = "hello"
    req = SchedulerRequest.build_request(url, payload, "127.0.0.1", rid)
    req.Task.KDN_server_addr = "kdn.local:7003"
    req.Task.P_proxy_id = "proxy_a"
    req.Task.P_proxy_addr = "127.0.0.1"
    req.Task.P_proxy_port = 8002
    return req


def _task_from_request(req_obj, *, sampled=True, trace_id=TRACE_ID, clock=None):
    clock = clock or ManualTraceClock(NOW)
    ctx = create_trace_context(req_obj.Request_ID, RuntimeProfile.LEGACY, sample_rate=1.0 if sampled else 0.0, clock=clock, trace_id=trace_id)
    collector = TraceCollector(
        ctx,
        clock=clock,
        id_factory=iter(["stage_prepare", "stage_ready", "stage_completion", "stage_first", "stage_decode"]).__next__,
    )
    from cacheroute.observability.v1 import TraceProvenance
    provenance = TraceProvenance(source_component=TraceComponent.PROXY, runtime_profile=ctx.runtime_profile, captured_at=clock.utc_now())
    mode = "chat" if req_obj.Service.Endpoint_type == "chat/completions" else "completions"
    return ProxyTask(
        req_obj.Request_ID,
        req_obj,
        build_body_for_instance(req_obj, mode=mode),
        "inst-a",
        "127.0.0.1",
        9001,
        f"/v1/{req_obj.Service.Endpoint_type}",
        kdn_addr=req_obj.Task.KDN_server_addr,
        trace_context=ctx,
        trace_collector=collector,
        trace_provenance=provenance,
    )


async def _drain_until_done(task, timeout=2.0):
    chunks = []
    while True:
        item = await asyncio.wait_for(task.response_queue.get(), timeout=timeout)
        if item is None:
            return chunks
        chunks.append(item)


async def _run_real_queue(monkeypatch, task, chunks=(), *, fail_at=None, cancel_after_first=False):
    calls = []
    manager = QueueManager()
    manager._READY_DEQUEUE_INTERVAL_S = 0.0
    task.trace["preexisting"] = 7

    async def fake_forward_request(url, data, use_chunked=False, extra_headers=None):
        calls.append({"url": url, "data": data.copy(), "use_chunked": use_chunked, "headers": dict(extra_headers or {})})
        if fail_at == "before_first":
            raise RuntimeError("raw downstream boom should not enter trace")
        for index, chunk in enumerate(chunks):
            yield chunk
            if cancel_after_first and index == 0:
                await asyncio.sleep(10)
            if fail_at == "after_first" and index == 0:
                raise RuntimeError("raw downstream boom should not enter trace")

    monkeypatch.setattr("proxy.queue.manager.forward_request", fake_forward_request)
    await manager.enqueue_prepare(task)
    output_task = asyncio.create_task(_drain_until_done(task))
    if cancel_after_first:
        await asyncio.sleep(0.05)
        for worker in manager._worker_tasks.values():
            worker.cancel()
    try:
        output = await output_task
    finally:
        for worker in manager._worker_tasks.values():
            worker.cancel()
        await asyncio.gather(*manager._worker_tasks.values(), return_exceptions=True)
    return manager, output, calls


async def _run_timed_real_queue(monkeypatch, task, clock):
    calls = []
    manager = QueueManager()
    manager._READY_DEQUEUE_INTERVAL_S = 0.0

    def start_without_workers(instance_id):
        manager._ensure_instance_reservation_state(instance_id)
    monkeypatch.setattr(manager, "_start_workers_for_instance", start_without_workers)

    original_reserve = manager._reserve_ready_task
    async def reserve_with_prediction_time(reserved_task, now_s=None):
        clock.advance(nanoseconds=100_000_000)
        await original_reserve(reserved_task, now_s=now_s)
    monkeypatch.setattr(manager, "_reserve_ready_task", reserve_with_prediction_time)

    async def dispatch_wait(wait_task, instance_id):
        clock.advance(nanoseconds=7_000_000)
        wait_task.has_started_forward = True
    monkeypatch.setattr(manager, "_wait_dispatch_turn", dispatch_wait)

    async def timed_forward_request(url, data, use_chunked=False, extra_headers=None):
        calls.append({"url": url, "data": data.copy(), "use_chunked": use_chunked, "headers": dict(extra_headers or {})})
        clock.advance(nanoseconds=11_000_000)
        yield b"data: token\n\n"
        clock.advance(nanoseconds=13_000_000)

    monkeypatch.setattr("proxy.queue.manager.forward_request", timed_forward_request)
    await manager.enqueue_prepare(task)
    clock.advance(nanoseconds=5_000_000)
    prepare_worker = asyncio.create_task(manager._prepare_dispatch_loop(task.instance_id))
    ready_worker = asyncio.create_task(manager._ready_worker_loop(task.instance_id, 0))
    try:
        output = await _drain_until_done(task)
    finally:
        for worker in (prepare_worker, ready_worker):
            worker.cancel()
        await asyncio.gather(prepare_worker, ready_worker, return_exceptions=True)
    return output, calls


def _assert_no_running_and_valid_refs(request_trace):
    assert request_trace is not None
    assert all(stage.state.value != "running" for stage in request_trace.stages)
    assert [stage.sequence for stage in request_trace.stages] == sorted(stage.sequence for stage in request_trace.stages)
    ids = {stage.stage_id for stage in request_trace.stages}
    assert all(stage.parent_stage_id is None or stage.parent_stage_id in ids for stage in request_trace.stages)
    assert all(stage.provenance.source_component is TraceComponent.PROXY for stage in request_trace.stages)


def test_startup_warning_reason_codes_are_bounded_and_non_blocking(caplog):
    assert resolve_scheduler_observability_startup("legacy", "0.0").sample_rate_warning_reason is None
    for value, reason in [("bad", "trace_sample_rate_malformed"), ("nan", "trace_sample_rate_non_finite"), ("-1", "trace_sample_rate_below_zero"), ("2", "trace_sample_rate_above_one")]:
        config = resolve_proxy_observability_startup("auto", value)
        assert config.trace_sample_rate == 0.0
        assert config.runtime_profile is RuntimeProfile.LEGACY
        assert config.sample_rate_warning_reason == reason
    caplog.set_level(logging.WARNING)
    config = resolve_scheduler_observability_startup("legacy", "bad")
    logging.getLogger("scheduler").warning("[Scheduler] observability startup warning reason=%s", config.sample_rate_warning_reason)
    assert caplog.text.count("trace_sample_rate_malformed") == 1
    assert "bad" not in caplog.text
    headers = build_proxy_headers(_app(rate=config.trace_sample_rate), {"authorization": "Bearer kept"}, 11)
    assert headers["scheduler-request-id"] == "11"


def test_scheduler_headers_overwrite_authorization_and_actual_payload_boundary():
    req = _scheduler_request(99)
    payload = req.to_payload()
    headers = build_proxy_headers(_app(), {"authorization": "Bearer kept", **{name: "client" for name in RESERVED_TRACE_HEADERS}}, req.Request_ID)
    assert headers["authorization"] == "Bearer kept"
    assert headers["scheduler-request-id"] == "99"
    assert all(headers[name] != "client" for name in RESERVED_TRACE_HEADERS)
    assert not (set(payload) & set(RESERVED_TRACE_HEADERS))
    assert recover_request_from_payload(payload).Request_ID == req.Request_ID


def test_proxy_acceptance_fallback_and_deterministic_local_sampling():
    headers = encode_trace_headers(create_trace_context("42", RuntimeProfile.LEGACY, sample_rate=1.0, clock=ManualTraceClock(NOW), trace_id=TRACE_ID))
    ctx, collector, provenance = build_proxy_trace(_request(headers), 42)
    assert ctx.trace_id == TRACE_ID and ctx.sampled is True
    assert collector.context is ctx
    assert provenance.source_component is TraceComponent.PROXY
    malformed = dict(headers)
    malformed[TRACE_ID_HEADER] = "bad"
    fallback_id = "trace_cccccccccccccccccccccccccccccccc"
    proxy_module = importlib.import_module("proxy.proxy")
    def fixed_fallback(request_id, runtime_profile, *, sample_rate=0.0, clock=None, trace_id=None):
        return create_trace_context(request_id, runtime_profile, sample_rate=sample_rate, clock=clock, trace_id=fallback_id)
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(proxy_module, "create_trace_context", fixed_fallback)
        app = _app(rate=0.5)
        first, _, _ = build_proxy_trace(_request(malformed, app), 42)
        second, _, _ = build_proxy_trace(_request(malformed, app), 42)
    finally:
        monkeypatch.undo()
    assert first.request_id == "42" and first.trace_id == fallback_id
    assert second.trace_id == fallback_id
    assert first.sampled == second.sampled == is_trace_sampled(fallback_id, 0.5)
    mismatch, _, _ = build_proxy_trace(_request(headers, _app(RuntimeProfile.TEST_MOCK)), 42)
    assert mismatch.runtime_profile is RuntimeProfile.TEST_MOCK


@pytest.mark.parametrize(("endpoint", "chunks", "expected_outcome", "expected_error"), [
    ("chat/completions", [b"data: token\\n\\n", b"data: [DONE]\\n\\n"], OutcomeCode.SUCCESS, None),
    ("completions", [json.dumps({"choices": [{"text": "ok"}]}).encode()], OutcomeCode.SUCCESS, None),
    ("chat/completions", [], OutcomeCode.FAILED, _EMPTY_STREAM),
])
def test_real_ready_worker_success_nonstream_and_empty_paths(monkeypatch, endpoint, chunks, expected_outcome, expected_error):
    async def scenario():
        req = _scheduler_request(42, stream=endpoint == "chat/completions", endpoint=endpoint)
        task = _task_from_request(req)
        original_body = task.instance_body.copy()
        original_trace = dict(task.trace)
        _manager, output, calls = await _run_real_queue(monkeypatch, task, chunks=chunks)
        assert output == chunks
        assert calls and calls[0]["url"] == f"http://{task.instance_host}:{task.instance_port}{task.url_path}"
        assert calls[0]["data"] == original_body
        assert calls[0]["use_chunked"] is (endpoint == "chat/completions")
        assert set(calls[0].get("headers", {})) == set(RESERVED_TRACE_HEADERS)
        assert task.request_trace.outcome is expected_outcome
        assert task.request_trace.error == expected_error
        _assert_no_running_and_valid_refs(task.request_trace)
        assert task.trace["preexisting"] == 7
        assert all(item in task.trace.items() for item in original_trace.items())
        names = [stage.name for stage in task.request_trace.stages]
        assert TraceStageName.PROXY_PREPARE_QUEUE in names
        assert TraceStageName.PROXY_READY_QUEUE in names
        assert TraceStageName.COMPLETION in names
        if endpoint == "completions":
            skipped = [stage for stage in task.request_trace.stages if stage.state.value == "skipped"]
            assert {stage.name for stage in skipped} == {TraceStageName.FIRST_TOKEN, TraceStageName.DECODE}
    asyncio.run(scenario())


@pytest.mark.parametrize(("fail_at", "expected_error"), [
    ("before_first", _DOWNSTREAM_FAILED),
    ("after_first", _DOWNSTREAM_FAILED),
])
def test_real_ready_worker_failure_paths(monkeypatch, fail_at, expected_error):
    async def scenario():
        req = _scheduler_request(42)
        task = _task_from_request(req)
        _manager, output, calls = await _run_real_queue(monkeypatch, task, chunks=[b"data: token\\n\\n"], fail_at=fail_at)
        assert output == ([] if fail_at == "before_first" else [b"data: token\\n\\n"])
        assert calls
        assert task.request_trace.outcome is OutcomeCode.FAILED
        assert task.request_trace.error == expected_error
        assert "raw downstream" not in task.request_trace.model_dump_json()
        _assert_no_running_and_valid_refs(task.request_trace)
    asyncio.run(scenario())


@pytest.mark.parametrize("cancel_after_first", [False, True])
def test_real_ready_worker_cancellation_paths(monkeypatch, cancel_after_first):
    async def scenario():
        req = _scheduler_request(42)
        task = _task_from_request(req)
        chunks = [b"data: token\\n\\n"] if cancel_after_first else []

        async def fake_forward_request(url, data, use_chunked=False):
            if not cancel_after_first:
                await asyncio.sleep(10)
                yield b""
            else:
                yield chunks[0]
                await asyncio.sleep(10)

        monkeypatch.setattr("proxy.queue.manager.forward_request", fake_forward_request)
        manager = QueueManager(); manager._READY_DEQUEUE_INTERVAL_S = 0.0
        await manager.enqueue_prepare(task)
        await asyncio.sleep(0.05)
        for worker in manager._worker_tasks.values():
            worker.cancel()
        with suppress(asyncio.CancelledError, TimeoutError):
            await asyncio.wait_for(_drain_until_done(task), timeout=1.0)
        await asyncio.gather(*manager._worker_tasks.values(), return_exceptions=True)
        assert task.request_trace.outcome is OutcomeCode.CANCELLED
        assert task.request_trace.error == _REQUEST_CANCELLED
        _assert_no_running_and_valid_refs(task.request_trace)
    asyncio.run(scenario())


def test_unsampled_real_queue_records_no_stages_and_metadata_shapes(monkeypatch):
    async def scenario():
        req = _scheduler_request(42)
        task = _task_from_request(req, sampled=False)
        _manager, output, _calls = await _run_real_queue(monkeypatch, task, chunks=[b"data: token\\n\\n"])
        assert output == [b"data: token\\n\\n"]
        assert task.request_trace.stages == ()
        meta = build_cacheroute_meta(task)
        assert list(meta) == ["trace", "kv_ack", "kv_ready_kids", "text_only_kids", "miss_kids", "error"]
        sse = ("event: cacheroute_meta\n" f"data: {json.dumps(meta, ensure_ascii=False)}\n\n").encode()
        assert sse.startswith(b"event: cacheroute_meta\n")
        nonstream = {"choices": [], "_cacheroute_meta": meta}
        assert list(nonstream) == ["choices", "_cacheroute_meta"]
    asyncio.run(scenario())


def test_cpu_only_scheduler_to_proxy_integration_with_real_workers(monkeypatch):
    async def scenario():
        scheduler_clock = ManualTraceClock(NOW)
        req = _scheduler_request(123)
        def fixed_context(request_id, runtime_profile, *, sample_rate=0.0, clock=None, trace_id=None):
            return create_trace_context(request_id, runtime_profile, sample_rate=1.0, clock=clock, trace_id=TRACE_ID)
        scheduler_module = importlib.import_module("scheduler.scheduler")
        monkeypatch.setattr(scheduler_module, "create_trace_context", fixed_context)
        headers = build_proxy_headers(_app(clock=scheduler_clock), {}, req.Request_ID)
        trace_id = headers[TRACE_ID_HEADER]
        recovered = recover_request_from_payload(req.to_payload())
        proxy_clock = ManualTraceClock(NOW)
        context, _collector, provenance = build_proxy_trace(_request(headers, _app(clock=proxy_clock)), recovered.Request_ID)
        collector = TraceCollector(context, clock=proxy_clock, id_factory=iter(["stage_prepare", "stage_ready", "stage_completion", "stage_first", "stage_decode"]).__next__)
        task = ProxyTask(
            recovered.Request_ID, recovered, build_body_for_instance(recovered, mode="chat"),
            "inst-a", "127.0.0.1", 9001, "/v1/chat/completions",
            kdn_addr=recovered.Task.KDN_server_addr,
            trace_context=context, trace_collector=collector, trace_provenance=provenance,
        )
        _manager, _output, calls = await _run_real_queue(monkeypatch, task, chunks=[b"data: token\\n\\n"])
        assert task.trace_context.request_id == str(req.Request_ID)
        assert task.trace_context.trace_id == trace_id
        assert task.request_trace.context.request_id == str(req.Request_ID)
        assert task.request_trace.context.trace_id == trace_id
        assert calls[0]["data"] == task.instance_body
        assert not (set(calls[0]["data"]) & set(RESERVED_TRACE_HEADERS))
    asyncio.run(scenario())



def test_skip_stage_failure_is_non_blocking_for_nonstream_and_empty(monkeypatch):
    async def scenario():
        for endpoint, chunks, expected_error in (
            ("completions", [json.dumps({"choices": [{"text": "ok"}]}).encode()], None),
            ("chat/completions", [], _EMPTY_STREAM),
        ):
            req = _scheduler_request(42, stream=endpoint == "chat/completions", endpoint=endpoint)
            task = _task_from_request(req)
            original_business_error = task.error
            def broken_skip_stage(*args, **kwargs):
                raise ValueError("unsafe model detail must not be logged")
            monkeypatch.setattr(task.trace_collector, "skip_stage", broken_skip_stage)
            _manager, output, calls = await _run_real_queue(monkeypatch, task, chunks=chunks)
            assert output == chunks
            assert calls
            assert task.error == original_business_error
            assert task.request_trace.error == expected_error
            _assert_no_running_and_valid_refs(task.request_trace)
    asyncio.run(scenario())


def test_real_methods_have_deterministic_elapsed_boundaries(monkeypatch):
    async def scenario():
        clock = ManualTraceClock(NOW)
        req = _scheduler_request(42)
        task = _task_from_request(req, clock=clock)
        output, calls = await _run_timed_real_queue(monkeypatch, task, clock)
        assert output == [b"data: token\n\n"]
        assert calls and calls[0]["use_chunked"] is True
        stages = {stage.name: stage for stage in task.request_trace.stages}
        assert stages[TraceStageName.PROXY_PREPARE_QUEUE].elapsed_ns == 5_000_000
        assert stages[TraceStageName.PROXY_READY_QUEUE].elapsed_ns == 7_000_000
        assert stages[TraceStageName.FIRST_TOKEN].elapsed_ns == 11_000_000
        assert stages[TraceStageName.DECODE].elapsed_ns == 13_000_000
        assert stages[TraceStageName.COMPLETION].elapsed_ns == 24_000_000
        assert stages[TraceStageName.PROXY_READY_QUEUE].elapsed_ns != 107_000_000
        _assert_no_running_and_valid_refs(task.request_trace)
    asyncio.run(scenario())
