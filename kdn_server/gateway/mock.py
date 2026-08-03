"""Deterministic CPU-only gateway for contract tests and policy development."""
from __future__ import annotations

from kdn_server.contracts.cache_service import *
from cacheroute.contracts.v1.common import utc_now
from cacheroute.contracts.v1.errors import OutcomeCode
from kdn_server.domain import CacheOperationState, CacheOperationTask, CacheOperationType
from .base import GatewayAdapterBase
from .capabilities import SupportState


_OPERATION_CAPABILITY = {
    CacheOperationType.PREFETCH: "warm_prefetch", CacheOperationType.REBUILD: "warm_prefetch",
    CacheOperationType.PIN: "pin_unpin", CacheOperationType.UNPIN: "pin_unpin",
    CacheOperationType.CLEAR: "object_deletion",
}


class MockGateway(GatewayAdapterBase):
    """Fixture-only CPU adapter; it performs no backend or device I/O."""
    def __init__(self, capabilities, *, artifacts=(), observations=(), token_fixtures=None,
                 endpoints=(), adapter_summary=None, tier_summary=None, maintenance_summary=None):
        self.capabilities = capabilities
        self.artifacts = {x.artifact_id: x for x in artifacts}
        self.observations = {x.artifact_id: x for x in observations}
        self.token_fixtures = dict(token_fixtures or {})
        self.endpoints = tuple(endpoints)
        self.adapter_summary, self.tier_summary = adapter_summary, tier_summary
        self.maintenance_summary = maintenance_summary
        self._tasks, self._logical = {}, {}

    def lookup_artifact(self, request):
        if (guard := self._gate(request, self.capabilities.artifact_lookup)): return LookupArtifactResponse.model_validate(guard.model_dump())
        value = self.artifacts.get(request.artifact_id)
        if value is None: return self._response(request, response_type=LookupArtifactResponse, outcome=OutcomeCode.STALE, message="artifact not observed")
        if value.runtime_profile is not request.runtime_profile or value.compatibility_profile_id != request.compatibility_profile_id:
            return self._response(request, response_type=LookupArtifactResponse, outcome=OutcomeCode.INCOMPATIBLE, message="artifact provenance mismatch")
        return self._response(request, response_type=LookupArtifactResponse, artifact=value)

    def get_cache_observation(self, request):
        response_at = utc_now()
        if (guard := self._gate(request, self.capabilities.cache_observation)): return GetCacheObservationResponse.model_validate(guard.model_dump())
        value = self.observations.get(request.artifact_id)
        if value is None:
            return self._response(request, response_type=GetCacheObservationResponse, outcome=OutcomeCode.STALE, message="observation is absent or stale",
                                  observation=None)
        incompatible = any((value.artifact_id != request.artifact_id, value.runtime_profile is not request.runtime_profile,
            value.compatibility_profile_id != request.compatibility_profile_id, value.endpoint_id != request.endpoint_id))
        if incompatible: return self._response(request, response_type=GetCacheObservationResponse, outcome=OutcomeCode.INCOMPATIBLE, message="observation provenance mismatch")
        if value.endpoint_generation != request.endpoint_generation: return self._response(request, response_type=GetCacheObservationResponse, outcome=OutcomeCode.STALE, message="observation generation mismatch")
        if not value.is_fresh(at=response_at):
            return self._response(request, response_type=GetCacheObservationResponse, timestamp=response_at, outcome=OutcomeCode.STALE, message="observation is stale", observation=value)
        return self._response(request, response_type=GetCacheObservationResponse, timestamp=response_at, observation=value)

    def lookup_tokens(self, request):
        if (guard := self._gate(request, self.capabilities.token_lookup)): return LookupTokensResponse.model_validate(guard.model_dump())
        key = request.tokens.token_ids or request.tokens.token_reference.reference_id
        coverage = self.token_fixtures.get(key)
        if coverage is None:
            return self._response(request, response_type=LookupTokensResponse, outcome=OutcomeCode.TEXT_FALLBACK, message="tokens are not cached",
                                  fallback_eligible=True)
        # Whole-request lookup is useful even when exact range reporting is unknown.
        if self.capabilities.range_coverage is not SupportState.SUPPORTED and coverage.covered_ranges:
            coverage = coverage.model_copy(update={"covered_ranges": ()})
        return self._response(request, response_type=LookupTokensResponse, token_coverage=coverage)

    def submit_operation(self, request):
        operation = INTENT_OPERATION_TYPES.get(type(request))
        if operation is None: raise TypeError("unknown operation intent")
        capability = getattr(self.capabilities, _OPERATION_CAPABILITY[operation])
        response_type = {CreatePrefetchIntentRequest: CreatePrefetchIntentResponse, CreatePinIntentRequest: CreatePinIntentResponse,
            CreateUnpinIntentRequest: CreateUnpinIntentResponse, CreateClearIntentRequest: CreateClearIntentResponse,
            CreateRebuildIntentRequest: CreateRebuildIntentResponse}[type(request)]
        if (guard := self._gate(request, capability)): return response_type.model_validate(guard.model_dump())
        logical = (operation.value, request.artifact_id, request.endpoint_id, request.endpoint_generation,
                   request.runtime_profile.value, request.compatibility_profile_id)
        existing = self._tasks.get(request.idempotency_key)
        if existing:
            # Idempotency covers the complete logical target, not merely the key text.
            if self._logical[request.idempotency_key] != logical:
                return self._response(request, response_type=response_type, outcome=OutcomeCode.IDEMPOTENCY_CONFLICT,
                    message="idempotency key was used for a different logical request")
            return self._response(request, response_type=response_type, operation=existing)
        task = CacheOperationTask(idempotency_key=request.idempotency_key, operation=operation,
            artifact_id=request.artifact_id, runtime_profile=request.runtime_profile,
            compatibility_profile_id=request.compatibility_profile_id, gateway_profile="mock",
            endpoint_id=request.endpoint_id, endpoint_generation=request.endpoint_generation)
        self._tasks[request.idempotency_key], self._logical[request.idempotency_key] = task, logical
        return self._response(request, response_type=response_type, operation=task)

    def complete(self, task_id, *, failed=False):
        """Deterministically simulate asynchronous execution without worker I/O."""
        key, task = self._find(task_id)
        if task is None: raise KeyError(task_id)
        if task.state is CacheOperationState.PENDING: task = task.transition("running")
        task = task.transition("failed" if failed else "succeeded")
        self._tasks[key] = task
        return task

    def start(self, task_id):
        key, task = self._find(task_id)
        if task is None: raise KeyError(task_id)
        task = task.transition("running"); self._tasks[key] = task
        return task

    def _find(self, task_id):
        return next(((key, task) for key, task in self._tasks.items() if task.task_id == task_id), (None, None))

    def get_operation_status(self, request):
        if (guard := self._gate(request, self.capabilities.operation_status)): return GetOperationStatusResponse.model_validate(guard.model_dump())
        _, task = self._find(request.task_id)
        if task is None: return self._response(request, response_type=GetOperationStatusResponse, outcome=OutcomeCode.STALE, message="operation was not found")
        return self._response(request, response_type=GetOperationStatusResponse, operation=task)

    def cancel_operation(self, request):
        if (guard := self._gate(request, self.capabilities.cancellation)): return CancelOperationResponse.model_validate(guard.model_dump())
        key, task = self._find(request.task_id)
        if task is None: return self._response(request, response_type=CancelOperationResponse, outcome=OutcomeCode.STALE, message="operation was not found")
        if task.terminal: return self._response(request, response_type=CancelOperationResponse, operation=task)
        task = task.transition("cancelled"); self._tasks[key] = task
        return self._response(request, response_type=CancelOperationResponse, outcome=OutcomeCode.CANCELLED, message="operation cancelled", operation=task)

    def get_endpoints(self, request):
        if (guard := self._discovery_negotiate(request, GetLMCacheEndpointsResponse)): return guard
        for endpoint in self.endpoints:
            if any((endpoint.runtime_profile is not self.capabilities.runtime_profile,
                    endpoint.compatibility_profile_id != self.capabilities.compatibility_profile.compatibility_profile_id,
                    endpoint.endpoint_id != self.capabilities.endpoint_id,
                    endpoint.generation != self.capabilities.endpoint_generation)):
                return self._response(request, response_type=GetLMCacheEndpointsResponse, outcome=OutcomeCode.INCOMPATIBLE, message="endpoint fixture provenance mismatch")
        return self._response(request, response_type=GetLMCacheEndpointsResponse, endpoints=self.endpoints)

    def get_tier_adapter_summary(self, request):
        if (guard := self._gate(request, self.capabilities.tier_capacity_usage)): return GetTierAndAdapterSummaryResponse.model_validate(guard.model_dump())
        if self.adapter_summary is None or self.tier_summary is None:
            # Absence is a stale discovery fact, not a malformed success response.
            return self._response(request, response_type=GetTierAndAdapterSummaryResponse,
                outcome=OutcomeCode.STALE, message="tier or adapter summary fixture is absent")
        if not self._summary_matches(request, self.adapter_summary) or not self._summary_matches(request, self.tier_summary):
            # A valid fixture for another endpoint is still incompatible here.
            return self._response(request, response_type=GetTierAndAdapterSummaryResponse,
                outcome=OutcomeCode.INCOMPATIBLE, message="tier or adapter summary provenance mismatch")
        return self._response(request, response_type=GetTierAndAdapterSummaryResponse, adapter_summary=self.adapter_summary, tier_summary=self.tier_summary)

    def get_maintenance_status(self, request):
        if (guard := self._gate(request, self.capabilities.maintenance_eviction)): return GetMaintenanceStatusResponse.model_validate(guard.model_dump())
        if self.maintenance_summary is None:
            return self._response(request, response_type=GetMaintenanceStatusResponse,
                outcome=OutcomeCode.STALE, message="maintenance summary fixture is absent")
        if not self._summary_matches(request, self.maintenance_summary):
            return self._response(request, response_type=GetMaintenanceStatusResponse,
                outcome=OutcomeCode.INCOMPATIBLE, message="maintenance summary provenance mismatch")
        return self._response(request, response_type=GetMaintenanceStatusResponse, maintenance_summary=self.maintenance_summary)

    @staticmethod
    def _summary_matches(request, summary):
        return all((summary.runtime_profile is request.runtime_profile,
                    summary.compatibility_profile_id == request.compatibility_profile_id,
                    summary.endpoint_id == request.endpoint_id,
                    summary.endpoint_generation == request.endpoint_generation))
