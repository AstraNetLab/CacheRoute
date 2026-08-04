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
    trace = api.RequestTrace(context=context(), stages=(stage,), cache_operation_ids=("cacheop_" + "1" * 32, "cacheop_" + "2" * 32))
    assert isinstance(trace.stages, tuple) and isinstance(trace.stages[0].measurements, tuple)
    with pytest.raises(ValidationError): trace.stages[0].measurements = ()
    with pytest.raises(ValidationError): trace.model_copy(update={"stages": (stage, stage.model_copy(update={"stage_id": "s2", "sequence": 0}))})
    assert api.RequestTrace.model_validate_json(trace.model_dump_json()) == trace


def test_operation_links_multiple_waiters():
    links = tuple(api.OperationWaiterLink(request_trace_id=f"t{i}", request_id=f"r{i}", linked_at=NOW) for i in range(2))
    operation = api.CacheOperationTrace(operation_id="cacheop_" + "a" * 32, operation_type="prefetch", waiters=links)
    assert len(operation.waiters) == 2


@pytest.mark.parametrize("value", ["op1", "cacheop_A" + "a" * 31, "cacheop_" + "g" * 32])
def test_cache_operation_ids_require_canonical_task_format(value):
    with pytest.raises(ValidationError): api.CacheOperationTrace(operation_id=value, operation_type="lookup")
    with pytest.raises(ValidationError): api.RequestTrace(context=context(), cache_operation_ids=(value,))


@pytest.mark.parametrize("code_or_scalar", [
    "physical_path", "file_path", "filesystem_path", "raw_exception", "exception",
    "traceback", "stack_trace", "api_key", "access_token", "authorization", "bearer",
    "cookie", "password", "credential", "secret", "request_body", "http_header",
    "redis_key", "kv_bytes", "tensor", "device_pointer", "private_lmcache_object",
    "chunk_index",
])
def test_sensitive_measurement_names_and_values_are_rejected(code_or_scalar):
    with pytest.raises(ValidationError): api.TraceMeasurement(code=code_or_scalar, value_kind="actual", count=1)
    with pytest.raises(ValidationError): api.TraceMeasurement(code="safe_code", value_kind="actual", scalar=code_or_scalar)


@pytest.mark.parametrize("value", [
    "/var/cache/kv.bin", r"C:\\cache\\kv.bin", "../cache/kv.bin", "cache/kv.bin",
    r"cache\\kv.bin", "weights.safetensors",
])
def test_measurement_scalar_rejects_physical_paths(value):
    with pytest.raises(ValidationError): api.TraceMeasurement(code="safe_code", value_kind="actual", scalar=value)


@pytest.mark.parametrize("value", [2**53, -(2**53), 1e300, math.inf, math.nan])
def test_measurement_scalar_numeric_bounds(value):
    with pytest.raises(ValidationError): api.TraceMeasurement(code="safe_code", value_kind="actual", scalar=value)


def test_source_endpoint_may_be_a_uri_but_remains_sanitized():
    assert provenance(source_endpoint="https://gateway.example/v1").source_endpoint.startswith("https://")


@pytest.mark.parametrize("updates", [
    {"runtime_profile": "v1", "source_component": "legacy_adapter"},
    {"runtime_profile": "test/mock", "source_component": "legacy_adapter"},
    {"runtime_profile": "v1", "gateway_profile": "legacy_gateway"},
    {"runtime_profile": "test/mock", "gateway_profile": "legacy_gateway"},
    {"runtime_profile": "legacy", "legacy_projected": True, "source_component": "proxy"},
    {"runtime_profile": "v1", "gateway_adapter": "legacy_adapter"},
    {"runtime_profile": "test/mock", "storage_adapter": "redis_legacy"},
])
def test_provenance_rejects_legacy_claims_from_nonlegacy_sources(updates):
    with pytest.raises(ValidationError): provenance(**updates)


def test_valid_legacy_and_nonlegacy_provenance_combinations():
    assert provenance(runtime_profile="legacy", source_component="legacy_adapter", legacy_projected=True,
                      gateway_profile="legacy_gateway").legacy_projected
    assert provenance(runtime_profile="v1", source_component="gateway", gateway_profile="mp_http_api").runtime_profile is RuntimeProfile.V1
    assert provenance(runtime_profile="test/mock", source_component="test", gateway_profile="mock").runtime_profile is RuntimeProfile.TEST_MOCK


def test_stage_reference_self_and_cycles_are_rejected():
    base = dict(name="fallback", state="skipped", provenance=provenance(), skip_reason="not_required")
    with pytest.raises(ValidationError):
        api.RequestTrace(context=context(), stages=(api.TraceStage(stage_id="s", sequence=0, parent_stage_id="s", **base),))
    with pytest.raises(ValidationError):
        api.RequestTrace(context=context(), stages=(api.TraceStage(stage_id="s", sequence=0, fallback_stage_id="s", **base),))
    parent_cycle = (
        api.TraceStage(stage_id="a", sequence=0, parent_stage_id="b", **base),
        api.TraceStage(stage_id="b", sequence=1, parent_stage_id="a", **base),
    )
    fallback_cycle = (
        api.TraceStage(stage_id="a", sequence=0, fallback_stage_id="b", **base),
        api.TraceStage(stage_id="b", sequence=1, fallback_stage_id="a", **base),
    )
    with pytest.raises(ValidationError, match="cycle"): api.RequestTrace(context=context(), stages=parent_cycle)
    with pytest.raises(ValidationError, match="cycle"): api.RequestTrace(context=context(), stages=fallback_cycle)
