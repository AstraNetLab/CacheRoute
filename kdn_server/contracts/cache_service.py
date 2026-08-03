"""Compatibility exports for canonical v1 Cache Service contracts."""

from datetime import datetime, timedelta
from enum import Enum
from typing import ClassVar

from pydantic import AwareDatetime, Field, field_validator, model_validator

from cacheroute.cache import (
    CacheArtifact, CacheOperationState, CacheOperationTask, CacheOperationType,
    CacheReplicaObservation,
)
from cacheroute.contracts.v1.cache_service import (
    INTENT_OPERATION_TYPES, AdapterSummary, ArtifactRequest, CacheServiceResponse,
    CancelOperationRequest, CancelOperationResponse, CapacityUsageObservation,
    CreateClearIntentRequest, CreateClearIntentResponse, CreatePinIntentRequest,
    CreatePinIntentResponse, CreatePrefetchIntentRequest, CreatePrefetchIntentResponse,
    CreateRebuildIntentRequest, CreateRebuildIntentResponse, CreateUnpinIntentRequest,
    CreateUnpinIntentResponse, GatewayTargetedResponse, GetCacheObservationRequest,
    GetCacheObservationResponse, GetLMCacheEndpointsRequest, GetLMCacheEndpointsResponse,
    GetMaintenanceStatusRequest, GetMaintenanceStatusResponse, GetOperationStatusRequest,
    GetOperationStatusResponse, GetTierAndAdapterSummaryRequest,
    GetTierAndAdapterSummaryResponse, LookupArtifactRequest, LookupArtifactResponse,
    LookupTokensRequest, LookupTokensResponse, MaintenanceSummary, OperationIntentRequest,
    OperationResponse, SummaryBase, TierLevel, TierSummary, TokenCoverage,
)
from cacheroute.contracts.v1.common import (
    ContractModel, GatewayTargetedRequest, SupportState, TokenInput,
    VersionedMessage, utc_now,
)
from cacheroute.contracts.v1.errors import ContractErrorDetail, OutcomeCode
from cacheroute.runtime import RuntimeProfile
from cacheroute.topology import LMCacheEndpoint

__all__ = [
    "datetime", "timedelta", "Enum", "ClassVar", "AwareDatetime", "Field",
    "field_validator", "model_validator", "RuntimeProfile", "CacheArtifact",
    "CacheOperationState", "CacheOperationTask", "CacheOperationType",
    "CacheReplicaObservation", "LMCacheEndpoint", "ContractModel",
    "GatewayTargetedRequest", "SupportState", "TokenInput", "VersionedMessage",
    "utc_now", "ContractErrorDetail", "OutcomeCode", "ArtifactRequest",
    "GetCacheObservationRequest", "LookupArtifactRequest", "LookupTokensRequest",
    "OperationIntentRequest", "CreatePrefetchIntentRequest", "CreatePinIntentRequest",
    "CreateUnpinIntentRequest", "CreateClearIntentRequest", "CreateRebuildIntentRequest",
    "GetOperationStatusRequest", "CancelOperationRequest", "GetLMCacheEndpointsRequest",
    "GetTierAndAdapterSummaryRequest", "GetMaintenanceStatusRequest", "TokenCoverage",
    "SummaryBase", "AdapterSummary", "TierLevel", "CapacityUsageObservation",
    "TierSummary", "MaintenanceSummary", "CacheServiceResponse",
    "GatewayTargetedResponse", "GetCacheObservationResponse", "LookupArtifactResponse",
    "LookupTokensResponse", "OperationResponse", "CreatePrefetchIntentResponse",
    "CreatePinIntentResponse", "CreateUnpinIntentResponse", "CreateClearIntentResponse",
    "CreateRebuildIntentResponse", "GetOperationStatusResponse",
    "CancelOperationResponse", "GetLMCacheEndpointsResponse",
    "GetTierAndAdapterSummaryResponse", "GetMaintenanceStatusResponse",
    "INTENT_OPERATION_TYPES",
]
