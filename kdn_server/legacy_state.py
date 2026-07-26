"""Read-only projection of Legacy ``kv_ready`` rows onto lifecycle models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict

from core.state_models import (
    ArtifactState, CacheArtifact, CacheReplica, ReplicaHealth, ReplicaState,
    legacy_artifact_id, replica_id,
)


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    """Read dictionaries, sqlite3.Row objects, and attribute-backed records safely."""
    getter = getattr(row, "get", None)
    if callable(getter):
        return getter(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


class LegacyStateWarning(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    message: str


class LegacyKVStateView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: Literal["legacy_kv_ready"] = "legacy_kv_ready"
    compatibility_status: Literal["unknown"] = "unknown"
    artifact: CacheArtifact
    replica: CacheReplica
    warnings: Tuple[LegacyStateWarning, ...] = ()


def _safe_component(value: Any, field: str, *, allow_dot: bool = False) -> str:
    component = str(value or "").strip()
    if component == "." and allow_dot:
        return component
    path = Path(component)
    if not component or component in {".", ".."} or path.is_absolute() or len(path.parts) != 1:
        raise ValueError(f"{field} must be a non-empty single path component")
    return component


def _normalize_kv_ready(value: Any) -> bool:
    if value is False or (type(value) is int and value == 0) or (type(value) is str and value == "0"):
        return False
    if value is True or (type(value) is int and value == 1) or (type(value) is str and value == "1"):
        return True
    raise ValueError("kv_ready must be one of False, 0, '0', True, 1, or '1'")


def map_legacy_kv_state(row: Any, kv_root: Optional[str | Path] = None) -> LegacyKVStateView:
    """Map a Legacy row without changing SQLite or the filesystem.

    Passing ``kv_root=None`` explicitly means that no filesystem check was performed.
    """
    kid = _safe_component(_row_value(row, "kid"), "kid")
    ready = _normalize_kv_ready(_row_value(row, "kv_ready", 0))
    raw_rel_dir = _row_value(row, "kv_rel_dir")
    rel_dir = None
    if raw_rel_dir is not None and str(raw_rel_dir).strip():
        rel_dir = _safe_component(raw_rel_dir, "kv_rel_dir", allow_dot=True)

    exists: Optional[bool] = None
    if kv_root is not None:
        root = Path(kv_root).resolve(strict=False)
        runtime_directory = (root / kid).resolve(strict=False)
        if runtime_directory.parent != root:
            raise ValueError("kid escapes the configured KV root")
        exists = runtime_directory.is_dir()

    warnings = []
    if rel_dir is not None and rel_dir != kid:
        warnings.append(LegacyStateWarning(
            code="legacy_kv_rel_dir_mismatch",
            message="Legacy kv_rel_dir differs from the runtime kid directory.",
        ))

    if ready:
        artifact_state = ArtifactState.READY
        if exists is False:
            replica_state, health = ReplicaState.FAILED, ReplicaHealth.UNHEALTHY
            warnings.append(LegacyStateWarning(
                code="legacy_replica_directory_missing",
                message="Legacy kv_ready is set but the runtime kid directory is missing.",
            ))
        else:
            replica_state = ReplicaState.READY
            health = ReplicaHealth.HEALTHY if exists is True else ReplicaHealth.UNKNOWN
    elif exists is True:
        artifact_state, replica_state = ArtifactState.STAGING, ReplicaState.STAGING
        health = ReplicaHealth.UNKNOWN
        warnings.append(LegacyStateWarning(
            code="legacy_files_without_ready_confirmation",
            message="Runtime kid directory exists without Legacy kv_ready confirmation.",
        ))
    else:
        artifact_state, replica_state, health = (
            ArtifactState.PENDING, ReplicaState.PENDING, ReplicaHealth.UNKNOWN,
        )

    artifact_identifier = legacy_artifact_id(kid)
    artifact = CacheArtifact(
        artifact_id=artifact_identifier, knowledge_id=kid,
        capability_fingerprint=None, state=artifact_state,
    )
    replica = CacheReplica(
        replica_id=replica_id(artifact_identifier, location_key=kid),
        artifact_id=artifact_identifier, location_key=kid,
        state=replica_state, health=health,
    )
    return LegacyKVStateView(artifact=artifact, replica=replica, warnings=tuple(warnings))
