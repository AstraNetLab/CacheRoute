from datetime import datetime, timedelta, timezone
from typing import get_args

import pytest
from pydantic import ValidationError

from kdn_server.contracts import *
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
        tier_capacity_usage="supported", maintenance_eviction="supported")
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
    observed = NOW - timedelta(seconds=1 if fresh else 20)
    return CacheReplicaObservation(artifact_id=artifact(runtime_profile=runtime_profile).artifact_id,
        state="available", source="legacy_projection" if legacy else "mock", endpoint_id=ENDPOINT_ID,
        endpoint_generation=0 if legacy else 1, runtime_profile=runtime_profile,
        gateway_profile="legacy_gateway" if legacy else "mock", compatibility_profile_id="cpu-test",
        source_observed_at=observed, projected_at=NOW, expires_at=observed + timedelta(seconds=10),
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
    assert TokenCoverage(total_tokens=5, covered_ranges=((0, 2), (2, 5)))
    for ranges in (((-1, 1),), ((1, 1),), ((1, 6),), ((2, 4), (1, 2)), ((0, 3), (2, 4))):
        with pytest.raises(ValidationError): TokenCoverage(total_tokens=5, covered_ranges=ranges)


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
    with pytest.raises(GatewayContractException): gateway.submit_operation(intent(artifact_id=artifact("different").artifact_id))
    running = gateway.start(first.task_id)
    cancelled = gateway.cancel_operation(CancelOperationRequest(**target(), task_id=running.task_id))
    assert cancelled.outcome is OutcomeCode.CANCELLED and cancelled.operation.state.value == "cancelled"
    done = gateway.submit_operation(intent(idempotency_key="done")).operation
    gateway.complete(done.task_id)
    terminal = gateway.cancel_operation(CancelOperationRequest(**target(), task_id=done.task_id))
    assert terminal.outcome is OutcomeCode.SUCCESS and terminal.operation.state.value == "succeeded"


def test_summary_models_and_response_consistency():
    capacity = CapacityUsageObservation(source="mock", endpoint_generation=1, support="supported", capacity_bytes=10, used_bytes=4)
    adapter = AdapterSummary(source="mock", endpoint_generation=1, support="supported", loaded_adapters=("a",))
    tier = TierSummary(source="mock", endpoint_generation=1, support="supported", l1_tiers=("cpu",), capacity=(capacity,))
    maintenance = MaintenanceSummary(source="mock", endpoint_generation=1, support="unknown", partial=True)
    for model in (capacity, adapter, tier, maintenance): assert type(model).model_validate_json(model.model_dump_json()) == model
    gateway = MockGateway(capabilities(), adapter_summary=adapter, tier_summary=tier, maintenance_summary=maintenance)
    assert gateway.get_tier_adapter_summary(GetTierAndAdapterSummaryRequest(**target())).tier_summary == tier
    assert gateway.get_maintenance_status(GetMaintenanceStatusRequest(**target())).maintenance_summary == maintenance
    with pytest.raises(ValidationError): CacheServiceResponse(runtime_profile="test/mock", outcome="success", error=error(OutcomeCode.FAILED))
    with pytest.raises(ValidationError): CacheServiceResponse(runtime_profile="test/mock", outcome="failed")
    with pytest.raises(ValidationError): CacheServiceResponse(runtime_profile="test/mock", outcome="text_fallback", error=error(OutcomeCode.TEXT_FALLBACK))


def test_legacy_fresh_stale_read_only_and_v1_incompatible():
    caps = capabilities(runtime_profile="legacy", adapter_bindings=(binding("legacy_redis"),),
        token_lookup="unsupported", warm_prefetch="unsupported", cancellation="unsupported")
    fresh, stale = observation(fresh=True, runtime_profile="legacy", legacy=True), observation(fresh=False, runtime_profile="legacy", legacy=True)
    request = GetCacheObservationRequest(**target(runtime_profile="legacy"), artifact_id=fresh.artifact_id)
    assert LegacyCacheAdapter(caps, observations=(fresh,)).get_cache_observation(request).outcome is OutcomeCode.SUCCESS
    assert LegacyCacheAdapter(caps, observations=(stale,)).get_cache_observation(request).outcome is OutcomeCode.STALE
    legacy = create_gateway("legacy_redis", caps)
    assert legacy.submit_operation(intent(runtime_profile="legacy")).outcome is OutcomeCode.UNSUPPORTED
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
    forbidden = {"socket", "redis", "torch", "vllm", "lmcache"}
    assert not forbidden.intersection(type(gateway).__module__.split("."))
