import pytest
from pydantic import ValidationError

from core.state_models import (
    ArtifactState, CacheArtifact, CacheReplica, DataPlaneTask, DataPlaneTaskState,
    InvalidStateTransition, QueueWork, QueueWorkState, ReplicaState,
)


@pytest.mark.parametrize("model,target", [
    (CacheArtifact(artifact_id="a", kid="kid"), ArtifactState.READY),
    (CacheReplica(replica_id="r", artifact_id="a", location_key="kid"), ReplicaState.READY),
    (DataPlaneTask(task_id="t"), DataPlaneTaskState.RUNNING),
    (QueueWork(work_id="w"), QueueWorkState.RUNNING),
])
def test_lifecycle_state_is_frozen(model, target):
    with pytest.raises(ValidationError, match="Instance is frozen"):
        model.state = target


def test_legal_transition_returns_changed_copy_without_mutating_source():
    source = CacheArtifact(artifact_id="a", kid="kid")
    building, result = source.transition_to(ArtifactState.BUILDING)
    assert source.state == ArtifactState.PENDING
    assert building.state == ArtifactState.BUILDING
    assert result.changed is True


def test_same_state_transition_is_idempotent():
    source = DataPlaneTask(task_id="t")
    unchanged, result = source.transition_to(DataPlaneTaskState.PENDING)
    assert unchanged is source
    assert result.changed is False


def test_terminal_transition_has_structured_sorted_detail():
    source = QueueWork(work_id="w", state=QueueWorkState.SUCCEEDED)
    with pytest.raises(InvalidStateTransition) as caught:
        source.transition_to(QueueWorkState.RUNNING)
    assert caught.value.detail == {
        "code": "invalid_state_transition", "current_state": "succeeded",
        "target_state": "running", "allowed_targets": [],
    }
