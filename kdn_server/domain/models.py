"""Compatibility forwarding imports for canonical CacheRoute domain state."""

from cacheroute.cache import (
    CacheArtifact,
    CacheOperationState,
    CacheOperationTask,
    CacheOperationType,
    CacheReplicaObservation,
    ObservationConfidence,
    ObservationSource,
    ObservationState,
)
from cacheroute.routing import QueueState, QueueWork
from cacheroute.runtime import RuntimeProfile, Snapshot, StateTransitionError, StrEnum
from cacheroute.topology import LMCacheEndpoint, LMCacheGatewayProfile

__all__ = [
    "CacheArtifact", "CacheOperationState", "CacheOperationTask", "CacheOperationType",
    "CacheReplicaObservation", "LMCacheEndpoint", "LMCacheGatewayProfile",
    "ObservationConfidence", "ObservationSource", "ObservationState", "QueueState",
    "QueueWork", "RuntimeProfile", "Snapshot", "StateTransitionError", "StrEnum",
]
