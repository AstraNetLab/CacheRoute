from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from kdn_server.contracts import *
from kdn_server.domain import CacheArtifact, LMCacheEndpoint
from kdn_server.gateway import *

NOW = datetime.now(timezone.utc)


def capabilities(**changes):
    values = dict(runtime_profile="test/mock", transport_kind="mock",
        compatibility_profile=LMCacheCompatibilityProfile(compatibility_profile_id="cpu-test"),
        endpoint_id="endpoint_" + "1" * 32, endpoint_generation=1, source="fixture",
        token_lookup="supported", async_completion="supported", cancellation="supported")
    return CapabilitySnapshot(**(values | changes))


def artifact(knowledge_id="kid"):
    return CacheArtifact(knowledge_id=knowledge_id, model_profile="model", tokenizer_profile="tokenizer",
        cache_data_profile="layout", compatibility_profile_id="cpu-test", runtime_profile="test/mock")


def intent(**changes):
    values = dict(runtime_profile="test/mock", artifact_id=artifact().artifact_id,
        idempotency_key="same", compatibility_profile_id="cpu-test",
        endpoint_id="endpoint_" + "1" * 32, endpoint_generation=1)
    return CreatePrefetchIntentRequest(**(values | changes))


def test_versions_profiles_freezing_and_round_trip():
    request = ResolveKnowledgeRequest(runtime_profile="v1", knowledge_id="kid", timestamp=NOW)
    assert ResolveKnowledgeRequest.model_validate_json(request.model_dump_json()) == request
    with pytest.raises(ValidationError): request.runtime_profile = "legacy"
    with pytest.raises(ValidationError): ResolveKnowledgeRequest(runtime_profile="auto", knowledge_id="kid")
    with pytest.raises(ValidationError): ResolveKnowledgeRequest(runtime_profile="v1", knowledge_id="kid", contract_version="v2")


def test_gateway_profiles_and_unknown_is_not_supported():
    assert {x.value for x in GatewayTransportKind} == {
        "mp_http_api", "mp_coordinator", "mp_sdk", "mp_metrics_events", "mp_l2_plugin",
        "legacy_redis", "mock", "unknown_future"}
    snapshot = capabilities(token_lookup="unknown")
    assert not snapshot.token_lookup
    with pytest.raises(ValidationError): snapshot.loaded_adapters = ("new",)


def test_mock_lookup_fallback_idempotency_completion_and_cancel():
    cache = artifact()
    gateway = MockGateway(capabilities(), artifacts=(cache,))
    lookup = LookupArtifactRequest(runtime_profile="test/mock", artifact_id=cache.artifact_id)
    assert gateway.lookup_artifact(lookup).artifact == cache
    tokens = LookupTokensRequest(runtime_profile="test/mock", tokens=TokenInput(token_ids=(1, 2)))
    assert gateway.lookup_tokens(tokens).outcome is OutcomeCode.TEXT_FALLBACK
    first = gateway.submit_operation(intent()).operation
    assert gateway.submit_operation(intent()).operation.task_id == first.task_id
    with pytest.raises(GatewayContractException) as conflict:
        gateway.submit_operation(intent(artifact_id=artifact("different").artifact_id))
    assert conflict.value.error.code is OutcomeCode.IDEMPOTENCY_CONFLICT
    assert gateway.complete(first.task_id).state.value == "succeeded"
    second = gateway.submit_operation(intent(idempotency_key="cancel")).operation
    cancel = CancelOperationRequest(runtime_profile="test/mock", task_id=second.task_id)
    assert gateway.cancel_operation(cancel).operation.state.value == "cancelled"


@pytest.mark.parametrize("field", ["password", "api_key", "credentials", "authorization",
    "redis_key", "kv_bytes", "tensor", "device_pointer", "chunk_index", "block_index", "lmcache_object"])
def test_contracts_reject_secrets_and_physical_payloads(field):
    with pytest.raises(ValidationError):
        ResolveKnowledgeRequest(runtime_profile="v1", knowledge_id="kid", **{field: "forbidden"})


def test_legacy_is_explicit_read_only_and_factory_has_no_production_io():
    legacy_caps = capabilities(runtime_profile="legacy", transport_kind="legacy_redis",
        token_lookup="unsupported", async_completion="unsupported", cancellation="unsupported")
    legacy = create_gateway("legacy_redis", legacy_caps)
    result = legacy.submit_operation(intent(runtime_profile="v1"))
    assert result.outcome is OutcomeCode.UNSUPPORTED and legacy.read_only
    with pytest.raises(NotImplementedError): create_gateway("mp_http_api", capabilities())
