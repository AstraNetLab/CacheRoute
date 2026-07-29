"""Explicit read-only Legacy gateway boundary (no Redis or filesystem I/O)."""
from kdn_server.contracts.cache_service import CacheServiceResponse
from kdn_server.contracts.errors import OutcomeCode
from kdn_server.domain import CacheOperationType, RuntimeProfile


class LegacyCacheAdapter:
    read_only = True

    def __init__(self, capabilities, *, artifacts=(), observations=()):
        self.capabilities = capabilities
        self.artifacts = {x.artifact_id: x for x in artifacts}
        self.observations = {x.artifact_id: x for x in observations}

    def discover_capabilities(self): return self.capabilities
    def _response(self, request, **values):
        return CacheServiceResponse(runtime_profile=RuntimeProfile.LEGACY,
            request_id=request.request_id, correlation_id=request.correlation_id,
            compatibility_profile_id=self.capabilities.compatibility_profile.compatibility_profile_id,
            endpoint_id=self.capabilities.endpoint_id,
            endpoint_generation=self.capabilities.endpoint_generation, **values)
    def lookup_artifact(self, request):
        artifact = self.artifacts.get(request.artifact_id)
        return self._response(request, outcome=OutcomeCode.SUCCESS if artifact else OutcomeCode.STALE, artifact=artifact)
    def get_cache_observation(self, request):
        observation = self.observations.get(request.artifact_id)
        return self._response(request, outcome=OutcomeCode.SUCCESS if observation else OutcomeCode.STALE, observation=observation)
    def lookup_tokens(self, request): return self._response(request, outcome=OutcomeCode.UNSUPPORTED)
    def submit_operation(self, request):
        # Legacy remains representable, but the v1 facade never gains writes through it.
        return self._response(request, outcome=OutcomeCode.UNSUPPORTED)
    def get_operation_status(self, request): return self._response(request, outcome=OutcomeCode.UNSUPPORTED)
    def cancel_operation(self, request): return self._response(request, outcome=OutcomeCode.UNSUPPORTED)
    def get_endpoints(self): raise NotImplementedError
    def get_tier_adapter_summary(self): raise NotImplementedError
    def get_maintenance_status(self): raise NotImplementedError
