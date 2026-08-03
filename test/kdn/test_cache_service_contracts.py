from datetime import datetime, timedelta, timezone
from typing import get_args

import pytest
from pydantic import ValidationError

from cacheroute.contracts.v1 import *
from cacheroute.contracts.v1.cache_service import CacheServiceResponse, GatewayTargetedResponse
from kdn_server.domain import CacheArtifact, CacheReplicaObservation, LMCacheEndpoint
from kdn_server.gateway import *

NOW = datetime.now(timezone.utc)
ENDPOINT_ID = "endpoint_" + "1" * 32


def binding(kind="mock"):
    return GatewayAdapterBinding(transport_kind=kind, binding_id=f"{kind}-binding")


def capabilities(**changes):
    values = dict(runtime_profile="test/mock", adapter_bindings=(binding(),),
        compatibility_profile=LMCacheCompatibilityProfile(compatibility_profile_id="cpu-test", key_hash_profile="sha256-v1"),
        endpoint_id=ENDPOINT_ID, endpoint_generation=1, source="fixture", loaded_adapters=("a", "b"),
        token_lookup="supported", warm_prefetch="supported", pin_unpin="supported",
        object_deletion="supported", operation_status="supported", cancellation="supported",
        tier_capacity_usage="supported", maintenance_eviction="supported",
        artifact_lookup="supported", cache_observation="supported")
    return CapabilitySnapshot(**(values | changes))


def target(**changes):
    return dict(runtime_profile="test/mock", compatibility_profile_id="cpu-test",
                endpoint_id=ENDPOINT_ID, endpoint_generation=1) | changes


def artifact(knowledge_id="kid", runtime_profile="test/mock"):
    return CacheArtifact(knowledge_id=knowledge_id, model_profile="model", tokenizer_profile="tokenizer",
        cache_data_profile="layout", compatibility_profile_id="cpu-test", runtime_profile=runtime_profile)


def intent(cls=CreatePrefetchIntentRequest, **changes):
    return cls(**(target() | dict(artifact_id=artifact().artifact_id, idempotency_key="same") | changes))


def observation(*, fresh=True, runtime_profile="test/mock", legacy=False):
    observed = datetime.now(timezone.utc) - timedelta(seconds=1) if fresh else NOW - timedelta(minutes=20)
    return CacheReplicaObservation(artifact_id=artifact(runtime_profile=runtime_profile).artifact_id,
        state="available", source="legacy_projection" if legacy else "mock", endpoint_id=ENDPOINT_ID,
        endpoint_generation=0 if legacy else 1, runtime_profile=runtime_profile,
        gateway_profile="legacy_gateway" if legacy else "mock", compatibility_profile_id="cpu-test",
        source_observed_at=observed, projected_at=max(NOW, observed), expires_at=observed + timedelta(minutes=10),
        legacy_projection=legacy, compatibility_uncertain=legacy)


def error(code, fallback=False):
    return ContractErrorDetail(code=code, message=code.value, fallback_eligible=fallback)


def test_versions_profiles_freezing_and_round_trips():
    requests = [
        GetCacheObservationRequest(**target(), artifact_id=artifact().artifact_id),
        LookupArtifactRequest(**target(), artifact_id=artifact().artifact_id),
        LookupTokensRequest(**target(), tokens=TokenInput(token_ids=(1, 2))), intent(),
        GetOperationStatusRequest(**target(), task_id="cacheop_" + "1" * 32),
        CancelOperationRequest(**target(), task_id="cacheop_" + "1" * 32),
        GetLMCacheEndpointsRequest(runtime_profile="test/mock"), GetTierAndAdapterSummaryRequest(**target()),
        GetMaintenanceStatusRequest(**target()), ResolveKnowledgeRequest(runtime_profile="v1", knowledge_id="kid"),
    ]
    for request in requests:
        assert type(request).model_validate_json(request.model_dump_json()) == request
        with pytest.raises(ValidationError): request.runtime_profile = "legacy"
    with pytest.raises(ValidationError): ResolveKnowledgeRequest(runtime_profile="auto", knowledge_id="kid")
    with pytest.raises(ValidationError): ResolveKnowledgeRequest(runtime_profile="v1", knowledge_id="kid", contract_version="v2")


@pytest.mark.parametrize("request_cls,values", [
    (LookupArtifactRequest, {"artifact_id": artifact().artifact_id}),
    (GetCacheObservationRequest, {"artifact_id": artifact().artifact_id}),
    (LookupTokensRequest, {"tokens": TokenInput(token_ids=(1,))}),
    (GetOperationStatusRequest, {"task_id": "cacheop_" + "1" * 32}),
    (CancelOperationRequest, {"task_id": "cacheop_" + "1" * 32}),
    (GetTierAndAdapterSummaryRequest, {}), (GetMaintenanceStatusRequest, {}),
])
def test_target_metadata_is_required_and_validated(request_cls, values):
    for missing in ("compatibility_profile_id", "endpoint_id", "endpoint_generation"):
        data = target() | values; data.pop(missing)
        with pytest.raises(ValidationError): request_cls(**data)
    with pytest.raises(ValidationError): request_cls(**(target(endpoint_id="bad") | values))
    with pytest.raises(ValidationError): request_cls(**(target(endpoint_generation=0) | values))


def test_token_coverage_boundaries():
    assert TokenCoverage(whole_request_hit=True, total_tokens=5, covered_ranges=((0, 2), (2, 5)))
    for ranges in (((-1, 1),), ((1, 1),), ((1, 6),), ((2, 4), (1, 2)), ((0, 3), (2, 4))):
        with pytest.raises(ValidationError): TokenCoverage(whole_request_hit=False, total_tokens=5, covered_ranges=ranges)


def test_transport_runtime_matrix_composition_and_factory_membership():
    mp = ("mp_http_api", "mp_coordinator", "mp_sdk", "mp_metrics_events", "mp_l2_plugin", "unknown_future")
    composed = capabilities(runtime_profile="v1", adapter_bindings=tuple(binding(x) for x in mp))
    assert tuple(x.transport_kind.value for x in composed.adapter_bindings) == mp
    for profile, good in (("v1", "mp_sdk"), ("legacy", "legacy_redis"), ("test/mock", "mock")):
        assert capabilities(runtime_profile=profile, adapter_bindings=(binding(good),))
        for bad in set(x.value for x in GatewayTransportKind) - ({*mp} if profile == "v1" else {good}):
            with pytest.raises(ValidationError): capabilities(runtime_profile=profile, adapter_bindings=(binding(bad),))
    with pytest.raises(ValueError): create_gateway("legacy_redis", capabilities())
    with pytest.raises(ValidationError): capabilities(adapter_bindings=(binding(), binding()))


def test_names_compatibility_profile_and_snapshot_immutability():
    assert capabilities().compatibility_profile.key_hash_profile == "sha256-v1"
    for changes in ({"loaded_adapters": ("a", "a")}, {"loaded_adapters": ("",)}, {"l1_tiers": ("x", "x")}):
        with pytest.raises(ValidationError): capabilities(**changes)
    snapshot = capabilities(token_lookup="unknown")
    assert not snapshot.token_lookup
    with pytest.raises(ValidationError): snapshot.loaded_adapters = ("new",)


def test_negotiation_mismatch_and_generation_stale_preserve_correlation():
    gateway = MockGateway(capabilities())
    base = dict(tokens=TokenInput(token_ids=(1,)), request_id="request", correlation_id="correlation")
    for changes, outcome in (({"runtime_profile": "legacy"}, OutcomeCode.INCOMPATIBLE),
                             ({"compatibility_profile_id": "other"}, OutcomeCode.INCOMPATIBLE),
                             ({"endpoint_id": "endpoint_" + "2" * 32}, OutcomeCode.INCOMPATIBLE),
                             ({"endpoint_generation": 2}, OutcomeCode.STALE)):
        response = gateway.lookup_tokens(LookupTokensRequest(**(target(**changes) | base)))
        assert response.outcome is outcome and response.request_id == "request" and response.correlation_id == "correlation"
        assert response.error.code is outcome


@pytest.mark.parametrize("request_factory,capability", [
    (lambda: LookupArtifactRequest(**target(), artifact_id=artifact().artifact_id), "artifact_lookup"),
    (lambda: GetCacheObservationRequest(**target(), artifact_id=artifact().artifact_id), "cache_observation"),
    (lambda: LookupTokensRequest(**target(), tokens=TokenInput(token_ids=(1,))), "token_lookup"),
    (lambda: intent(), "warm_prefetch"), (lambda: intent(CreateRebuildIntentRequest), "warm_prefetch"),
    (lambda: intent(CreatePinIntentRequest), "pin_unpin"), (lambda: intent(CreateUnpinIntentRequest), "pin_unpin"),
    (lambda: intent(CreateClearIntentRequest), "object_deletion"),
    (lambda: GetOperationStatusRequest(**target(), task_id="cacheop_" + "1" * 32), "operation_status"),
    (lambda: CancelOperationRequest(**target(), task_id="cacheop_" + "1" * 32), "cancellation"),
    (lambda: GetTierAndAdapterSummaryRequest(**target()), "tier_capacity_usage"),
    (lambda: GetMaintenanceStatusRequest(**target()), "maintenance_eviction"),
])
@pytest.mark.parametrize("state", ["unsupported", "unknown"])
def test_every_capability_gate_rejects_unsupported_and_unknown(request_factory, capability, state):
    gateway = MockGateway(capabilities(**{capability: state}))
    request = request_factory()
    method = (gateway.lookup_tokens if isinstance(request, LookupTokensRequest) else
              gateway.lookup_artifact if isinstance(request, LookupArtifactRequest) else
              gateway.get_cache_observation if isinstance(request, GetCacheObservationRequest) else
              gateway.submit_operation if isinstance(request, OperationIntentRequest) else
              gateway.get_operation_status if isinstance(request, GetOperationStatusRequest) and not isinstance(request, CancelOperationRequest) else
              gateway.cancel_operation if isinstance(request, CancelOperationRequest) else
              gateway.get_tier_adapter_summary if isinstance(request, GetTierAndAdapterSummaryRequest) else gateway.get_maintenance_status)
    assert method(request).outcome is OutcomeCode.UNSUPPORTED


def test_lookup_fallback_idempotency_completion_and_terminal_cancel():
    cache = artifact(); gateway = MockGateway(capabilities(), artifacts=(cache,))
    assert gateway.lookup_artifact(LookupArtifactRequest(**target(), artifact_id=cache.artifact_id)).artifact == cache
    fallback = gateway.lookup_tokens(LookupTokensRequest(**target(), tokens=TokenInput(token_ids=(1, 2))))
    assert fallback.outcome is OutcomeCode.TEXT_FALLBACK and fallback.error.fallback_eligible
    first = gateway.submit_operation(intent()).operation
    assert gateway.submit_operation(intent()).operation.task_id == first.task_id
    conflict = gateway.submit_operation(intent(artifact_id=artifact("different").artifact_id))
    assert conflict.outcome is OutcomeCode.IDEMPOTENCY_CONFLICT
    assert conflict.runtime_profile.value == "test/mock" and conflict.endpoint_id == ENDPOINT_ID
    running = gateway.start(first.task_id)
    cancelled = gateway.cancel_operation(CancelOperationRequest(**target(), task_id=running.task_id))
    assert cancelled.outcome is OutcomeCode.CANCELLED and cancelled.operation.state.value == "cancelled"
    done = gateway.submit_operation(intent(idempotency_key="done")).operation
    gateway.complete(done.task_id)
    terminal = gateway.cancel_operation(CancelOperationRequest(**target(), task_id=done.task_id))
    assert terminal.outcome is OutcomeCode.SUCCESS and terminal.operation.state.value == "succeeded"


def test_summary_models_and_response_consistency():
    provenance = dict(source="mock", runtime_profile="test/mock", compatibility_profile_id="cpu-test",
        endpoint_id=ENDPOINT_ID, endpoint_generation=1)
    capacity = CapacityUsageObservation(**provenance, support="supported", tier_name="cpu", tier_level="l1", capacity_bytes=10, used_bytes=4)
    adapter = AdapterSummary(**provenance, support="supported", loaded_adapters=("a",))
    tier = TierSummary(**provenance, support="supported", l1_tiers=("cpu",), capacity=(capacity,))
    maintenance = MaintenanceSummary(**provenance, support="unknown", partial=True)
    for model in (capacity, adapter, tier, maintenance): assert type(model).model_validate_json(model.model_dump_json()) == model
    gateway = MockGateway(capabilities(), adapter_summary=adapter, tier_summary=tier, maintenance_summary=maintenance)
    assert gateway.get_tier_adapter_summary(GetTierAndAdapterSummaryRequest(**target())).tier_summary == tier
    assert gateway.get_maintenance_status(GetMaintenanceStatusRequest(**target())).maintenance_summary == maintenance
    with pytest.raises(ValidationError): CacheServiceResponse(runtime_profile="test/mock", outcome="success", error=error(OutcomeCode.FAILED))
    with pytest.raises(ValidationError): CacheServiceResponse(runtime_profile="test/mock", outcome="failed")
    with pytest.raises(ValidationError): CacheServiceResponse(runtime_profile="test/mock", outcome="text_fallback", error=error(OutcomeCode.TEXT_FALLBACK))


def test_legacy_fresh_stale_read_only_and_v1_incompatible():
    caps = capabilities(runtime_profile="legacy", adapter_bindings=(binding("legacy_redis"),),
        endpoint_generation=0, token_lookup="unsupported", warm_prefetch="unsupported", cancellation="unsupported")
    fresh, stale = observation(fresh=True, runtime_profile="legacy", legacy=True), observation(fresh=False, runtime_profile="legacy", legacy=True)
    request = GetCacheObservationRequest(**target(runtime_profile="legacy", endpoint_generation=0), artifact_id=fresh.artifact_id)
    assert LegacyCacheAdapter(caps, observations=(fresh,)).get_cache_observation(request).outcome is OutcomeCode.SUCCESS
    assert LegacyCacheAdapter(caps, observations=(stale,)).get_cache_observation(request).outcome is OutcomeCode.STALE
    legacy = create_gateway("legacy_redis", caps)
    assert legacy.submit_operation(intent(runtime_profile="legacy", endpoint_generation=0)).outcome is OutcomeCode.UNSUPPORTED
    assert legacy.submit_operation(intent(runtime_profile="v1")).outcome is OutcomeCode.INCOMPATIBLE
    endpoints = legacy.get_endpoints(GetLMCacheEndpointsRequest(runtime_profile="legacy", request_id="r", correlation_id="c"))
    assert endpoints.outcome is OutcomeCode.UNSUPPORTED and (endpoints.request_id, endpoints.correlation_id) == ("r", "c")


@pytest.mark.parametrize("field", ["password", "api_key", "credentials", "authorization", "redis_key",
    "kv_bytes", "tensor", "device_pointer", "chunk_index", "block_index", "lmcache_object"])
@pytest.mark.parametrize("factory", [
    lambda **x: ResolveKnowledgeRequest(runtime_profile="v1", knowledge_id="kid", **x),
    lambda **x: LookupArtifactRequest(**target(), artifact_id=artifact().artifact_id, **x),
    lambda **x: LookupTokensRequest(**target(), tokens=TokenInput(token_ids=(1,)), **x),
    lambda **x: intent(**x), lambda **x: GetOperationStatusRequest(**target(), task_id="cacheop_" + "1" * 32, **x),
    lambda **x: GetLMCacheEndpointsRequest(runtime_profile="test/mock", **x),
])
def test_contract_families_reject_secrets_and_physical_payloads(factory, field):
    with pytest.raises(ValidationError): factory(**{field: "forbidden"})


def test_protocol_conformance_and_dependency_isolation(monkeypatch):
    gateway = MockGateway(capabilities())
    assert isinstance(gateway, LMCacheGateway)
    legacy_caps = capabilities(runtime_profile="legacy", endpoint_generation=0,
        adapter_bindings=(binding("legacy_redis"),))
    assert isinstance(LegacyCacheAdapter(legacy_caps), LMCacheGateway)
    forbidden = {"socket", "redis", "torch", "vllm", "lmcache"}
    assert not forbidden.intersection(type(gateway).__module__.split("."))


def test_legacy_unknown_generation_and_mixed_generation_rejection():
    assert GetCacheObservationRequest(**target(runtime_profile="legacy", endpoint_generation=0), artifact_id=artifact("x", "legacy").artifact_id)
    with pytest.raises(ValidationError): GetCacheObservationRequest(**target(endpoint_generation=0), artifact_id=artifact().artifact_id)
    with pytest.raises(ValidationError): CapabilitySnapshot(**(capabilities().model_dump() | {"endpoint_generation": 0}))
    legacy_observation = observation(fresh=True, runtime_profile="legacy", legacy=True)
    with pytest.raises(ValidationError):
        GetCacheObservationResponse(**target(runtime_profile="legacy", endpoint_generation=1),
            outcome="success", observation=legacy_observation)


def test_fixture_provenance_and_dedicated_response_invariants():
    wrong_artifact = artifact(runtime_profile="legacy")
    gateway = MockGateway(capabilities(), artifacts=(wrong_artifact,))
    request = LookupArtifactRequest(**target(), artifact_id=wrong_artifact.artifact_id)
    assert gateway.lookup_artifact(request).outcome is OutcomeCode.INCOMPATIBLE
    endpoint = LMCacheEndpoint(name="different", runtime_profile="test/mock", gateway_profile="mock",
        compatibility_profile_id="cpu-test", generation=1)
    endpoint_result = MockGateway(capabilities(), endpoints=(endpoint,)).get_endpoints(
        GetLMCacheEndpointsRequest(runtime_profile="test/mock"))
    assert endpoint_result.outcome is OutcomeCode.INCOMPATIBLE
    required = ((GetCacheObservationResponse, "observation"), (LookupArtifactResponse, "artifact"),
        (LookupTokensResponse, "token_coverage"), (GetOperationStatusResponse, "operation"),
        (GetLMCacheEndpointsResponse, "endpoints"),
        (GetTierAndAdapterSummaryResponse, "adapter_summary"),
        (GetMaintenanceStatusResponse, "maintenance_summary"))
    for response_type, _ in required:
        with pytest.raises(ValidationError): response_type(runtime_profile="test/mock")


def test_deterministic_stale_round_trip_and_error_version():
    stale = observation(fresh=False)
    response = GetCacheObservationResponse(**target(), timestamp=NOW, outcome="stale",
        error=error(OutcomeCode.STALE), observation=stale)
    assert GetCacheObservationResponse.model_validate_json(response.model_dump_json()) == response
    with pytest.raises(ValidationError): ContractErrorDetail(code="failed", message="bad", contract_version="v2")


def test_public_exports_are_explicit():
    import kdn_server.gateway as gateway
    assert "CapabilitySnapshot" in gateway.__all__ and "MockGateway" in gateway.__all__


def test_targeted_error_responses_require_target_metadata():
    for response_type in (GetCacheObservationResponse, LookupArtifactResponse, LookupTokensResponse,
                          GetOperationStatusResponse, GetTierAndAdapterSummaryResponse,
                          GetMaintenanceStatusResponse):
        with pytest.raises(ValidationError):
            response_type(runtime_profile="test/mock", outcome="unsupported",
                          error=error(OutcomeCode.UNSUPPORTED))


def test_response_level_object_provenance_and_freshness():
    stale = observation(fresh=False)
    with pytest.raises(ValidationError):
        GetCacheObservationResponse(**target(), timestamp=NOW, observation=stale)
    wrong_artifact = artifact(runtime_profile="legacy")
    with pytest.raises(ValidationError):
        LookupArtifactResponse(**target(), artifact=wrong_artifact)
    fresh = observation(fresh=True)
    for changes in ({"runtime_profile": "legacy"}, {"compatibility_profile_id": "other"},
                    {"endpoint_id": "endpoint_" + "2" * 32}):
        with pytest.raises(ValidationError):
            GetCacheObservationResponse(**target(**changes), observation=fresh)
    gateway = MockGateway(capabilities())
    operation = gateway.submit_operation(intent()).operation
    with pytest.raises(ValidationError):
        GetOperationStatusResponse(**target(compatibility_profile_id="other"), operation=operation)


def test_nested_capacity_provenance_and_discovery_runtime_negotiation():
    provenance = dict(source="mock", runtime_profile="test/mock", compatibility_profile_id="cpu-test",
        endpoint_id=ENDPOINT_ID, endpoint_generation=1, support="supported")
    capacity = CapacityUsageObservation(**provenance, tier_name="cpu", tier_level="l1")
    with pytest.raises(ValidationError):
        TierSummary(**(provenance | {"compatibility_profile_id": "other"}),
                    l1_tiers=("cpu",), capacity=(capacity,))
    request = GetLMCacheEndpointsRequest(runtime_profile="v1")
    assert MockGateway(capabilities()).get_endpoints(request).outcome is OutcomeCode.INCOMPATIBLE
    legacy_caps = capabilities(runtime_profile="legacy", endpoint_generation=0,
        adapter_bindings=(binding("legacy_redis"),))
    assert LegacyCacheAdapter(legacy_caps).get_endpoints(request).outcome is OutcomeCode.INCOMPATIBLE


def test_protocol_dedicated_return_annotations_and_repeat_round_trip():
    import inspect
    expected = {"lookup_artifact": "LookupArtifactResponse", "lookup_tokens": "LookupTokensResponse",
        "get_cache_observation": "GetCacheObservationResponse",
        "get_operation_status": "GetOperationStatusResponse", "cancel_operation": "CancelOperationResponse",
        "get_endpoints": "GetLMCacheEndpointsResponse",
        "get_tier_adapter_summary": "GetTierAndAdapterSummaryResponse",
        "get_maintenance_status": "GetMaintenanceStatusResponse"}
    for method, return_name in expected.items():
        assert inspect.signature(getattr(LMCacheGateway, method)).return_annotation.__name__ == return_name
    submit_annotation = inspect.signature(LMCacheGateway.submit_operation).return_annotation
    assert len(submit_annotation.__args__) == 5
    value = LookupTokensResponse(**target(), token_coverage=TokenCoverage(whole_request_hit=True, total_tokens=2, covered_ranges=((0, 2),)))
    encoded = value.model_dump_json()
    for _ in range(3):
        value = LookupTokensResponse.model_validate_json(encoded)
        assert value.model_dump_json() == encoded


@pytest.mark.parametrize("lookup", ["supported", "unsupported", "unknown"])
@pytest.mark.parametrize("ranges", ["supported", "unsupported", "unknown"])
def test_token_and_range_capabilities_are_independent(lookup, ranges):
    coverage = TokenCoverage(whole_request_hit=False, total_tokens=4, covered_ranges=((0, 2),))
    gateway = MockGateway(capabilities(token_lookup=lookup, range_coverage=ranges),
                          token_fixtures={(1, 2, 3, 4): coverage})
    response = gateway.lookup_tokens(LookupTokensRequest(**target(), tokens=TokenInput(token_ids=(1, 2, 3, 4))))
    if lookup != "supported":
        assert response.outcome is OutcomeCode.UNSUPPORTED and response.token_coverage is None
    else:
        assert response.outcome is OutcomeCode.SUCCESS
        assert response.token_coverage.whole_request_hit is False
        assert bool(response.token_coverage.covered_ranges) is (ranges == "supported")


def test_missing_and_mismatched_summary_fixtures_are_structured():
    gateway = MockGateway(capabilities())
    tier_request, maintenance_request = GetTierAndAdapterSummaryRequest(**target()), GetMaintenanceStatusRequest(**target())
    assert gateway.get_tier_adapter_summary(tier_request).outcome is OutcomeCode.STALE
    assert gateway.get_maintenance_status(maintenance_request).outcome is OutcomeCode.STALE
    wrong = dict(source="mock", runtime_profile="test/mock", compatibility_profile_id="wrong",
        endpoint_id=ENDPOINT_ID, endpoint_generation=1, support="supported")
    adapter = AdapterSummary(**wrong, loaded_adapters=("a",))
    tier = TierSummary(**wrong, l1_tiers=("cpu",))
    maintenance = MaintenanceSummary(**wrong, active=True)
    gateway = MockGateway(capabilities(), adapter_summary=adapter, tier_summary=tier, maintenance_summary=maintenance)
    assert gateway.get_tier_adapter_summary(tier_request).outcome is OutcomeCode.INCOMPATIBLE
    assert gateway.get_maintenance_status(maintenance_request).outcome is OutcomeCode.INCOMPATIBLE


def test_operation_intent_response_types_reject_every_wrong_operation():
    gateway = MockGateway(capabilities())
    pairs = ((CreatePrefetchIntentRequest, CreatePrefetchIntentResponse),
             (CreatePinIntentRequest, CreatePinIntentResponse),
             (CreateUnpinIntentRequest, CreateUnpinIntentResponse),
             (CreateClearIntentRequest, CreateClearIntentResponse),
             (CreateRebuildIntentRequest, CreateRebuildIntentResponse))
    tasks = [gateway.submit_operation(intent(request_type, idempotency_key=request_type.__name__)).operation
             for request_type, _ in pairs]
    for index, (_, response_type) in enumerate(pairs):
        for wrong_index, task in enumerate(tasks):
            if index != wrong_index:
                with pytest.raises(ValidationError): response_type(**target(), operation=task)


def test_cancel_response_success_requires_terminal_task():
    gateway = MockGateway(capabilities())
    pending = gateway.submit_operation(intent(idempotency_key="pending")).operation
    running = gateway.start(gateway.submit_operation(intent(idempotency_key="running")).operation.task_id)
    succeeded = gateway.complete(gateway.submit_operation(intent(idempotency_key="succeeded")).operation.task_id)
    failed = gateway.complete(gateway.submit_operation(intent(idempotency_key="failed")).operation.task_id, failed=True)
    cancelled = pending.transition("cancelled")
    for task in (succeeded, failed, cancelled): assert CancelOperationResponse(**target(), operation=task)
    for task in (pending, running):
        with pytest.raises(ValidationError): CancelOperationResponse(**target(), operation=task)
    assert CancelOperationResponse(**target(), outcome="cancelled", error=error(OutcomeCode.CANCELLED), operation=cancelled)


def test_generic_response_cannot_bypass_target_metadata():
    coverage = TokenCoverage(whole_request_hit=True, total_tokens=1)
    for base in (CacheServiceResponse, GatewayTargetedResponse):
        with pytest.raises(ValidationError): base(runtime_profile="test/mock", token_coverage=coverage)
    assert "CacheServiceResponse" in __import__("cacheroute.contracts.v1", fromlist=["__all__"]).__all__
