"""Read-only compatibility views for legacy ``kv_ready`` metadata."""
from __future__ import annotations

from pathlib import Path
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from core.state_models import (
    ArtifactState, CacheArtifact, CacheReplica, ReplicaHealth, ReplicaState,
    generate_legacy_artifact_id, generate_replica_id,
)


class LegacyStateWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str


class LegacyKVStateView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["legacy_kv_ready"] = "legacy_kv_ready"
    compatibility_status: Literal["unknown"] = "unknown"
    artifact: CacheArtifact
    replica: CacheReplica
    warnings: List[LegacyStateWarning] = Field(default_factory=list)


def normalize_legacy_kv_ready(value: Union[bool, int, str]) -> bool:
    """Normalize SQLite-compatible legacy values without Python truthiness."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return value == 1
    if isinstance(value, str) and value.strip() in ("0", "1"):
        return value.strip() == "1"
    raise ValueError("kv_ready must be bool, integer 0/1, or string '0'/'1'")


def map_legacy_kv_state(
    *, kid: str, kv_ready: Union[bool, int, str], kv_rel_dir: Optional[str],
    kv_dumped_keys: Optional[int], kv_updated_at: Optional[int],
    replica_directory_exists: Optional[bool],
) -> LegacyKVStateView:
    """Purely derive lifecycle state; legacy timing/count fields remain unchanged."""
    del kv_dumped_keys, kv_updated_at  # Inputs are accepted but do not imply lifecycle state.
    normalized_kid = (kid or "").strip().lower()
    if not normalized_kid:
        raise ValueError("kid must not be empty")
    ready = normalize_legacy_kv_ready(kv_ready)
    location_key = (kv_rel_dir or normalized_kid).strip()
    if not location_key:
        raise ValueError("kv_rel_dir must not be empty when provided")

    warnings: List[LegacyStateWarning] = []
    if ready:
        artifact_state = ArtifactState.READY
        if replica_directory_exists is False:
            replica_state, health = ReplicaState.FAILED, ReplicaHealth.UNHEALTHY
            warnings.append(LegacyStateWarning(
                code="legacy_replica_directory_missing",
                message="Legacy metadata marks KV ready, but the replica directory is missing.",
            ))
        elif replica_directory_exists is True:
            replica_state, health = ReplicaState.READY, ReplicaHealth.HEALTHY
        else:
            replica_state, health = ReplicaState.READY, ReplicaHealth.UNKNOWN
    elif replica_directory_exists is True:
        artifact_state, replica_state, health = ArtifactState.STAGING, ReplicaState.STAGING, ReplicaHealth.UNKNOWN
        warnings.append(LegacyStateWarning(
            code="legacy_files_without_ready_confirmation",
            message="Legacy replica files exist without a KV-ready confirmation.",
        ))
    else:
        artifact_state, replica_state, health = ArtifactState.PENDING, ReplicaState.PENDING, ReplicaHealth.UNKNOWN

    artifact_id = generate_legacy_artifact_id(normalized_kid)
    replica_id = generate_replica_id(artifact_id, "legacy_kdn", "legacy_file", location_key)
    return LegacyKVStateView(
        artifact=CacheArtifact(
            artifact_id=artifact_id, knowledge_id=normalized_kid,
            capability_fingerprint=None, state=artifact_state,
        ),
        replica=CacheReplica(
            replica_id=replica_id, artifact_id=artifact_id, data_plane_id="legacy_kdn",
            backend_type="legacy_file", location_key=location_key,
            state=replica_state, health=health,
        ),
        warnings=warnings,
    )


def map_legacy_kv_state_from_filesystem(
    *, kv_root: Union[str, Path], kid: str, kv_ready: Union[bool, int, str],
    kv_rel_dir: Optional[str], kv_dumped_keys: Optional[int], kv_updated_at: Optional[int],
) -> LegacyKVStateView:
    """Resolve the legacy directory below ``kv_root`` and reject path escapes."""
    root = Path(kv_root).resolve()
    relative = kv_rel_dir or (kid or "").strip().lower()
    if not relative:
        raise ValueError("legacy replica location must not be empty")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("legacy replica location escapes the configured KV root") from exc
    return map_legacy_kv_state(
        kid=kid, kv_ready=kv_ready, kv_rel_dir=relative,
        kv_dumped_keys=kv_dumped_keys, kv_updated_at=kv_updated_at,
        replica_directory_exists=candidate.is_dir(),
    )
