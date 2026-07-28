from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from kdn_server.domain import (
    CacheArtifact,
    CacheOperationState,
    CacheOperationTask,
    CacheOperationType,
    CacheReplicaObservation,
    LMCacheEndpoint,
    LMCacheProfile,
    ObservationConfidence,
    ObservationSource,
    QueueState,
    QueueWork,
    RuntimeProfile,
    StateTransitionError,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def artifact(**overrides):
    values = dict(knowledge_id="kid-1", model_id="model-1", runtime_profile="v1")
    return CacheArtifact(**(values | overrides))


def endpoint(**overrides):
    values = dict(name="worker-a", runtime_profile="v1", lmcache_profile="mp_sdk")
    return LMCacheEndpoint(**(values | overrides))


def observation(**overrides):
    ep = endpoint()
    values = dict(
        artifact_id=artifact().artifact_id,
        available=True,
        source=ObservationSource.SDK,
        endpoint_id=ep.endpoint_id,
        endpoint_generation=ep.generation,
        runtime_profile=RuntimeProfile.V1,
        lmcache_profile=LMCacheProfile.MP_SDK,
        observed_at=NOW,
        expires_at=NOW + timedelta(seconds=30),
        confidence=ObservationConfidence.HIGH,
    )
    return CacheReplicaObservation(**(values | overrides))


def test_operation_transitions_are_validated_and_idempotent():
    pending = CacheOperationTask(operation="prefetch", artifact_id="artifact-1")
    assert pending.transition(CacheOperationState.PENDING) is pending
    running = pending.transition("running", at=NOW)
    assert running.state is CacheOperationState.RUNNING
    assert running.attempt == 1
    assert running.transition("succeeded").terminal
    with pytest.raises(StateTransitionError) as error:
        pending.transition("succeeded")
    assert error.value.to_dict()["error"] == "invalid_state_transition"


def test_queue_state_is_independent_from_operation_state():
    task = CacheOperationTask(operation=CacheOperationType.LOOKUP, artifact_id="a")
    work = QueueWork(cache_task_id=task.task_id).transition(QueueState.CLAIMED)
    assert work.state is QueueState.CLAIMED
    assert task.state is CacheOperationState.PENDING
    assert work.transition(QueueState.CLAIMED) is work


def test_serialization_immutable_snapshot_and_stable_ids():
    first = artifact()
    second = artifact(created_at=NOW + timedelta(days=1))
    assert first.artifact_id == second.artifact_id
    assert CacheArtifact.model_validate_json(first.to_json()) == first
    with pytest.raises(ValidationError):
        first.knowledge_id = "changed"


@pytest.mark.parametrize("field", ["password", "credential", "redis_key", "kv_bytes", "device_pointer", "chunk_index"])
def test_secret_and_physical_fields_are_rejected(field):
    with pytest.raises(ValidationError):
        artifact(**{field: "must-not-enter-domain"})


def test_observation_expiry_generation_and_legacy_projection():
    ep = endpoint()
    current = observation()
    assert current.is_fresh(NOW + timedelta(seconds=29))
    assert not current.is_fresh(NOW + timedelta(seconds=30))
    assert current.applies_to(ep, NOW)
    assert not current.applies_to(ep.next_generation(), NOW)
    assert observation(expires_at=datetime.now(timezone.utc) + timedelta(minutes=1)).kv_ready == 1
    with pytest.raises((AttributeError, ValidationError)):
        current.kv_ready = 0


def test_runtime_auto_resolution_and_persistence_rejection():
    assert RuntimeProfile.resolve_auto("auto") is RuntimeProfile.LEGACY
    assert RuntimeProfile.resolve_auto("auto", v1_available=True) is RuntimeProfile.V1
    assert RuntimeProfile.resolve_auto("legacy", v1_available=True) is RuntimeProfile.LEGACY
    with pytest.raises(ValidationError, match="startup-only"):
        artifact(runtime_profile="auto")
