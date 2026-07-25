import re

import pytest
from pydantic import ValidationError

from core.state_models import (
    ArtifactState, CacheArtifact, CacheReplica, DataPlaneTask, DataPlaneTaskState,
    InvalidStateTransition, QueueWork, QueueWorkState, ReplicaHealth, ReplicaState,
    StateTransitionDetail, allowed_target_states, generate_artifact_id,
    generate_data_plane_task_id, generate_queue_work_id, generate_replica_id,
    is_retryable_state, is_terminal_state,
)


ENUM_VALUES = [
    (ArtifactState, ["pending", "building", "staging", "ready", "failed", "deleting", "deleted"]),
    (ReplicaState, ["pending", "staging", "ready", "failed", "evicting", "deleted"]),
    (ReplicaHealth, ["unknown", "healthy", "degraded", "unhealthy"]),
    (DataPlaneTaskState, ["pending", "queued", "leased", "running", "succeeded", "failed", "cancelled", "expired"]),
    (QueueWorkState, ["pending", "blocked", "ready", "queued", "running", "succeeded", "failed", "cancelled", "skipped"]),
]


@pytest.mark.parametrize("enum_type,values", ENUM_VALUES)
def test_exact_enum_values(enum_type, values):
    assert [item.value for item in enum_type] == values
    with pytest.raises(ValueError):
        enum_type("future_value")


def _models():
    aid = generate_artifact_id("kid", "sha256:cap")
    rid = generate_replica_id(aid, "plane", "file", "kid")
    return [
        CacheArtifact(artifact_id=aid, knowledge_id="kid"),
        CacheReplica(replica_id=rid, artifact_id=aid), DataPlaneTask(), QueueWork(),
    ]


@pytest.mark.parametrize("index", range(4))
def test_json_round_trip_and_forbid_extra(index):
    model = _models()[index]
    assert type(model).model_validate_json(model.model_dump_json()) == model
    with pytest.raises(ValidationError):
        type(model).model_validate({**model.model_dump(), "unexpected": True})


def test_unknown_state_is_rejected_and_mutable_defaults_are_independent():
    with pytest.raises(ValidationError):
        DataPlaneTask(state="not_a_state")
    left = StateTransitionDetail(entity_type="x", entity_id="1", current_state="a", target_state="b", reason="x", terminal=False, retryable=False)
    right = StateTransitionDetail(entity_type="x", entity_id="2", current_state="a", target_state="b", reason="x", terminal=False, retryable=False)
    left.allowed_targets.append("c")
    assert right.allowed_targets == []


def test_stable_artifact_ids_and_canonical_inputs():
    first = generate_artifact_id(" KID ", "sha256:cap", "variant")
    assert first == generate_artifact_id("kid", "sha256:cap", "variant")
    assert re.fullmatch(r"artifact:sha256:[0-9a-f]{64}", first)
    assert first != generate_artifact_id("other", "sha256:cap", "variant")
    assert first != generate_artifact_id("kid", "sha256:other", "variant")
    assert first != generate_artifact_id("kid", "sha256:cap", "other")


def test_replica_ids_are_stable_and_sensitive_without_exposing_inputs():
    args = ("artifact:sha256:" + "a" * 64, "plane", "file", "opaque-location")
    replica_id = generate_replica_id(*args)
    assert replica_id == generate_replica_id(*args)
    assert re.fullmatch(r"replica:sha256:[0-9a-f]{64}", replica_id)
    for changed in [
        (args[0], "other-plane", args[2], args[3]), (args[0], args[1], "redis", args[3]),
        (args[0], args[1], args[2], "other-location"),
    ]:
        assert replica_id != generate_replica_id(*changed)
    secret = "redis://user:password@example/key"
    with pytest.raises(ValueError, match="opaque, non-secret"):
        generate_replica_id(args[0], "plane", "redis", secret)
    with pytest.raises(ValidationError, match="opaque, non-secret"):
        CacheReplica(replica_id=replica_id, artifact_id=args[0], location_key=secret)


def test_generated_and_restored_execution_ids():
    task_ids = {generate_data_plane_task_id() for _ in range(10)}
    work_ids = {generate_queue_work_id() for _ in range(10)}
    assert len(task_ids) == len(work_ids) == 10
    assert all(re.fullmatch(r"dpt:[0-9a-f]{32}", item) for item in task_ids)
    assert all(re.fullmatch(r"qwork:[0-9a-f]{32}", item) for item in work_ids)
    assert DataPlaneTask(task_id="restored-task").task_id == "restored-task"
    assert QueueWork(work_id="restored-work").work_id == "restored-work"
    with pytest.raises(ValidationError): DataPlaneTask(task_id=" ")
    with pytest.raises(ValidationError): QueueWork(work_id="")


TRANSITIONS = [
    (CacheArtifact, ArtifactState, {"pending": "building failed deleting", "building": "staging failed deleting", "staging": "ready failed deleting", "ready": "building failed deleting", "failed": "building deleting", "deleting": "deleted failed"}),
    (CacheReplica, ReplicaState, {"pending": "staging failed evicting", "staging": "ready failed evicting", "ready": "staging failed evicting", "failed": "staging evicting", "evicting": "deleted failed"}),
    (DataPlaneTask, DataPlaneTaskState, {"pending": "queued cancelled", "queued": "leased running cancelled expired", "leased": "running queued cancelled expired", "running": "succeeded failed cancelled", "failed": "queued cancelled"}),
    (QueueWork, QueueWorkState, {"pending": "blocked ready cancelled skipped", "blocked": "ready cancelled skipped", "ready": "queued running cancelled skipped", "queued": "running cancelled", "running": "succeeded failed cancelled", "failed": "ready cancelled skipped"}),
]


def _make(model_type, state):
    aid = generate_artifact_id("kid", None)
    if model_type is CacheArtifact: return model_type(artifact_id=aid, knowledge_id="kid", state=state)
    if model_type is CacheReplica: return model_type(replica_id="replica", artifact_id=aid, state=state)
    return model_type(state=state)


@pytest.mark.parametrize("model_type,enum_type,mapping", TRANSITIONS)
def test_every_allowed_transition_and_same_state(model_type, enum_type, mapping):
    for source, targets in mapping.items():
        model = _make(model_type, enum_type(source))
        for target in targets.split():
            changed, result = model.transition_to(enum_type(target))
            assert changed.state == enum_type(target) and result.changed
            assert model.state == enum_type(source)
        same, result = model.transition_to(enum_type(source))
        assert same.state == model.state and not result.changed
        assert [item.value for item in allowed_target_states(enum_type(source))] == sorted(targets.split())


@pytest.mark.parametrize("model_type,enum_type,mapping", TRANSITIONS)
def test_invalid_and_terminal_transition_details(model_type, enum_type, mapping):
    source = next(iter(mapping))
    invalid = next(item for item in enum_type if item.value != source and item.value not in mapping[source].split())
    with pytest.raises(InvalidStateTransition) as caught:
        _make(model_type, enum_type(source)).transition_to(invalid)
    assert caught.value.detail.code == "invalid_state_transition"
    assert caught.value.detail.reason == "transition_not_allowed"
    assert caught.value.detail.allowed_targets == sorted(mapping[source].split())
    terminal = next(item for item in enum_type if is_terminal_state(item))
    target = next(item for item in enum_type if item != terminal)
    with pytest.raises(InvalidStateTransition) as terminal_error:
        _make(model_type, terminal).transition_to(target)
    assert terminal_error.value.detail.reason == "terminal_state"
    assert terminal_error.value.detail.terminal is True


def test_terminal_and_retryable_traits():
    expected_terminal = {ArtifactState.DELETED, ReplicaState.DELETED, DataPlaneTaskState.SUCCEEDED, DataPlaneTaskState.CANCELLED, DataPlaneTaskState.EXPIRED, QueueWorkState.SUCCEEDED, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED}
    expected_retryable = {ArtifactState.FAILED, ReplicaState.FAILED, DataPlaneTaskState.FAILED, QueueWorkState.FAILED}
    for enum_type in (ArtifactState, ReplicaState, DataPlaneTaskState, QueueWorkState):
        for state in enum_type:
            assert is_terminal_state(state) == (state in expected_terminal)
            assert is_retryable_state(state) == (state in expected_retryable)
    assert all(not is_terminal_state(state) for state in expected_retryable)
