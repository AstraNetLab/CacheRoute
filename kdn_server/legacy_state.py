"""Read-only projection of Legacy ``kv_ready`` rows onto lifecycle models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from core.state_models import (
    ArtifactState, CacheArtifact, CacheReplica, ReplicaState, artifact_id, replica_id,
)


class LegacyStateWarning(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    message: str


class LegacyKVStateView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    compatibility_status: str = "unknown"
    artifact: CacheArtifact
    replica: CacheReplica
    replica_directory_exists: bool
    warnings: tuple[LegacyStateWarning, ...] = ()


def _safe_component(value: Any, field: str, *, allow_dot: bool = False) -> str:
    component = str(value or "").strip()
    if component == "." and allow_dot:
        return component
    path = Path(component)
    if not component or component == ".." or (component == "." and not allow_dot) or path.is_absolute() or len(path.parts) != 1:
        raise ValueError(f"{field} must be a non-empty single path component")
    return component


def map_legacy_kv_state(row: Any, kv_root: str | Path) -> LegacyKVStateView:
    """Map a Legacy database row without mutating either storage or the filesystem."""
    get = row.get if hasattr(row, "get") else lambda key, default=None: getattr(row, key, default)
    kid = _safe_component(get("kid"), "kid")
    raw_rel_dir = get("kv_rel_dir")
    rel_dir = None
    if raw_rel_dir is not None and str(raw_rel_dir).strip():
        rel_dir = _safe_component(raw_rel_dir, "kv_rel_dir", allow_dot=True)

    root = Path(kv_root).resolve(strict=False)
    runtime_directory = (root / kid).resolve(strict=False)
    if runtime_directory.parent != root:
        raise ValueError("kid escapes the configured KV root")
    directory_exists = runtime_directory.is_dir()
    kv_ready = bool(get("kv_ready", False))
    artifact_state = ArtifactState.READY if kv_ready else ArtifactState.PENDING
    replica_state = ReplicaState.READY if kv_ready and directory_exists else ReplicaState.FAILED
    artifact = CacheArtifact(artifact_id=artifact_id(kid), kid=kid, state=artifact_state)
    replica = CacheReplica(
        replica_id=replica_id(artifact.artifact_id, kid), artifact_id=artifact.artifact_id,
        location_key=kid, state=replica_state,
    )
    warnings = ()
    if rel_dir is not None and rel_dir != kid:
        warnings = (LegacyStateWarning(
            code="legacy_kv_rel_dir_mismatch",
            message="Legacy kv_rel_dir differs from the runtime kid directory.",
        ),)
    return LegacyKVStateView(
        artifact=artifact, replica=replica, replica_directory_exists=directory_exists,
        warnings=warnings,
    )
