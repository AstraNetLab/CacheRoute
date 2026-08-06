"""Instance-local observability session helpers.

This module adapts dependency-light canonical tracing primitives to the
transitional Instance FastAPI handlers without creating service-global trace
state or exposing traces on public responses.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from dataclasses import dataclass
from uuid import uuid4
from collections.abc import Mapping
from typing import AsyncGenerator, Awaitable, Callable, Any

from cacheroute.contracts.v1 import ContractErrorDetail, OutcomeCode
from cacheroute.observability import TraceCollector, create_trace_context, decode_trace_headers
from cacheroute.observability.clock import SystemTraceClock, TraceClock
from cacheroute.observability.propagation import TracePropagationError
from cacheroute.observability.startup import ObservabilityStartupConfig
from cacheroute.observability.v1 import RequestTrace, TraceContext, TraceProvenance, TraceStageName
from cacheroute.observability.v1.enums import TraceComponent
from cacheroute.runtime import RuntimeProfile

logger = logging.getLogger("instance")
_NON_STREAMING = "non_streaming_request"
_EMPTY_STREAM_REASON = "stream_ended_before_decode"
_DOWNSTREAM_FAILED = ContractErrorDetail(code=OutcomeCode.FAILED, message="instance downstream request failed")
_EMPTY_STREAM = ContractErrorDetail(code=OutcomeCode.FAILED, message="instance stream ended before first response")
_REQUEST_CANCELLED = ContractErrorDetail(code=OutcomeCode.CANCELLED, message="instance request cancelled")


def local_request_id() -> str:
    return f"req_{uuid4().hex}"


@dataclass(frozen=True)
class InstanceTraceResult:
    context: TraceContext
    accepted_propagated: bool
    fallback_reason: str | None


@dataclass
class InstanceTraceSession:
    context: TraceContext
    collector: TraceCollector | None
    provenance: TraceProvenance | None
    request_trace: RequestTrace | None = None
    completion_stage_id: str | None = None
    first_token_stage_id: str | None = None
    decode_stage_id: str | None = None

    def start_completion(self) -> None:
        if self.collector is None or self.provenance is None:
            return
        try:
            self.completion_stage_id = self.collector.start_stage(TraceStageName.COMPLETION, self.provenance)
        except (ValueError, TypeError):
            logger.warning("[Trace] instance stage start failed reason=collector_state_invalid")

    def start_first_response(self) -> None:
        if self.collector is None or self.provenance is None:
            return
        try:
            self.first_token_stage_id = self.collector.start_stage(
                TraceStageName.FIRST_TOKEN, self.provenance, parent_stage_id=self.completion_stage_id
            )
        except (ValueError, TypeError):
            logger.warning("[Trace] instance stage start failed reason=collector_state_invalid")

    def finish_first_response_and_start_decode(self) -> None:
        self.finish_stage("first_token_stage_id", OutcomeCode.SUCCESS)
        if self.collector is None or self.provenance is None:
            return
        try:
            self.decode_stage_id = self.collector.start_stage(
                TraceStageName.DECODE, self.provenance, parent_stage_id=self.completion_stage_id
            )
        except (ValueError, TypeError):
            logger.warning("[Trace] instance stage start failed reason=collector_state_invalid")

    def skip_non_streaming(self) -> None:
        if self.collector is None or self.provenance is None:
            return
        for name in (TraceStageName.FIRST_TOKEN, TraceStageName.DECODE):
            try:
                self.collector.skip_stage(name, self.provenance, reason=_NON_STREAMING, parent_stage_id=self.completion_stage_id)
            except (ValueError, TypeError):
                logger.warning("[Trace] instance stage skip failed reason=collector_state_invalid")

    def skip_empty_decode(self) -> None:
        if self.collector is None or self.provenance is None:
            return
        try:
            self.collector.skip_stage(TraceStageName.DECODE, self.provenance, reason=_EMPTY_STREAM_REASON, parent_stage_id=self.completion_stage_id)
        except (ValueError, TypeError):
            logger.warning("[Trace] instance stage skip failed reason=collector_state_invalid")

    def finish_stage(self, attr: str, outcome: OutcomeCode, error: ContractErrorDetail | None = None) -> None:
        if self.collector is None:
            return
        stage_id = getattr(self, attr)
        try:
            self.collector.finish_stage(stage_id, outcome=outcome, error=error)
            setattr(self, attr, None)
        except (ValueError, TypeError):
            logger.warning("[Trace] instance stage finalization failed reason=collector_state_invalid")

    def finalize(self, outcome: OutcomeCode, error: ContractErrorDetail | None = None) -> None:
        if self.collector is None or self.request_trace is not None:
            return
        try:
            self.request_trace = self.collector.export(outcome=outcome, error=error)
        except (ValueError, TypeError):
            logger.warning("[Trace] instance finalization failed reason=collector_state_invalid")


def resolve_instance_context(
    headers: Mapping[str, str], config: ObservabilityStartupConfig, *, clock: TraceClock | None = None
) -> InstanceTraceResult:
    active_clock = clock or SystemTraceClock()
    fallback_request_id: str | None = None
    try:
        propagated = decode_trace_headers(headers, clock=active_clock)
        fallback_request_id = propagated.request_id
        if propagated.runtime_profile is not config.runtime_profile:
            raise TracePropagationError("profile_mismatch")
        return InstanceTraceResult(propagated, True, None)
    except TracePropagationError as exc:
        reason = exc.reason
        try:
            # A second decode may relax freshness only.  It must still validate
            # the complete canonical header set before its request ID is kept.
            complete = decode_trace_headers(headers, clock=active_clock, max_age=timedelta.max)
            fallback_request_id = complete.request_id
        except TracePropagationError:
            fallback_request_id = None
    request_id = fallback_request_id or local_request_id()
    context = create_trace_context(
        request_id, RuntimeProfile.normalize(config.runtime_profile),
        sample_rate=config.trace_sample_rate, clock=active_clock,
    )
    logger.info("[Trace] instance context fallback reason=%s", reason)
    return InstanceTraceResult(context, False, reason)


def start_instance_trace_session(
    headers: Mapping[str, str], config: ObservabilityStartupConfig, *, clock: TraceClock | None = None,
    endpoint_label: str = "instance_downstream",
) -> InstanceTraceSession:
    active_clock = clock or SystemTraceClock()
    result = resolve_instance_context(headers, config, clock=active_clock)
    if not result.context.sampled:
        return InstanceTraceSession(result.context, None, None)
    provenance = TraceProvenance(
        source_component=TraceComponent.INSTANCE,
        runtime_profile=result.context.runtime_profile,
        captured_at=active_clock.utc_now(),
        source_endpoint=endpoint_label,
    )
    return InstanceTraceSession(
        result.context,
        TraceCollector(result.context, clock=active_clock),
        provenance,
    )


async def collect_non_streaming(session: InstanceTraceSession, call: Callable[[], Awaitable[Any]]) -> Any:
    session.start_completion()
    session.skip_non_streaming()
    try:
        result = await call()
    except asyncio.CancelledError:
        session.finish_stage("completion_stage_id", OutcomeCode.CANCELLED, _REQUEST_CANCELLED)
        session.finalize(OutcomeCode.CANCELLED, _REQUEST_CANCELLED)
        raise
    except Exception:
        session.finish_stage("completion_stage_id", OutcomeCode.FAILED, _DOWNSTREAM_FAILED)
        session.finalize(OutcomeCode.FAILED, _DOWNSTREAM_FAILED)
        raise
    session.finish_stage("completion_stage_id", OutcomeCode.SUCCESS)
    session.finalize(OutcomeCode.SUCCESS)
    return result


async def collect_streaming(session: InstanceTraceSession, stream: AsyncGenerator[bytes, None]) -> AsyncGenerator[bytes, None]:
    session.start_completion()
    session.start_first_response()
    seen_first = False
    try:
        async for chunk in stream:
            if chunk and not seen_first:
                seen_first = True
                session.finish_first_response_and_start_decode()
            yield chunk
    except asyncio.CancelledError:
        session.finish_stage("first_token_stage_id", OutcomeCode.CANCELLED, _REQUEST_CANCELLED)
        session.finish_stage("decode_stage_id", OutcomeCode.CANCELLED, _REQUEST_CANCELLED)
        session.finish_stage("completion_stage_id", OutcomeCode.CANCELLED, _REQUEST_CANCELLED)
        session.finalize(OutcomeCode.CANCELLED, _REQUEST_CANCELLED)
        raise
    except GeneratorExit:
        # ``aclose()`` injects GeneratorExit at the current yield.  Finalize
        # the request-local trace, then preserve normal generator closure.
        session.finish_stage("first_token_stage_id", OutcomeCode.CANCELLED, _REQUEST_CANCELLED)
        session.finish_stage("decode_stage_id", OutcomeCode.CANCELLED, _REQUEST_CANCELLED)
        session.finish_stage("completion_stage_id", OutcomeCode.CANCELLED, _REQUEST_CANCELLED)
        session.finalize(OutcomeCode.CANCELLED, _REQUEST_CANCELLED)
        raise
    except Exception:
        session.finish_stage("first_token_stage_id", OutcomeCode.FAILED, _DOWNSTREAM_FAILED)
        session.finish_stage("decode_stage_id", OutcomeCode.FAILED, _DOWNSTREAM_FAILED)
        session.finish_stage("completion_stage_id", OutcomeCode.FAILED, _DOWNSTREAM_FAILED)
        session.finalize(OutcomeCode.FAILED, _DOWNSTREAM_FAILED)
        raise
    if seen_first:
        session.finish_stage("decode_stage_id", OutcomeCode.SUCCESS)
        session.finish_stage("completion_stage_id", OutcomeCode.SUCCESS)
        session.finalize(OutcomeCode.SUCCESS)
    else:
        session.finish_stage("first_token_stage_id", OutcomeCode.FAILED, _EMPTY_STREAM)
        session.skip_empty_decode()
        session.finish_stage("completion_stage_id", OutcomeCode.FAILED, _EMPTY_STREAM)
        session.finalize(OutcomeCode.FAILED, _EMPTY_STREAM)


__all__ = ["InstanceTraceSession", "resolve_instance_context", "start_instance_trace_session", "collect_non_streaming", "collect_streaming", "local_request_id"]
