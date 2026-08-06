from datetime import datetime, timedelta, timezone
import asyncio
import json
import re
from types import SimpleNamespace

import pytest

from cacheroute.contracts.v1 import OutcomeCode
from cacheroute.observability import ManualTraceClock, create_trace_context, encode_trace_headers
from cacheroute.observability.propagation import (
    RESERVED_TRACE_HEADERS,
    REQUEST_ID_HEADER,
    TRACE_ID_HEADER,
)
from cacheroute.observability.startup import resolve_observability_startup
from cacheroute.observability.v1 import TraceStageName
from cacheroute.observability.v1.enums import TraceComponent
from cacheroute.runtime import RuntimeProfile
from instance.observability import collect_non_streaming, collect_streaming, resolve_instance_context, start_instance_trace_session

NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)
TRACE_ID = "trace_" + "1" * 32


def cfg(rate="1.0", profile="legacy"):
    return resolve_observability_startup(profile, rate, v1_available=False)


def headers():
    return encode_trace_headers(create_trace_context("scheduler-1", RuntimeProfile.LEGACY, sample_rate=1.0, clock=ManualTraceClock(NOW), trace_id=TRACE_ID))


def test_instance_context_accepts_valid_and_falls_back_for_missing_malformed_stale_and_mismatch(monkeypatch):
    clock = ManualTraceClock(NOW)
    accepted = resolve_instance_context(headers(), cfg(), clock=clock)
    assert accepted.accepted_propagated is True
    assert accepted.context.trace_id == TRACE_ID
    assert accepted.context.request_id == "scheduler-1"

    missing = resolve_instance_context({}, cfg(), clock=clock)
    assert missing.accepted_propagated is False
    assert re.fullmatch(r"req_[0-9a-f]{32}", missing.context.request_id)

    malformed = dict(headers(), **{TRACE_ID_HEADER: "bad"})
    bad = resolve_instance_context(malformed, cfg(), clock=clock)
    assert bad.fallback_reason == "trace_id_invalid"
    assert re.fullmatch(r"req_[0-9a-f]{32}", bad.context.request_id)

    old = ManualTraceClock(NOW + timedelta(minutes=6))
    stale = resolve_instance_context(headers(), cfg(), clock=old)
    assert stale.context.request_id == "scheduler-1"
    assert stale.accepted_propagated is False

    mismatch = resolve_instance_context(headers(), cfg(profile="test_mock"), clock=clock)
    assert mismatch.fallback_reason == "profile_mismatch"
    assert mismatch.context.request_id == "scheduler-1"


class _ConflictingHeaders(dict):
    def items(self):
        values = list(super().items())
        values.append((TRACE_ID_HEADER.upper(), "trace_" + "2" * 32))
        return values


@pytest.mark.parametrize(
    "invalid_headers,reason",
    [
        ({REQUEST_ID_HEADER: "safe-looking"}, "headers_incomplete"),
        ({REQUEST_ID_HEADER: "unsafe request id!"}, "headers_incomplete"),
        (dict(headers(), **{TRACE_ID_HEADER: "bad", REQUEST_ID_HEADER: "safe-looking"}), "trace_id_invalid"),
        (dict(headers(), **{"x-cacheroute-trace-unknown": "value"}), "header_unknown"),
        (_ConflictingHeaders(headers()), "header_conflict"),
    ],
)
def test_invalid_header_sets_never_retain_raw_request_id_or_fail_output(invalid_headers, reason):
    async def scenario():
        session = start_instance_trace_session(invalid_headers, cfg(), clock=ManualTraceClock(NOW))
        assert re.fullmatch(r"req_[0-9a-f]{32}", session.context.request_id)
        output = {"choices": []}
        assert await collect_non_streaming(session, lambda: asyncio.sleep(0, result=output)) is output
        assert session.request_trace.outcome is OutcomeCode.SUCCESS

    result = resolve_instance_context(invalid_headers, cfg(), clock=ManualTraceClock(NOW))
    assert result.fallback_reason == reason
    asyncio.run(scenario())


def test_startup_resolution_defaults_and_invalid_sample_rate():
    default = resolve_observability_startup(None, None, v1_available=False)
    assert default.runtime_profile is RuntimeProfile.LEGACY
    invalid = resolve_observability_startup("auto", "bad", v1_available=False)
    assert invalid.runtime_profile is RuntimeProfile.LEGACY
    assert invalid.trace_sample_rate == 0.0
    assert invalid.sample_rate_warning_reason == "trace_sample_rate_malformed"


def test_unsampled_session_collects_no_trace():
    session = start_instance_trace_session(headers(), cfg(rate="0.0"), clock=ManualTraceClock(NOW))
    assert session.collector is None


@pytest.mark.parametrize("stream_chunks", [[b"data: one\n\n", b"data: [DONE]\n\n"], [b"", b"data: one\n\n"]])
def test_streaming_timing_order_parent_provenance_and_shape(stream_chunks):
    async def scenario():
        clock = ManualTraceClock(NOW)
        session = start_instance_trace_session(headers(), cfg(), clock=clock)
        async def stream():
            for chunk in stream_chunks:
                clock.advance(nanoseconds=10)
                yield chunk
            clock.advance(nanoseconds=5)
        out = []
        async for chunk in collect_streaming(session, stream()):
            out.append(chunk)
        assert out == stream_chunks
        trace = session.request_trace
        assert trace.outcome is OutcomeCode.SUCCESS
        stages = trace.stages
        assert [s.name for s in stages] == [TraceStageName.COMPLETION, TraceStageName.FIRST_TOKEN, TraceStageName.DECODE]
        assert stages[1].parent_stage_id == stages[0].stage_id
        assert stages[2].parent_stage_id == stages[0].stage_id
        assert all(s.provenance.source_component is TraceComponent.INSTANCE for s in stages)
        assert TraceStageName.VLLM_PREFILL not in {s.name for s in stages}
        expected_first = 10 if stream_chunks[0] else 20
        assert stages[1].elapsed_ns == expected_first
        assert stages[2].elapsed_ns == 25 - expected_first
        assert stages[0].elapsed_ns == 25
    asyncio.run(scenario())


def test_non_streaming_skips_and_completion_payload_unchanged():
    async def scenario():
        clock = ManualTraceClock(NOW)
        session = start_instance_trace_session(headers(), cfg(), clock=clock)
        payload = {"choices": [{"message": {"content": "secret generated"}}]}
        result = await collect_non_streaming(session, lambda: asyncio.sleep(0, result=payload))
        assert result is payload
        stages = session.request_trace.stages
        assert [s.name for s in stages] == [TraceStageName.COMPLETION, TraceStageName.FIRST_TOKEN, TraceStageName.DECODE]
        assert {s.skip_reason for s in stages if s.name is not TraceStageName.COMPLETION} == {"non_streaming_request"}
        dumped = session.request_trace.model_dump_json()
        assert "secret generated" not in dumped
    asyncio.run(scenario())


def test_failure_empty_and_cancelled_paths_have_bounded_errors():
    async def before_failure():
        clock = ManualTraceClock(NOW)
        session = start_instance_trace_session(headers(), cfg(), clock=clock)
        async def stream():
            raise RuntimeError("raw boom prompt Authorization")
            yield b""
        with pytest.raises(RuntimeError):
            async for _ in collect_streaming(session, stream()):
                pass
        assert session.request_trace.error.message == "instance downstream request failed"
        assert "raw boom" not in session.request_trace.model_dump_json()

    async def empty():
        session = start_instance_trace_session(headers(), cfg(), clock=ManualTraceClock(NOW))
        async def stream():
            if False:
                yield b""
        async for _ in collect_streaming(session, stream()):
            pass
        assert session.request_trace.error.message == "instance stream ended before first response"

    asyncio.run(before_failure())
    asyncio.run(empty())


@pytest.mark.parametrize("after_first", [False, True])
def test_streaming_asyncio_cancellation_finalizes_every_stage(after_first):
    async def scenario():
        session = start_instance_trace_session(headers(), cfg(), clock=ManualTraceClock(NOW))
        gate = asyncio.Event()

        async def stream():
            if after_first:
                yield b"data: first\n\n"
            await gate.wait()
            yield b"never"

        collected = collect_streaming(session, stream())
        if after_first:
            assert await anext(collected) == b"data: first\n\n"
        pending = asyncio.create_task(anext(collected))
        await asyncio.sleep(0)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert session.request_trace.outcome is OutcomeCode.CANCELLED
        assert session.request_trace.error.message == "instance request cancelled"
        assert all(stage.state.value != "running" for stage in session.request_trace.stages)

    asyncio.run(scenario())


@pytest.mark.parametrize("after_first", [False, True])
def test_streaming_aclose_finalizes_as_cancellation(after_first):
    async def scenario():
        session = start_instance_trace_session(headers(), cfg(), clock=ManualTraceClock(NOW))

        async def stream():
            yield b"data: first\n\n" if after_first else b""
            yield b"never"

        collected = collect_streaming(session, stream())
        first = await anext(collected)
        assert first == (b"data: first\n\n" if after_first else b"")
        await collected.aclose()
        assert session.request_trace.outcome is OutcomeCode.CANCELLED
        assert session.request_trace.error.message == "instance request cancelled"
        assert all(stage.state.value != "running" for stage in session.request_trace.stages)
        stage = next(
            item for item in session.request_trace.stages
            if item.name is (TraceStageName.DECODE if after_first else TraceStageName.FIRST_TOKEN)
        )
        assert stage.outcome is OutcomeCode.CANCELLED

    asyncio.run(scenario())


def test_streaming_failure_after_first_response_is_bounded():
    async def scenario():
        session = start_instance_trace_session(headers(), cfg(), clock=ManualTraceClock(NOW))

        async def stream():
            yield b"data: first\n\n"
            raise RuntimeError("private downstream exception")

        collected = collect_streaming(session, stream())
        assert await anext(collected) == b"data: first\n\n"
        with pytest.raises(RuntimeError):
            await anext(collected)
        assert session.request_trace.outcome is OutcomeCode.FAILED
        assert all(stage.state.value != "running" for stage in session.request_trace.stages)
        assert "private downstream exception" not in session.request_trace.model_dump_json()

    asyncio.run(scenario())


def test_startup_configuration_is_reused_without_reinvoking_resolver(monkeypatch):
    from types import SimpleNamespace
    from instance import instance_api

    configured = cfg()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(_observability_config=configured)))
    monkeypatch.setattr(
        instance_api,
        "resolve_observability_startup",
        lambda *args, **kwargs: pytest.fail("request path reran startup resolver"),
    )
    assert instance_api._instance_observability_config(request) is configured
    assert instance_api._instance_observability_config(request) is configured


def test_real_vllm_forwarding_preserves_payload_and_sends_no_trace_headers(monkeypatch):
    from instance import instance_api

    async def scenario():
        stream_payload = {"model": "unit", "messages": [{"role": "user", "content": "secret"}], "stream": True}
        chat_payload = {"model": "unit", "messages": [], "stream": False}
        text_payload = {"model": "unit", "prompt": "secret", "stream": False}
        calls = []

        async def forwarded(url, data, use_chunked=False, **kwargs):
            calls.append((url, data, use_chunked, kwargs))
            if use_chunked:
                yield b"data: unchanged\n\n"
            else:
                yield json.dumps({"choices": []}).encode()

        monkeypatch.setattr(instance_api, "use_mock", False)
        monkeypatch.setattr(instance_api, "vllm_base_url", "http://vllm")
        monkeypatch.setattr(instance_api, "forward_request", forwarded)
        stream_bytes = [chunk async for chunk in instance_api._vllm_stream_chat(stream_payload)]
        chat_json = await instance_api._vllm_chat_completion(chat_payload)
        text_json = await instance_api._vllm_text_completion(text_payload)
        assert stream_bytes == [b"data: unchanged\n\n"]
        assert chat_json == text_json == {"choices": []}
        assert calls == [
            ("http://vllm/v1/chat/completions", stream_payload, True, {}),
            ("http://vllm/v1/chat/completions", chat_payload, False, {}),
            ("http://vllm/v1/completions", text_payload, False, {}),
        ]
        public_values = stream_bytes + [json.dumps(chat_json).encode(), json.dumps(text_json).encode()]
        for value in public_values:
            assert TRACE_ID.encode() not in value
            assert b"RequestTrace" not in value
            assert b"trace_id" not in value
            assert all(name.encode() not in value for name in RESERVED_TRACE_HEADERS)
        for _url, _payload, _chunked, kwargs in calls:
            assert kwargs == {}
            assert all(name not in kwargs for name in RESERVED_TRACE_HEADERS)
            assert "traceparent" not in kwargs and "tracestate" not in kwargs

    asyncio.run(scenario())


@pytest.mark.parametrize("after_first", [False, True])
def test_streaming_response_body_close_finalizes_and_closes_downstream(monkeypatch, after_first):
    from instance import instance_api

    async def scenario():
        clock = ManualTraceClock(NOW)
        app = SimpleNamespace(state=SimpleNamespace(
            _observability_config=cfg(),
            _trace_clock=clock,
        ))
        request = SimpleNamespace(
            app=app,
            headers=headers(),
            state=SimpleNamespace(),
            json=lambda: asyncio.sleep(0, result={"stream": True, "messages": []}),
        )
        downstream_closed = False
        emitted = b"data: first\n\n" if after_first else b""

        async def downstream(_payload):
            nonlocal downstream_closed
            try:
                yield emitted
                yield b"data: never\n\n"
            finally:
                downstream_closed = True

        monkeypatch.setattr(instance_api, "_vllm_stream_chat", downstream)
        response = await instance_api.instance_chat_completions(request)
        assert await anext(response.body_iterator) == emitted
        await response.body_iterator.aclose()

        trace = request.state._cacheroute_trace_session.request_trace
        assert downstream_closed is True
        assert trace.outcome is OutcomeCode.CANCELLED
        assert trace.error.message == "instance request cancelled"
        assert all(stage.state.value != "running" for stage in trace.stages)
        terminal_name = TraceStageName.DECODE if after_first else TraceStageName.FIRST_TOKEN
        assert next(stage for stage in trace.stages if stage.name is terminal_name).outcome is OutcomeCode.CANCELLED
        assert next(stage for stage in trace.stages if stage.name is TraceStageName.COMPLETION).outcome is OutcomeCode.CANCELLED
        assert emitted == (b"data: first\n\n" if after_first else b"")
        assert TRACE_ID not in str(response.headers)
        assert all(name not in response.headers for name in RESERVED_TRACE_HEADERS)

    asyncio.run(scenario())


@pytest.mark.parametrize("terminal", ["success", "failure", "cancel", "close"])
def test_collect_streaming_always_closes_wrapped_iterator(monkeypatch, terminal):
    async def scenario():
        session = start_instance_trace_session(headers(), cfg(), clock=ManualTraceClock(NOW))
        closed = False

        async def downstream():
            nonlocal closed
            try:
                if terminal == "failure":
                    raise RuntimeError("original failure")
                yield b"data: first\n\n"
                if terminal == "cancel":
                    await asyncio.Event().wait()
            finally:
                closed = True

        collected = collect_streaming(session, downstream())
        if terminal == "failure":
            with pytest.raises(RuntimeError, match="original failure"):
                await anext(collected)
        elif terminal == "close":
            await anext(collected)
            await collected.aclose()
        elif terminal == "cancel":
            await anext(collected)
            pending = asyncio.create_task(anext(collected))
            await asyncio.sleep(0)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        else:
            assert [chunk async for chunk in collected] == [b"data: first\n\n"]
        assert closed is True

    asyncio.run(scenario())


def test_mock_streaming_chat_and_nonstreaming_chat_and_text_shapes_are_unchanged(monkeypatch):
    from instance import instance_api

    async def scenario():
        stream_payload = {"stream": True, "messages": []}
        chat_payload = {"stream": False, "messages": []}
        text_payload = {"prompt": "kept"}
        stream_bytes = [b"data: mock\n\n", b"data: [DONE]\n\n"]
        chat_json = {"choices": [{"message": {"content": "mock"}}]}
        text_json = {"choices": [{"text": "mock"}]}

        async def mock_stream(payload):
            assert payload is stream_payload
            for chunk in stream_bytes:
                yield chunk

        async def mock_chat(payload):
            assert payload is chat_payload
            return chat_json

        async def mock_text(payload):
            assert payload is text_payload
            return text_json

        monkeypatch.setattr(instance_api, "use_mock", True)
        monkeypatch.setattr(instance_api, "mock_chat_stream", mock_stream)
        monkeypatch.setattr(instance_api, "mock_chat_completion", mock_chat)
        monkeypatch.setattr(instance_api, "mock_text_completion", mock_text)
        assert [chunk async for chunk in instance_api._vllm_stream_chat(stream_payload)] == stream_bytes
        assert await instance_api._vllm_chat_completion(chat_payload) is chat_json
        assert await instance_api._vllm_text_completion(text_payload) is text_json

    asyncio.run(scenario())
