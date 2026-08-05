import importlib.util
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.state_models import ArtifactState, ReplicaHealth, ReplicaState
from kdn_server.legacy_state import map_legacy_kv_state
_spec = importlib.util.spec_from_file_location("proxy_queue_knowledge", Path(__file__).parents[1] / "proxy/queue/knowledge.py")
_knowledge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_knowledge)
classify_kdn_items = _knowledge.classify_kdn_items


def row(kid="kid", kv_ready=1, kv_rel_dir="kid"):
    return {"kid": kid, "kv_ready": kv_ready, "kv_rel_dir": kv_rel_dir}


def codes(view):
    return {warning.code for warning in view.warnings}


@pytest.mark.parametrize("ready,create,artifact,replica,health,warning", [
    (0, False, ArtifactState.PENDING, ReplicaState.PENDING, ReplicaHealth.UNKNOWN, None),
    (0, True, ArtifactState.STAGING, ReplicaState.STAGING, ReplicaHealth.UNKNOWN, "legacy_files_without_ready_confirmation"),
    (1, True, ArtifactState.READY, ReplicaState.READY, ReplicaHealth.HEALTHY, None),
    (1, False, ArtifactState.READY, ReplicaState.FAILED, ReplicaHealth.UNHEALTHY, "legacy_replica_directory_missing"),
])
def test_complete_filesystem_mapping(tmp_path, ready, create, artifact, replica, health, warning):
    if create:
        (tmp_path / "kid").mkdir()
    view = map_legacy_kv_state(row(kv_ready=ready), tmp_path)
    assert (view.artifact.state, view.replica.state, view.replica.health) == (artifact, replica, health)
    assert warning is None or warning in codes(view)


def test_ready_without_filesystem_check_has_unknown_health():
    view = map_legacy_kv_state(row(), None)
    assert view.artifact.state == ArtifactState.READY
    assert view.replica.state == ReplicaState.READY
    assert view.replica.health == ReplicaHealth.UNKNOWN


@pytest.mark.parametrize("value,expected", [(False, False), (0, False), ("0", False), (True, True), (1, True), ("1", True)])
def test_explicit_kv_ready_normalization(tmp_path, value, expected):
    view = map_legacy_kv_state(row(kv_ready=value), tmp_path)
    assert (view.artifact.state == ArtifactState.READY) is expected


@pytest.mark.parametrize("value", [None, "", "true", 2, -1, [], {}])
def test_invalid_kv_ready_rejected(tmp_path, value):
    with pytest.raises(ValueError, match="kv_ready"):
        map_legacy_kv_state(row(kv_ready=value), tmp_path)


def test_runtime_kid_is_authoritative_and_mismatch_warns(tmp_path):
    (tmp_path / "stale").mkdir()
    view = map_legacy_kv_state(row(kv_rel_dir="stale"), tmp_path)
    assert view.replica.state == ReplicaState.FAILED
    assert view.replica.location_key == "kid"
    assert "legacy_kv_rel_dir_mismatch" in codes(view)


def test_matching_metadata_has_no_mismatch_warning(tmp_path):
    (tmp_path / "kid").mkdir()
    assert "legacy_kv_rel_dir_mismatch" not in codes(map_legacy_kv_state(row(), tmp_path))


def test_sqlite_row_is_mapped_without_conversion_or_mutation(tmp_path):
    (tmp_path / "kid").mkdir()
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE legacy (kid TEXT, kv_ready INTEGER, kv_rel_dir TEXT)")
    connection.execute("INSERT INTO legacy VALUES (?, ?, ?)", ("kid", 1, "kid"))
    sqlite_row = connection.execute("SELECT kid, kv_ready, kv_rel_dir FROM legacy").fetchone()
    view = map_legacy_kv_state(sqlite_row, tmp_path)
    assert view.artifact.knowledge_id == "kid"
    assert view.artifact.state == ArtifactState.READY
    assert view.replica.state == ReplicaState.READY
    assert view.replica.health == ReplicaHealth.HEALTHY
    assert view.replica.location_key == "kid"
    assert view.artifact.artifact_id and view.replica.replica_id
    assert codes(view) == set()
    assert connection.execute("SELECT COUNT(*) FROM legacy").fetchone()[0] == 1
    connection.close()


def test_dot_cannot_make_root_healthy(tmp_path):
    view = map_legacy_kv_state(row(kv_rel_dir="."), tmp_path)
    assert view.replica.state == ReplicaState.FAILED
    assert "legacy_kv_rel_dir_mismatch" in codes(view)


@pytest.mark.parametrize("field,value", [("kid", "../outside"), ("kv_rel_dir", "../outside")])
def test_escaped_paths_rejected(tmp_path, field, value):
    data = row()
    data[field] = value
    with pytest.raises(ValueError, match=field):
        map_legacy_kv_state(data, tmp_path)


def test_ids_are_stable_and_projection_is_deeply_frozen(tmp_path):
    first, second = map_legacy_kv_state(row(), tmp_path), map_legacy_kv_state(row(), tmp_path)
    assert first.artifact.artifact_id == second.artifact.artifact_id
    assert first.replica.replica_id == second.replica.replica_id
    assert first.source == "legacy_kv_ready" and first.compatibility_status == "unknown"
    with pytest.raises(ValidationError, match="Instance is frozen"):
        first.compatibility_status = "compatible"
    with pytest.raises(ValidationError, match="Instance is frozen"):
        first.replica.state = ReplicaState.READY


def test_mapping_does_not_write(tmp_path):
    marker = tmp_path / "marker"
    marker.write_bytes(b"unchanged")
    before = [(path.name, path.stat().st_mtime_ns, path.read_bytes()) for path in tmp_path.iterdir()]
    map_legacy_kv_state(row(), tmp_path)
    after = [(path.name, path.stat().st_mtime_ns, path.read_bytes()) for path in tmp_path.iterdir()]
    assert after == before


def test_existing_proxy_classification_is_unchanged():
    items = [{"kid": "ready", "kv_ready": 1}, {"kid": "text", "kv_ready": 0}]
    result = classify_kdn_items(["ready", "text", "miss"], items, ["miss"])
    assert [item["kid"] for item in result["kv_ready_items"]] == ["ready"]
    assert [item["kid"] for item in result["text_only_items"]] == ["text"]
    assert result["miss_ids"] == ["miss"]
