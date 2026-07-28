from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from kdn_server.domain import *
from kdn_server.text_db import KBItem

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def artifact(**kw):
    base = dict(knowledge_id="kid", model_profile="model", tokenizer_profile="tok",
                cache_data_profile="layout", compatibility_profile_id="compat", created_at=NOW)
    return CacheArtifact(**(base | kw))


def endpoint(**kw):
    base = dict(name="node", gateway_profile="mp_sdk", compatibility_profile_id="compat")
    return LMCacheEndpoint(**(base | kw))


def observation(**kw):
    ep = endpoint()
    base = dict(artifact_id=artifact().artifact_id, state="available", source="sdk",
                endpoint_id=ep.endpoint_id, endpoint_generation=1, gateway_profile="mp_sdk",
                compatibility_profile_id="compat", observed_at=NOW, expires_at=NOW + timedelta(seconds=10))
    return CacheReplicaObservation(**(base | kw))


def task(**kw):
    base = dict(idempotency_key="submission", operation="lookup", artifact_id=artifact().artifact_id,
                compatibility_profile_id="compat", gateway_profile="mp_sdk", created_at=NOW, updated_at=NOW)
    return CacheOperationTask(**(base | kw))


def work(**kw):
    base = dict(idempotency_key="queue-submission", cache_task_id=task().task_id, created_at=NOW, updated_at=NOW)
    return QueueWork(**(base | kw))


def test_runtime_aliases_auto_resolution_and_freeze():
    for alias in ("old", "v0"): assert RuntimeProfile.normalize(alias) is RuntimeProfile.LEGACY
    for alias in ("modern", "new", "current"): assert RuntimeProfile.normalize(alias) is RuntimeProfile.V1
    assert RuntimeProfile.normalize("mock") is RuntimeProfile.TEST_MOCK
    resolved = RuntimeProfile.resolve_startup("auto", v1_available=False)
    snap = artifact(runtime_profile=resolved)
    assert snap.runtime_profile is RuntimeProfile.LEGACY
    with pytest.raises(ValidationError): artifact(runtime_profile="auto")
    with pytest.raises((ValueError, ValidationError)): RuntimeProfile.normalize("future")
    with pytest.raises(ValidationError): snap.runtime_profile = RuntimeProfile.V1


def test_artifact_canonical_identity_and_spoof_rejection():
    assert artifact().artifact_id == artifact().artifact_id
    assert artifact(knowledge_id="a|b", model_profile="c").artifact_id != artifact(knowledge_id="a", model_profile="b|c").artifact_id
    base = artifact()
    for change in (dict(tokenizer_profile="other"), dict(adapters=("a",)), dict(adapters=("a", "b")),
                   dict(cache_data_profile="other"), dict(compatibility_profile_id="other")):
        assert artifact(**change).artifact_id != base.artifact_id
    with pytest.raises(ValidationError, match="canonical"): artifact(artifact_id="artifact_" + "0" * 32)
    with pytest.raises(ValidationError): artifact(knowledge_id=" ")


def test_observation_state_id_expiry_and_endpoint_matching():
    assert observation(state="available").observation_id != observation(state="unavailable").observation_id
    current = observation()
    assert current.is_fresh(NOW)
    assert not current.is_fresh(NOW + timedelta(seconds=10))
    assert current.applies_to(endpoint(), NOW)
    assert not current.applies_to(endpoint(generation=2), NOW)
    assert not current.applies_to(endpoint(runtime_profile="legacy"), NOW)
    assert not current.applies_to(endpoint(compatibility_profile_id="other"), NOW)
    with pytest.raises(ValidationError): observation(observed_at=datetime(2026, 1, 1), expires_at=datetime(2026, 1, 2))
    with pytest.raises(ValidationError): observation(expires_at=NOW)


def test_legacy_projection_is_read_only_and_uncertain(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError("projection attempted I/O")
    monkeypatch.setattr("builtins.open", forbidden)
    zero = CacheReplicaObservation.from_legacy_kv_ready(
        KBItem("kid", "path", "text", 4, kv_ready=0), artifact_id=artifact().artifact_id, endpoint_id=endpoint().endpoint_id, now=NOW)
    one = CacheReplicaObservation.from_legacy_kv_ready(
        {"kv_ready": 1, "kv_updated_at": int(NOW.timestamp()), "kv_rel_dir": "logical/dir", "kv_dumped_keys": 2},
        artifact_id=artifact().artifact_id, endpoint_id=endpoint().endpoint_id)
    assert zero.state is ObservationState.UNKNOWN
    assert one.state is ObservationState.AVAILABLE
    assert one.legacy_projection and one.compatibility_uncertain
    assert one.runtime_profile is RuntimeProfile.LEGACY and one.endpoint_generation == 0
    assert one.legacy_kv_rel_dir == "logical/dir" and one.legacy_kv_dumped_keys == 2
    with pytest.raises(ValueError): CacheReplicaObservation.from_legacy_kv_ready(
        {"kv_ready": "yes"}, artifact_id=artifact().artifact_id, endpoint_id=endpoint().endpoint_id)


OP_ALLOWED = {
    "pending": {"running", "cancelled"}, "running": {"succeeded", "retry_wait", "failed", "cancelled"},
    "retry_wait": {"running", "failed", "cancelled"}, "succeeded": set(), "failed": set(), "cancelled": set(),
}
QUEUE_ALLOWED = {
    "queued": {"claimed", "cancelled"}, "claimed": {"executing", "retry_wait", "cancelled"},
    "executing": {"completed", "retry_wait", "failed", "cancelled"},
    "retry_wait": {"queued", "failed", "cancelled"}, "completed": set(), "failed": set(), "cancelled": set(),
}


@pytest.mark.parametrize("current", OP_ALLOWED)
@pytest.mark.parametrize("requested", OP_ALLOWED)
def test_all_operation_transitions(current, requested):
    obj = task(state=current)
    if current == requested: assert obj.transition(requested) is obj
    elif requested in OP_ALLOWED[current]: assert obj.transition(requested).state.value == requested
    else:
        with pytest.raises(StateTransitionError) as exc: obj.transition(requested)
        assert exc.value.to_dict()["error"] == "invalid_state_transition"


@pytest.mark.parametrize("current", QUEUE_ALLOWED)
@pytest.mark.parametrize("requested", QUEUE_ALLOWED)
def test_all_queue_transitions(current, requested):
    obj = work(state=current)
    if current == requested: assert obj.transition(requested) is obj
    elif requested in QUEUE_ALLOWED[current]: assert obj.transition(requested).state.value == requested
    else:
        with pytest.raises(StateTransitionError): obj.transition(requested)


def test_terminal_retryable_and_time_validation():
    for state in CacheOperationState: assert not (state.terminal and state.retryable)
    for state in QueueState: assert not (state.terminal and state.retryable)
    with pytest.raises(ValueError): task().transition("running", at=NOW - timedelta(seconds=1))
    with pytest.raises(ValidationError): work(updated_at=NOW - timedelta(seconds=1))


def test_v1_write_cannot_use_legacy_gateway():
    for operation in ("prefetch", "pin", "unpin", "clear", "rebuild"):
        with pytest.raises(ValidationError, match="legacy_gateway"): task(operation=operation, gateway_profile="legacy_gateway")
    assert task(operation="lookup", gateway_profile="legacy_gateway")
    assert task(operation="observe", gateway_profile="legacy_gateway")


def test_validated_model_copy_and_round_trips():
    models = [artifact(), endpoint(), observation(), task(), work()]
    for model in models: assert type(model).model_validate_json(model.to_json()) == model
    with pytest.raises(ValidationError): artifact().model_copy(update={"runtime_profile": "auto"})
    with pytest.raises(ValidationError): artifact().model_copy(update={"artifact_id": "artifact_" + "0" * 32})
    with pytest.raises(ValidationError): task().model_copy(update={"task_id": "bad"})


@pytest.mark.parametrize("factory", [artifact, endpoint, observation, task, work])
@pytest.mark.parametrize("field", ["password", "credential", "redis_key", "kv_bytes", "device_pointer", "chunk_index"])
def test_forbidden_extra_fields_every_model(factory, field):
    with pytest.raises(ValidationError): factory(**{field: "forbidden"})
