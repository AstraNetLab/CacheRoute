from datetime import datetime, timedelta, timezone
import math

import pytest
from pydantic import ValidationError

import cacheroute.observability as helpers
import cacheroute.observability.v1 as api
from cacheroute.cache import CacheOperationTask, CacheOperationType
from cacheroute.contracts.v1.common import ContractModel
from cacheroute.contracts.v1.errors import ContractErrorDetail, OutcomeCode
from cacheroute.runtime import RuntimeProfile
from cacheroute.topology import LMCacheEndpoint, LMCacheGatewayProfile
from cacheroute.observability.v1.models import (
    CacheOperationTask as ReusedTask, CacheOperationType as ReusedType,
    ContractErrorDetail as ReusedError, LMCacheEndpoint as ReusedEndpoint,
    OutcomeCode as ReusedOutcome, RuntimeProfile as ReusedRuntime,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def provenance(**updates):
    values = dict(source_component="test", runtime_profile="test/mock", captured_at=NOW)
    values.update(updates)
    return api.TraceProvenance(**values)


def context(**updates):
    values = dict(trace_id="trace_1", request_id="request_1", runtime_profile="test/mock", created_at=NOW)
    values.update(updates)
    return api.TraceContext(**values)


def test_public_surfaces_and_canonical_identity():
    assert api.__all__ == ["TraceContext", "TraceComponent", "TraceStageName", "TraceStageState", "TraceValueKind", "TraceProvenance", "TraceMeasurement", "TraceStage", "RequestTrace", "CacheOperationTrace", "OperationWaiterLink", "OperationWaiterState"]
    assert helpers.__all__ == ["TraceClock", "SystemTraceClock", "ManualTraceClock", "TraceCollector", "project_legacy_proxy_trace"]
    assert ReusedRuntime is RuntimeProfile
    assert ReusedOutcome is OutcomeCode
    assert ReusedError is ContractErrorDetail
    assert ReusedTask is CacheOperationTask
    assert ReusedType is CacheOperationType
    assert ReusedEndpoint is LMCacheEndpoint
    assert issubclass(api.TraceContext, ContractModel)
    assert api.TraceContext.__module__ == "cacheroute.observability.v1.models"


def test_stable_enum_values():
    assert [x.value for x in api.TraceStageState] == ["pending", "running", "completed", "skipped"]
    assert [x.value for x in api.TraceValueKind] == ["predicted", "desired", "observed", "measured", "actual", "inferred", "legacy_projected"]
    assert [x.value for x in api.OperationWaiterState] == ["waiting", "completed", "cancelled", "detached", "expired"]
    assert {"legacy_scan", "gateway_async_operation", "proxy_ready_queue", "first_token"} <= {x.value for x in api.TraceStageName}


def test_context_frozen_extra_utc_and_validated_copy():
    value = context(expires_at=NOW + timedelta(seconds=1))
    with pytest.raises(ValidationError): value.request_id = "changed"
    with pytest.raises(ValidationError): api.TraceContext(**(value.model_dump() | {"unknown": 1}))
    with pytest.raises(ValidationError): value.model_copy(update={"runtime_profile": "auto"})
    assert api.TraceContext.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize("updates", [
    {}, {"duration_ns": 1, "count": 1}, {"ratio": math.inf}, {"ratio": -0.1},
    {"scalar": math.nan}, {"scalar": "password secret"}, {"scalar": [1]},
])
def test_measurement_exactly_one_finite_safe_value(updates):
    with pytest.raises((ValidationError, TypeError)):
        api.TraceMeasurement(code="metric", value_kind="measured", **updates)


def test_provenance_endpoint_and_legacy_rules():
    with pytest.raises(ValidationError): provenance(endpoint_id="endpoint_" + "a" * 32)
    with pytest.raises(ValidationError): provenance(endpoint_id="endpoint_" + "a" * 32, endpoint_generation=0)
    legacy = provenance(runtime_profile="legacy", source_component="legacy_adapter", legacy_projected=True,
                        endpoint_id="endpoint_" + "a" * 32, endpoint_generation=0,
                        gateway_profile=LMCacheGatewayProfile.LEGACY_GATEWAY)
    assert legacy.endpoint_generation == 0


def test_recursive_immutability_and_ordered_correlation():
    measurement = api.TraceMeasurement(code="tokens", value_kind="actual", tokens=2)
    stage = api.TraceStage(stage_id="s1", sequence=0, name="completion", state="skipped",
        provenance=provenance(), skip_reason="not_needed", measurements=(measurement,))
    trace = api.RequestTrace(context=context(), stages=(stage,), cache_operation_ids=("op1", "op2"))
    assert isinstance(trace.stages, tuple) and isinstance(trace.stages[0].measurements, tuple)
    with pytest.raises(ValidationError): trace.stages[0].measurements = ()
    with pytest.raises(ValidationError): trace.model_copy(update={"stages": (stage, stage.model_copy(update={"stage_id": "s2", "sequence": 0}))})
    assert api.RequestTrace.model_validate_json(trace.model_dump_json()) == trace


def test_operation_links_multiple_waiters():
    links = tuple(api.OperationWaiterLink(request_trace_id=f"t{i}", request_id=f"r{i}", linked_at=NOW) for i in range(2))
    operation = api.CacheOperationTrace(operation_id="cacheop_" + "a" * 32, operation_type="prefetch", waiters=links)
    assert len(operation.waiters) == 2
