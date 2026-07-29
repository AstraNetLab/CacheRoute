"""Deterministic CPU-only gateway for contract tests and policy development."""
from __future__ import annotations

from kdn_server.contracts.cache_service import *
from kdn_server.contracts.errors import ContractError, GatewayContractException, OutcomeCode
from kdn_server.domain import CacheArtifact, CacheOperationState, CacheOperationTask, LMCacheEndpoint
from .capabilities import CapabilitySnapshot, SupportState


class MockGateway:
    def __init__(self, capabilities: CapabilitySnapshot, *, artifacts=(), observations=(), token_fixtures=None, endpoints=()):
        self.capabilities = capabilities
        self.artifacts = {x.artifact_id: x for x in artifacts}
        self.observations = {x.artifact_id: x for x in observations}
        self.token_fixtures = dict(token_fixtures or {})
        self.endpoints = tuple(endpoints)
        self._tasks = {}
        self._logical = {}

    def discover_capabilities(self): return self.capabilities
    def _response(self, request=None, **kw):
        base = dict(runtime_profile=self.capabilities.runtime_profile,
                    compatibility_profile_id=self.capabilities.compatibility_profile.compatibility_profile_id,
                    endpoint_id=self.capabilities.endpoint_id,
                    endpoint_generation=self.capabilities.endpoint_generation)
        if request is not None: base.update(request_id=request.request_id, correlation_id=request.correlation_id)
        return CacheServiceResponse(**(base | kw))
    def lookup_artifact(self, request):
        value = self.artifacts.get(request.artifact_id)
        return self._response(request, outcome=OutcomeCode.SUCCESS if value else OutcomeCode.STALE, artifact=value)
    def get_cache_observation(self, request):
        value = self.observations.get(request.artifact_id)
        outcome = OutcomeCode.SUCCESS if value and value.is_fresh() else OutcomeCode.STALE
        return self._response(request, outcome=outcome, observation=value)
    def lookup_tokens(self, request):
        if not self.capabilities.token_lookup:
            return self._response(request, outcome=OutcomeCode.UNSUPPORTED)
        key = request.tokens.token_ids or request.tokens.token_reference.reference_id
        coverage = self.token_fixtures.get(key)
        return self._response(request, outcome=OutcomeCode.SUCCESS if coverage else OutcomeCode.TEXT_FALLBACK,
                              token_coverage=coverage)
    def submit_operation(self, request):
        operation = INTENT_OPERATION_TYPES.get(type(request))
        if operation is None: raise TypeError("unknown operation intent")
        logical = (operation.value, request.artifact_id, request.endpoint_id, request.endpoint_generation,
                   request.runtime_profile.value, request.compatibility_profile_id)
        existing = self._tasks.get(request.idempotency_key)
        if existing:
            if self._logical[request.idempotency_key] != logical:
                error = ContractError(runtime_profile=request.runtime_profile, request_id=request.request_id,
                    compatibility_profile_id=request.compatibility_profile_id, endpoint_id=request.endpoint_id,
                    endpoint_generation=request.endpoint_generation, code=OutcomeCode.IDEMPOTENCY_CONFLICT,
                    message="idempotency key was used for a different logical request")
                raise GatewayContractException(error)
            return self._response(request, operation=existing)
        task = CacheOperationTask(idempotency_key=request.idempotency_key, operation=operation,
            artifact_id=request.artifact_id, runtime_profile=request.runtime_profile,
            compatibility_profile_id=request.compatibility_profile_id,
            gateway_profile="mock", endpoint_id=request.endpoint_id,
            endpoint_generation=request.endpoint_generation)
        self._tasks[request.idempotency_key] = task
        self._logical[request.idempotency_key] = logical
        return self._response(request, operation=task)
    def complete(self, task_id, *, failed=False):
        key, task = next((x for x in self._tasks.items() if x[1].task_id == task_id), (None, None))
        if task is None: raise KeyError(task_id)
        if task.state is CacheOperationState.PENDING: task = task.transition("running")
        task = task.transition("failed" if failed else "succeeded")
        self._tasks[key] = task
        return task
    def get_operation_status(self, request):
        task = next((x for x in self._tasks.values() if x.task_id == request.task_id), None)
        return self._response(request, outcome=OutcomeCode.SUCCESS if task else OutcomeCode.STALE, operation=task)
    def cancel_operation(self, request):
        key, task = next((x for x in self._tasks.items() if x[1].task_id == request.task_id), (None, None))
        if task and not task.terminal:
            task = task.transition("cancelled"); self._tasks[key] = task
        return self._response(request, outcome=OutcomeCode.CANCELLED if task else OutcomeCode.STALE, operation=task)
    def get_endpoints(self): return self._response(endpoints=self.endpoints)
    def get_tier_adapter_summary(self):
        return self._response(summary=tuple(("adapter", x) for x in self.capabilities.loaded_adapters))
    def get_maintenance_status(self):
        outcome = OutcomeCode.SUCCESS if self.capabilities.maintenance_eviction else OutcomeCode.UNSUPPORTED
        return self._response(outcome=outcome)
