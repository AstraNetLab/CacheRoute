"""Shared adapter negotiation and safe response construction."""
from kdn_server.contracts.cache_service import CacheServiceResponse
from kdn_server.contracts.errors import ContractErrorDetail, OutcomeCode
from .capabilities import SupportState


class GatewayAdapterBase:
    capabilities = None

    def discover_capabilities(self):
        return self.capabilities

    def _response(self, request, *, response_type=CacheServiceResponse, outcome=OutcomeCode.SUCCESS, message=None,
                  retryable=False, fallback_eligible=False, **values):
        metadata = dict(runtime_profile=request.runtime_profile, request_id=request.request_id,
                        correlation_id=request.correlation_id)
        for field in ("compatibility_profile_id", "endpoint_id", "endpoint_generation"):
            if hasattr(request, field): metadata[field] = getattr(request, field)
        error = None
        if outcome is not OutcomeCode.SUCCESS:
            error = ContractErrorDetail(code=outcome, message=message or outcome.value.replace("_", " "),
                                        retryable=retryable, fallback_eligible=fallback_eligible)
        return response_type(**metadata, outcome=outcome, error=error, **values)

    def _negotiate(self, request):
        cap = self.capabilities
        if (request.runtime_profile is not cap.runtime_profile or
                request.compatibility_profile_id != cap.compatibility_profile.compatibility_profile_id or
                request.endpoint_id != cap.endpoint_id):
            return self._response(request, outcome=OutcomeCode.INCOMPATIBLE,
                                  message="request target is incompatible with gateway capabilities")
        if request.endpoint_generation != cap.endpoint_generation:
            return self._response(request, outcome=OutcomeCode.STALE,
                                  message="request endpoint generation is stale", retryable=True)
        return None

    def _gate(self, request, capability):
        mismatch = self._negotiate(request)
        if mismatch is not None: return mismatch
        if capability is not SupportState.SUPPORTED:
            return self._response(request, outcome=OutcomeCode.UNSUPPORTED,
                                  message="gateway capability is unsupported or unknown")
        return None
