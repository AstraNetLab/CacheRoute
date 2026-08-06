from datetime import datetime, timedelta, timezone
import asyncio
import json
import re

import pytest

from cacheroute.contracts.v1 import OutcomeCode
from cacheroute.observability import ManualTraceClock, create_trace_context, encode_trace_headers
from cacheroute.observability.propagation import RESERVED_TRACE_HEADERS, TRACE_ID_HEADER
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

    old = ManualTraceClock(NOW + timedelta(minutes=6))
    stale = resolve_instance_context(headers(), cfg(), clock=old)
    assert stale.context.request_id == "scheduler-1"
    assert stale.accepted_propagated is False

    mismatch = resolve_instance_context(headers(), cfg(profile="test_mock"), clock=clock)
    assert mismatch.fallback_reason == "profile_mismatch"
    assert mismatch.context.request_id == "scheduler-1"


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
