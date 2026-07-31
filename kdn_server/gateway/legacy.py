"""Explicit read-only Legacy gateway boundary (no Redis or filesystem I/O)."""
from kdn_server.contracts.cache_service import (
    CancelOperationResponse, CreateClearIntentRequest, CreateClearIntentResponse,
    CreatePinIntentRequest, CreatePinIntentResponse, CreatePrefetchIntentRequest,
    CreatePrefetchIntentResponse, CreateRebuildIntentRequest, CreateRebuildIntentResponse,
    CreateUnpinIntentRequest, CreateUnpinIntentResponse, GetCacheObservationResponse,
    GetLMCacheEndpointsResponse, GetMaintenanceStatusResponse, GetOperationStatusResponse,
    GetTierAndAdapterSummaryResponse, LookupArtifactResponse, LookupTokensResponse,
)
from cacheroute.contracts.v1.common import utc_now
from cacheroute.contracts.v1.errors import OutcomeCode
from .base import GatewayAdapterBase


class LegacyCacheAdapter(GatewayAdapterBase):
    """Read-only Legacy projection with no Redis or filesystem access.

    Legacy generation zero means unknown; shared negotiation rejects v1 calls
    before this adapter can project or return Legacy state.
    """
    read_only = True

    def __init__(self, capabilities, *, artifacts=(), observations=()):
        self.capabilities = capabilities
        self.artifacts = {x.artifact_id: x for x in artifacts}
        self.observations = {x.artifact_id: x for x in observations}

    def lookup_artifact(self, request):
        if (guard := self._gate(request, self.capabilities.artifact_lookup)): return LookupArtifactResponse.model_validate(guard.model_dump())
        artifact = self.artifacts.get(request.artifact_id)
        if artifact is None: return self._response(request, response_type=LookupArtifactResponse, outcome=OutcomeCode.STALE, message="artifact not observed")
        if artifact.runtime_profile is not request.runtime_profile or artifact.compatibility_profile_id != request.compatibility_profile_id:
            return self._response(request, response_type=LookupArtifactResponse, outcome=OutcomeCode.INCOMPATIBLE, message="artifact provenance mismatch")
        return self._response(request, response_type=LookupArtifactResponse, artifact=artifact)

    def get_cache_observation(self, request):
        response_at = utc_now()
        if (guard := self._gate(request, self.capabilities.cache_observation)): return GetCacheObservationResponse.model_validate(guard.model_dump())
        observation = self.observations.get(request.artifact_id)
        if observation is None: return self._response(request, response_type=GetCacheObservationResponse, outcome=OutcomeCode.STALE, message="Legacy observation is absent")
        incompatible = any((observation.artifact_id != request.artifact_id,
            observation.runtime_profile is not request.runtime_profile,
            observation.compatibility_profile_id != request.compatibility_profile_id,
            observation.endpoint_id != request.endpoint_id))
        if incompatible: return self._response(request, response_type=GetCacheObservationResponse, outcome=OutcomeCode.INCOMPATIBLE, message="Legacy observation provenance mismatch")
        if observation.endpoint_generation != request.endpoint_generation:
            return self._response(request, response_type=GetCacheObservationResponse, outcome=OutcomeCode.STALE, message="Legacy observation generation mismatch")
        if not observation.is_fresh(at=response_at): return self._response(request, response_type=GetCacheObservationResponse, timestamp=response_at, outcome=OutcomeCode.STALE, message="Legacy observation is stale", observation=observation)
        return self._response(request, response_type=GetCacheObservationResponse, timestamp=response_at, observation=observation)

    def _unsupported(self, request, response_type):
        if (guard := self._negotiate(request)): return response_type.model_validate(guard.model_dump())
        return self._response(request, response_type=response_type, outcome=OutcomeCode.UNSUPPORTED,
                              message="Legacy adapter is read-only and does not provide this capability")

    def lookup_tokens(self, request): return self._unsupported(request, LookupTokensResponse)
    def submit_operation(self, request):
        response_type = {CreatePrefetchIntentRequest: CreatePrefetchIntentResponse,
            CreatePinIntentRequest: CreatePinIntentResponse, CreateUnpinIntentRequest: CreateUnpinIntentResponse,
            CreateClearIntentRequest: CreateClearIntentResponse, CreateRebuildIntentRequest: CreateRebuildIntentResponse}[type(request)]
        return self._unsupported(request, response_type)
    def get_operation_status(self, request): return self._unsupported(request, GetOperationStatusResponse)
    def cancel_operation(self, request): return self._unsupported(request, CancelOperationResponse)
    def get_tier_adapter_summary(self, request): return self._unsupported(request, GetTierAndAdapterSummaryResponse)
    def get_maintenance_status(self, request): return self._unsupported(request, GetMaintenanceStatusResponse)
    def get_endpoints(self, request):
        if (guard := self._discovery_negotiate(request, GetLMCacheEndpointsResponse)): return guard
        return self._response(request, response_type=GetLMCacheEndpointsResponse, outcome=OutcomeCode.UNSUPPORTED,
                              message="Legacy endpoint discovery is unavailable")
