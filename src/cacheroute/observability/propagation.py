"""Canonical internal CacheRoute trace-context propagation.

This module deliberately contains no service configuration or I/O.  Services
resolve startup settings and pass the resulting values into these helpers.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
import hashlib
import math
import re
from uuid import uuid4

from cacheroute.runtime import RuntimeProfile
from .clock import SystemTraceClock, TraceClock
from .v1 import TraceContext
from .v1.models import OBSERVABILITY_SCHEMA_VERSION

REQUEST_ID_HEADER = "scheduler-request-id"
TRACE_VERSION_HEADER = "x-cacheroute-trace-version"
TRACE_ID_HEADER = "x-cacheroute-trace-id"
RUNTIME_PROFILE_HEADER = "x-cacheroute-runtime-profile"
TRACE_SAMPLED_HEADER = "x-cacheroute-trace-sampled"
TRACE_CREATED_AT_HEADER = "x-cacheroute-trace-created-at"

RESERVED_TRACE_HEADERS = (
    REQUEST_ID_HEADER,
    TRACE_VERSION_HEADER,
    TRACE_ID_HEADER,
    RUNTIME_PROFILE_HEADER,
    TRACE_SAMPLED_HEADER,
    TRACE_CREATED_AT_HEADER,
)
_TRACE_ID = re.compile(r"^trace_[0-9a-f]{32}$")
_MAX_AGE = timedelta(minutes=5)
# Scheduler, Proxy, and Instance clocks may differ during startup or host sync.
# Accept only this bounded future skew and retain the maximum-age freshness rule.
_FUTURE_SKEW_TOLERANCE = timedelta(seconds=30)


class TracePropagationError(ValueError):
    """A bounded, value-free propagation validation failure."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def parse_sample_rate(value: str | float | None) -> float:
    """Return a safe rate, failing closed for malformed startup input."""
    try:
        rate = float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        return 0.0
    return rate if math.isfinite(rate) and 0.0 <= rate <= 1.0 else 0.0


def is_trace_sampled(trace_id: str, sample_rate: float) -> bool:
    if _TRACE_ID.fullmatch(trace_id) is None:
        raise ValueError("trace_id_invalid")
    rate = parse_sample_rate(sample_rate)
    if rate <= 0.0:
        return False
    if rate >= 1.0:
        return True
    bucket = int.from_bytes(hashlib.sha256(trace_id.encode("ascii")).digest()[:8], "big")
    return bucket < int(rate * (1 << 64))


def new_trace_id() -> str:
    return f"trace_{uuid4().hex}"


def create_trace_context(request_id: str | int, runtime_profile: RuntimeProfile, *,
                         sample_rate: float = 0.0, clock: TraceClock | None = None,
                         trace_id: str | None = None) -> TraceContext:
    profile = RuntimeProfile.normalize(runtime_profile)
    if profile is RuntimeProfile.AUTO:
        raise ValueError("runtime_profile_auto")
    identifier = trace_id or new_trace_id()
    if _TRACE_ID.fullmatch(identifier) is None:
        raise ValueError("trace_id_invalid")
    return TraceContext(
        trace_id=identifier,
        request_id=str(request_id),
        runtime_profile=profile,
        sampled=is_trace_sampled(identifier, sample_rate),
        created_at=(clock or SystemTraceClock()).utc_now(),
    )


def encode_trace_headers(context: TraceContext) -> dict[str, str]:
    if _TRACE_ID.fullmatch(context.trace_id) is None:
        raise TracePropagationError("trace_id_invalid")
    if context.runtime_profile is RuntimeProfile.AUTO:
        raise TracePropagationError("profile_invalid")
    if context.created_at.utcoffset() != timedelta(0):
        raise TracePropagationError("created_at_invalid")
    return {
        REQUEST_ID_HEADER: context.request_id,
        TRACE_VERSION_HEADER: OBSERVABILITY_SCHEMA_VERSION,
        TRACE_ID_HEADER: context.trace_id,
        RUNTIME_PROFILE_HEADER: context.runtime_profile.value,
        TRACE_SAMPLED_HEADER: "1" if context.sampled else "0",
        TRACE_CREATED_AT_HEADER: context.created_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
    }


def decode_trace_headers(headers: Mapping[str, str], *, clock: TraceClock | None = None,
                         max_age: timedelta = _MAX_AGE,
                         future_skew_tolerance: timedelta = _FUTURE_SKEW_TOLERANCE) -> TraceContext:
    lowered: dict[str, str] = {}
    for key, value in headers.items():
        name = str(key).lower()
        if name.startswith("x-cacheroute-trace-") and name not in RESERVED_TRACE_HEADERS:
            raise TracePropagationError("header_unknown")
        if name in RESERVED_TRACE_HEADERS:
            if name in lowered and lowered[name] != str(value):
                raise TracePropagationError("header_conflict")
            lowered[name] = str(value)
    if set(lowered) != set(RESERVED_TRACE_HEADERS):
        raise TracePropagationError("headers_incomplete")
    if lowered[TRACE_VERSION_HEADER] != OBSERVABILITY_SCHEMA_VERSION:
        raise TracePropagationError("version_invalid")
    trace_id = lowered[TRACE_ID_HEADER]
    if _TRACE_ID.fullmatch(trace_id) is None:
        raise TracePropagationError("trace_id_invalid")
    try:
        profile = RuntimeProfile.normalize(lowered[RUNTIME_PROFILE_HEADER])
    except ValueError as exc:
        raise TracePropagationError("profile_invalid") from exc
    if profile is RuntimeProfile.AUTO:
        raise TracePropagationError("profile_invalid")
    sampled_value = lowered[TRACE_SAMPLED_HEADER]
    if sampled_value not in {"0", "1"}:
        raise TracePropagationError("sampled_invalid")
    stamp_value = lowered[TRACE_CREATED_AT_HEADER]
    try:
        created_at = datetime.fromisoformat(stamp_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TracePropagationError("created_at_invalid") from exc
    if created_at.utcoffset() != timedelta(0):
        raise TracePropagationError("created_at_invalid")
    now = (clock or SystemTraceClock()).utc_now()
    if created_at - now > future_skew_tolerance or now - created_at > max_age:
        raise TracePropagationError("created_at_stale")
    try:
        return TraceContext(
            schema_version=lowered[TRACE_VERSION_HEADER], trace_id=trace_id,
            request_id=lowered[REQUEST_ID_HEADER], runtime_profile=profile,
            sampled=sampled_value == "1", created_at=created_at,
        )
    except ValueError as exc:
        raise TracePropagationError("context_invalid") from exc


__all__ = [
    "REQUEST_ID_HEADER", "TRACE_VERSION_HEADER", "TRACE_ID_HEADER",
    "RUNTIME_PROFILE_HEADER", "TRACE_SAMPLED_HEADER", "TRACE_CREATED_AT_HEADER",
    "RESERVED_TRACE_HEADERS", "TracePropagationError", "parse_sample_rate",
    "_MAX_AGE", "_FUTURE_SKEW_TOLERANCE",
    "is_trace_sampled", "new_trace_id", "create_trace_context",
    "encode_trace_headers", "decode_trace_headers",
]
