from pathlib import Path

import pytest
from pydantic import ValidationError

from core.state_models import ReplicaState
from kdn_server.legacy_state import map_legacy_kv_state


def row(kid="kid", kv_rel_dir="kid"):
    return {"kid": kid, "kv_ready": 1, "kv_rel_dir": kv_rel_dir}


def warning_codes(view):
    return {warning.code for warning in view.warnings}


def test_runtime_kid_directory_is_healthy_and_matching_metadata_has_no_warning(tmp_path):
    (tmp_path / "kid").mkdir()
    view = map_legacy_kv_state(row(), tmp_path)
    assert view.replica.state == ReplicaState.READY
    assert view.replica_directory_exists is True
    assert view.replica.location_key == "kid"
    assert "legacy_kv_rel_dir_mismatch" not in warning_codes(view)


def test_stale_existing_metadata_directory_does_not_make_replica_healthy(tmp_path):
    (tmp_path / "stale").mkdir()
    view = map_legacy_kv_state(row(kv_rel_dir="stale"), tmp_path)
    assert view.replica.state == ReplicaState.FAILED
    assert view.replica_directory_exists is False
    assert "legacy_kv_rel_dir_mismatch" in warning_codes(view)


def test_dot_metadata_does_not_treat_root_as_replica(tmp_path):
    view = map_legacy_kv_state(row(kv_rel_dir="."), tmp_path)
    assert view.replica.state == ReplicaState.FAILED
    assert view.replica_directory_exists is False
    assert "legacy_kv_rel_dir_mismatch" in warning_codes(view)


def test_escaping_metadata_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="kv_rel_dir"):
        map_legacy_kv_state(row(kv_rel_dir="../outside"), tmp_path)


def test_projection_and_nested_models_are_frozen(tmp_path):
    (tmp_path / "kid").mkdir()
    view = map_legacy_kv_state(row(kv_rel_dir="other"), tmp_path)
    with pytest.raises(ValidationError, match="Instance is frozen"):
        view.compatibility_status = "compatible"
    with pytest.raises(ValidationError, match="Instance is frozen"):
        view.replica.state = ReplicaState.FAILED
    with pytest.raises(ValidationError, match="Instance is frozen"):
        view.warnings[0].code = "changed"


def test_mapping_does_not_create_or_modify_files(tmp_path):
    marker = tmp_path / "marker"
    marker.write_text("unchanged")
    before = {path.relative_to(tmp_path): (path.stat().st_mtime_ns, path.read_bytes())
              for path in tmp_path.iterdir() if path.is_file()}
    map_legacy_kv_state(row(), tmp_path)
    after = {path.relative_to(tmp_path): (path.stat().st_mtime_ns, path.read_bytes())
             for path in tmp_path.iterdir() if path.is_file()}
    assert after == before
