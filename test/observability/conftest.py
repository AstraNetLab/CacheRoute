from datetime import datetime, timezone

import pytest

from cacheroute_observability import TraceComponent, TraceContext, TraceProvenance


@pytest.fixture
def now():
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def context(now):
    return TraceContext(trace_id="trace_" + "1" * 32, request_id="req-1",
                        correlation_id="corr-1", sampled=True, created_at=now)


@pytest.fixture
def provenance(now):
    return TraceProvenance(source_component=TraceComponent.TEST,
                           runtime_profile="test.mock", captured_at=now)
