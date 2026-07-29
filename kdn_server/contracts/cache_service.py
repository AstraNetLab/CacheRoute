"""Versioned Cache Service Facade contracts; no physical cache vocabulary."""
from pydantic import Field

from kdn_server.domain import CacheArtifact, CacheOperationTask, CacheReplicaObservation, LMCacheEndpoint, CacheOperationType
from .common import TokenInput, VersionedMessage
from .errors import ContractError, OutcomeCode


class ArtifactRequest(VersionedMessage): artifact_id: str = Field(pattern=r"^artifact_[0-9a-f]{32}$")
class GetCacheObservationRequest(ArtifactRequest): pass
class LookupArtifactRequest(ArtifactRequest): pass
class LookupTokensRequest(VersionedMessage): tokens: TokenInput

class OperationIntentRequest(ArtifactRequest):
    idempotency_key: str = Field(min_length=1)
    endpoint_id: str
    endpoint_generation: int = Field(ge=1)

class CreatePrefetchIntentRequest(OperationIntentRequest): pass
class CreatePinIntentRequest(OperationIntentRequest): pass
class CreateUnpinIntentRequest(OperationIntentRequest): pass
class CreateClearIntentRequest(OperationIntentRequest): pass
class CreateRebuildIntentRequest(OperationIntentRequest): pass
class GetOperationStatusRequest(VersionedMessage): task_id: str = Field(pattern=r"^cacheop_[0-9a-f]{32}$")
class CancelOperationRequest(GetOperationStatusRequest): pass
class GetLMCacheEndpointsRequest(VersionedMessage): pass
class GetTierAndAdapterSummaryRequest(VersionedMessage): pass
class GetMaintenanceStatusRequest(VersionedMessage): pass

class TokenCoverage(VersionedMessage):
    covered_ranges: tuple[tuple[int, int], ...] = ()
    total_tokens: int = Field(ge=0)

class CacheServiceResponse(VersionedMessage):
    outcome: OutcomeCode = OutcomeCode.SUCCESS
    artifact: CacheArtifact | None = None
    artifacts: tuple[CacheArtifact, ...] = ()
    observation: CacheReplicaObservation | None = None
    observations: tuple[CacheReplicaObservation, ...] = ()
    operation: CacheOperationTask | None = None
    endpoints: tuple[LMCacheEndpoint, ...] = ()
    token_coverage: TokenCoverage | None = None
    summary: tuple[tuple[str, str], ...] = ()
    error: ContractError | None = None

GetCacheObservationResponse = CacheServiceResponse
LookupArtifactResponse = CacheServiceResponse
LookupTokensResponse = CacheServiceResponse
CreatePrefetchIntentResponse = CacheServiceResponse
CreatePinIntentResponse = CacheServiceResponse
CreateUnpinIntentResponse = CacheServiceResponse
CreateClearIntentResponse = CacheServiceResponse
CreateRebuildIntentResponse = CacheServiceResponse
GetOperationStatusResponse = CacheServiceResponse
CancelOperationResponse = CacheServiceResponse
GetLMCacheEndpointsResponse = CacheServiceResponse
GetTierAndAdapterSummaryResponse = CacheServiceResponse
GetMaintenanceStatusResponse = CacheServiceResponse

INTENT_OPERATION_TYPES = {
    CreatePrefetchIntentRequest: CacheOperationType.PREFETCH,
    CreatePinIntentRequest: CacheOperationType.PIN,
    CreateUnpinIntentRequest: CacheOperationType.UNPIN,
    CreateClearIntentRequest: CacheOperationType.CLEAR,
    CreateRebuildIntentRequest: CacheOperationType.REBUILD,
}
