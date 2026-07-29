"""Explicit read-only Legacy gateway boundary (no Redis or filesystem I/O)."""
from kdn_server.contracts.errors import OutcomeCode
from .base import GatewayAdapterBase


class LegacyCacheAdapter(GatewayAdapterBase):
    read_only = True

    def __init__(self, capabilities, *, artifacts=(), observations=()):
        self.capabilities = capabilities
        self.artifacts = {x.artifact_id: x for x in artifacts}
        self.observations = {x.artifact_id: x for x in observations}

    def lookup_artifact(self, request):
        if (guard := self._negotiate(request)): return guard
        artifact = self.artifacts.get(request.artifact_id)
        if artifact is None: return self._response(request, outcome=OutcomeCode.STALE, message="artifact not observed")
        return self._response(request, artifact=artifact)

    def get_cache_observation(self, request):
        if (guard := self._negotiate(request)): return guard
        observation = self.observations.get(request.artifact_id)
        if observation is None or not observation.is_fresh():
            return self._response(request, outcome=OutcomeCode.STALE,
                                  message="Legacy observation is absent or stale", observation=observation)
        return self._response(request, observation=observation)

    def _unsupported(self, request):
        if (guard := self._negotiate(request)): return guard
        return self._response(request, outcome=OutcomeCode.UNSUPPORTED,
                              message="Legacy adapter is read-only and does not provide this capability")

    def lookup_tokens(self, request): return self._unsupported(request)
    def submit_operation(self, request): return self._unsupported(request)
    def get_operation_status(self, request): return self._unsupported(request)
    def cancel_operation(self, request): return self._unsupported(request)
    def get_tier_adapter_summary(self, request): return self._unsupported(request)
    def get_maintenance_status(self, request): return self._unsupported(request)
    def get_endpoints(self, request):
        return self._response(request, outcome=OutcomeCode.UNSUPPORTED,
                              message="Legacy endpoint discovery is unavailable")
