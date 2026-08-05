from datetime import datetime, timedelta, timezone

import pytest

from cacheroute.observability import ManualTraceClock
from cacheroute.observability.propagation import (
    RESERVED_TRACE_HEADERS, TracePropagationError, create_trace_context,
    decode_trace_headers, encode_trace_headers, is_trace_sampled, parse_sample_rate,
    _FUTURE_SKEW_TOLERANCE, _MAX_AGE,
)
from cacheroute.observability.startup import resolve_observability_startup
from cacheroute.runtime import RuntimeProfile

NOW = datetime(2026, 8, 4, 12, tzinfo=timezone.utc)
TRACE_ID = "trace_0123456789abcdef0123456789abcdef"


def context(sample_rate=1.0):
    return create_trace_context("42", RuntimeProfile.LEGACY, sample_rate=sample_rate,
                                clock=ManualTraceClock(NOW), trace_id=TRACE_ID)


def test_exact_vocabulary_and_deterministic_round_trip():
    headers = encode_trace_headers(context())
    assert tuple(headers) == RESERVED_TRACE_HEADERS
    assert decode_trace_headers(headers, clock=ManualTraceClock(NOW)) == context()
    assert encode_trace_headers(decode_trace_headers(headers, clock=ManualTraceClock(NOW))) == headers


def test_decode_is_case_insensitive():
    headers = {key.upper(): value for key, value in encode_trace_headers(context()).items()}
    assert decode_trace_headers(headers, clock=ManualTraceClock(NOW)).trace_id == TRACE_ID


@pytest.mark.parametrize("change", [
    lambda h: h.pop("x-cacheroute-trace-id"),
    lambda h: h.__setitem__("x-cacheroute-trace-id", "TRACE_bad"),
    lambda h: h.__setitem__("x-cacheroute-trace-sampled", "true"),
    lambda h: h.__setitem__("x-cacheroute-runtime-profile", "auto"),
    lambda h: h.__setitem__("x-cacheroute-trace-created-at", "2026-08-04T12:00:00+01:00"),
    lambda h: h.__setitem__("x-cacheroute-trace-extra", "x"),
])
def test_malformed_context_is_rejected(change):
    headers = encode_trace_headers(context())
    change(headers)
    with pytest.raises(TracePropagationError):
        decode_trace_headers(headers, clock=ManualTraceClock(NOW))


def test_timestamp_freshness_boundaries():
    headers = encode_trace_headers(context())
    decode_trace_headers(headers, clock=ManualTraceClock(NOW - _FUTURE_SKEW_TOLERANCE))
    with pytest.raises(TracePropagationError):
        decode_trace_headers(headers, clock=ManualTraceClock(NOW - _FUTURE_SKEW_TOLERANCE - timedelta(microseconds=1)))
    decode_trace_headers(headers, clock=ManualTraceClock(NOW + _MAX_AGE))
    with pytest.raises(TracePropagationError):
        decode_trace_headers(headers, clock=ManualTraceClock(NOW + _MAX_AGE + timedelta(microseconds=1)))


def test_sampling_boundaries_and_invalid_configuration():
    assert not is_trace_sampled(TRACE_ID, 0.0)
    assert is_trace_sampled(TRACE_ID, 1.0)
    assert is_trace_sampled(TRACE_ID, 0.5) == is_trace_sampled(TRACE_ID, 0.5)
    for value in (None, "bad", "nan", "inf", -1, 2):
        assert parse_sample_rate(value) == 0.0


@pytest.mark.parametrize(("value", "expected"), [
    (None, RuntimeProfile.LEGACY),
    ("legacy", RuntimeProfile.LEGACY),
    ("test/mock", RuntimeProfile.TEST_MOCK),
    ("v1", RuntimeProfile.V1),
    ("auto", RuntimeProfile.LEGACY),
])
def test_current_service_startup_profile_resolution(value, expected):
    config = resolve_observability_startup(value, "1.0", v1_available=False)
    assert config.runtime_profile is expected
    assert config.runtime_profile is not RuntimeProfile.AUTO
    assert config.trace_sample_rate == 1.0
