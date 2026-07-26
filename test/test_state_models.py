import re

import pytest
from pydantic import ValidationError

from core.state_models import (
    ARTIFACT_TRANSITIONS, REPLICA_TRANSITIONS, TASK_TRANSITIONS, WORK_TRANSITIONS,
    ArtifactState, CacheArtifact, CacheReplica, DataPlaneTask, DataPlaneTaskState,
    InvalidStateTransition, QueueWork, QueueWorkState, ReplicaHealth, ReplicaState,
    allowed_target_states, artifact_id, is_retryable_state, is_terminal_state, replica_id,
)


ENUM_VALUES = {
    ArtifactState: ["pending", "building", "staging", "ready", "failed", "deleting", "deleted"],
    ReplicaState: ["pending", "staging", "ready", "failed", "evicting", "deleted"],
    ReplicaHealth: ["unknown", "healthy", "degraded", "unhealthy"],
    DataPlaneTaskState: ["pending", "queued", "leased", "running", "succeeded", "failed", "cancelled", "expired"],
    QueueWorkState: ["pending", "blocked", "ready", "queued", "running", "succeeded", "failed", "cancelled", "skipped"],
}


def artifact(state=ArtifactState.PENDING):
    return CacheArtifact(artifact_id="artifact:restored", knowledge_id="kid", state=state)


def replica(state=ReplicaState.PENDING):
    return CacheReplica(replica_id="replica:restored", artifact_id="artifact:restored", state=state)


def test_exact_enum_wire_values():
    for enum_type, values in ENUM_VALUES.items():
        assert [item.value for item in enum_type] == values


@pytest.mark.parametrize("model", [artifact(), replica(), DataPlaneTask(), QueueWork()])
def test_json_round_trip(model):
    assert type(model).model_validate_json(model.model_dump_json()) == model


def test_unknown_enum_and_extra_field_rejected():
    with pytest.raises(ValidationError):
        artifact().model_copy(update={"state": "unknown"}).model_validate(
            {**artifact().model_dump(), "state": "unknown"})
    with pytest.raises(ValidationError, match="Extra inputs"):
        CacheArtifact(artifact_id="a", knowledge_id="k", unexpected=True)


@pytest.mark.parametrize("model,target", [
    (artifact(), ArtifactState.READY), (replica(), ReplicaState.READY),
    (DataPlaneTask(), DataPlaneTaskState.RUNNING), (QueueWork(), QueueWorkState.RUNNING),
])
def test_lifecycle_models_are_frozen(model, target):
    with pytest.raises(ValidationError, match="Instance is frozen"):
        model.state = target


@pytest.mark.parametrize("factory,table", [
    (artifact, ARTIFACT_TRANSITIONS), (replica, REPLICA_TRANSITIONS),
    (lambda state: DataPlaneTask(task_id="task", state=state), TASK_TRANSITIONS),
    (lambda state: QueueWork(work_id="work", state=state), WORK_TRANSITIONS),
])
def test_every_declared_transition_and_same_state(factory, table):
    for source_state, targets in table.items():
        source = factory(source_state)
        unchanged, result = source.transition_to(source_state)
        assert unchanged is source and result.changed is False
        for target in targets:
            changed, result = source.transition_to(target)
            assert source.state == source_state
            assert changed.state == target and result.changed is True


def test_invalid_terminal_and_cross_enum_transition_details():
    with pytest.raises(InvalidStateTransition) as terminal:
        artifact(ArtifactState.DELETED).transition_to(ArtifactState.PENDING)
    assert terminal.value.detail.reason == "terminal_state"
    assert terminal.value.detail.terminal is True
    assert terminal.value.detail.allowed_targets == ()
    with pytest.raises(InvalidStateTransition) as cross_enum:
        artifact().transition_to(ReplicaState.STAGING)
    assert cross_enum.value.detail.reason == "transition_not_allowed"
    assert cross_enum.value.detail.target_state == "staging"


def test_allowed_targets_are_sorted_and_traits_are_centralized():
    for enum_type, values in ENUM_VALUES.items():
        if enum_type is ReplicaHealth:
            continue
        for state in enum_type:
            assert [item.value for item in allowed_target_states(state)] == sorted(item.value for item in allowed_target_states(state))
            assert is_retryable_state(state) is (state.value == "failed")
    assert is_terminal_state(ArtifactState.DELETED)
    assert is_terminal_state(ReplicaState.DELETED)
    for state in (DataPlaneTaskState.SUCCEEDED, DataPlaneTaskState.CANCELLED, DataPlaneTaskState.EXPIRED,
                  QueueWorkState.SUCCEEDED, QueueWorkState.CANCELLED, QueueWorkState.SKIPPED):
        assert is_terminal_state(state)
    assert not is_terminal_state(ArtifactState.FAILED)


def test_stable_artifact_and_replica_ids_include_all_identity_inputs():
    first = artifact_id(" kid ", "cap", "variant")
    assert first == artifact_id("kid", "cap", "variant")
    assert re.fullmatch(r"artifact:sha256:[0-9a-f]{64}", first)
    assert first != artifact_id("kid", "other", "variant")
    base = replica_id(first, "plane", "disk", "location")
    assert re.fullmatch(r"replica:sha256:[0-9a-f]{64}", base)
    assert len({base, replica_id(first, "other", "disk", "location"),
                replica_id(first, "plane", "other", "location"),
                replica_id(first, "plane", "disk", "other"),
                replica_id(artifact_id("other"), "plane", "disk", "location")}) == 5


def test_generated_and_restored_ids_and_empty_rejection():
    tasks = {DataPlaneTask().task_id for _ in range(3)}
    works = {QueueWork().work_id for _ in range(3)}
    assert len(tasks) == 3 and all(re.fullmatch(r"dpt:[0-9a-f]{32}", item) for item in tasks)
    assert len(works) == 3 and all(re.fullmatch(r"qwork:[0-9a-f]{32}", item) for item in works)
    assert DataPlaneTask(task_id="restored").task_id == "restored"
    assert QueueWork(work_id="restored").work_id == "restored"
    for constructor, kwargs in [(DataPlaneTask, {"task_id": ""}), (QueueWork, {"work_id": ""}),
                                (CacheArtifact, {"artifact_id": "", "knowledge_id": "kid"}),
                                (CacheReplica, {"replica_id": "", "artifact_id": "a"})]:
        with pytest.raises(ValidationError):
            constructor(**kwargs)


def test_model_defaults_are_independent():
    assert DataPlaneTask().model_dump() is not DataPlaneTask().model_dump()
