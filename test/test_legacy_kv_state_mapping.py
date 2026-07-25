import pytest

from core.state_models import ArtifactState, ReplicaHealth, ReplicaState
from kdn_server.legacy_state import map_legacy_kv_state, map_legacy_kv_state_from_filesystem
from proxy.queue.knowledge import classify_kdn_items


@pytest.mark.parametrize("value", [False, 0, "0"])
def test_not_ready_without_directory(value):
    view = map_legacy_kv_state(kid="KID", kv_ready=value, kv_rel_dir="KID", kv_dumped_keys=None, kv_updated_at=None, replica_directory_exists=False)
    assert (view.artifact.state, view.replica.state, view.replica.health) == (ArtifactState.PENDING, ReplicaState.PENDING, ReplicaHealth.UNKNOWN)
    assert view.compatibility_status == "unknown" and view.artifact.capability_fingerprint is None


def test_not_ready_with_files_warns():
    view = map_legacy_kv_state(kid="kid", kv_ready=False, kv_rel_dir="kid", kv_dumped_keys=2, kv_updated_at=1, replica_directory_exists=True)
    assert (view.artifact.state, view.replica.state) == (ArtifactState.STAGING, ReplicaState.STAGING)
    assert view.warnings[0].code == "legacy_files_without_ready_confirmation"


@pytest.mark.parametrize("value", [True, 1, "1"])
def test_ready_with_directory(value):
    view = map_legacy_kv_state(kid="kid", kv_ready=value, kv_rel_dir="kid", kv_dumped_keys=2, kv_updated_at=1, replica_directory_exists=True)
    assert (view.artifact.state, view.replica.state, view.replica.health) == (ArtifactState.READY, ReplicaState.READY, ReplicaHealth.HEALTHY)


def test_ready_with_missing_directory_keeps_artifact_ready():
    view = map_legacy_kv_state(kid="kid", kv_ready=True, kv_rel_dir="kid", kv_dumped_keys=2, kv_updated_at=1, replica_directory_exists=False)
    assert view.artifact.state == ArtifactState.READY
    assert (view.replica.state, view.replica.health) == (ReplicaState.FAILED, ReplicaHealth.UNHEALTHY)
    assert view.warnings[0].code == "legacy_replica_directory_missing"


def test_ready_without_filesystem_check_has_unknown_health():
    view = map_legacy_kv_state(kid="kid", kv_ready=True, kv_rel_dir="kid", kv_dumped_keys=None, kv_updated_at=None, replica_directory_exists=None)
    assert (view.replica.state, view.replica.health) == (ReplicaState.READY, ReplicaHealth.UNKNOWN)


@pytest.mark.parametrize("value", [2, -1, "false", "true", "", None, object()])
def test_invalid_ready_values_fail(value):
    with pytest.raises(ValueError, match="kv_ready"):
        map_legacy_kv_state(kid="kid", kv_ready=value, kv_rel_dir="kid", kv_dumped_keys=None, kv_updated_at=None, replica_directory_exists=None)


def test_filesystem_wrapper_and_escape_rejection(tmp_path):
    (tmp_path / "kid").mkdir()
    view = map_legacy_kv_state_from_filesystem(kv_root=tmp_path, kid="kid", kv_ready=1, kv_rel_dir="kid", kv_dumped_keys=1, kv_updated_at=1)
    assert view.replica.health == ReplicaHealth.HEALTHY
    with pytest.raises(ValueError, match="escapes"):
        map_legacy_kv_state_from_filesystem(kv_root=tmp_path, kid="kid", kv_ready=1, kv_rel_dir="../outside", kv_dumped_keys=1, kv_updated_at=1)


def test_mapping_ids_are_stable_and_mapper_does_not_write(tmp_path):
    kwargs = dict(kv_root=tmp_path, kid="kid", kv_ready=0, kv_rel_dir="kid", kv_dumped_keys=None, kv_updated_at=None)
    first, second = map_legacy_kv_state_from_filesystem(**kwargs), map_legacy_kv_state_from_filesystem(**kwargs)
    assert first.artifact.artifact_id == second.artifact.artifact_id
    assert first.replica.replica_id == second.replica.replica_id
    assert list(tmp_path.iterdir()) == []


def test_existing_proxy_classification_is_unchanged():
    result = classify_kdn_items(["ready", "text", "missing"], [{"id": "ready", "kv_ready": 1}, {"id": "text", "kv_ready": 0}], ["missing"])
    assert [item["id"] for item in result["kv_ready_items"]] == ["ready"]
    assert [item["id"] for item in result["text_only_items"]] == ["text"]
    assert result["miss_ids"] == ["missing"]
