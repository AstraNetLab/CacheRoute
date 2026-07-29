"""Deterministic CPU-only gateway for contract tests and policy development."""
from __future__ import annotations

from kdn_server.contracts.cache_service import *
from kdn_server.contracts.errors import GatewayContractException, OutcomeCode, ContractErrorDetail
from kdn_server.domain import CacheOperationState, CacheOperationTask, CacheOperationType
from .base import GatewayAdapterBase


_OPERATION_CAPABILITY = {
    CacheOperationType.PREFETCH: "warm_prefetch", CacheOperationType.REBUILD: "warm_prefetch",
    CacheOperationType.PIN: "pin_unpin", CacheOperationType.UNPIN: "pin_unpin",
    CacheOperationType.CLEAR: "object_deletion",
}


class MockGateway(GatewayAdapterBase):
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
        if (guard := self._negotiate(request)): return guard
        value = self.artifacts.get(request.artifact_id)
        if value is None: return self._response(request, outcome=OutcomeCode.STALE, message="artifact not observed")
        return self._response(request, artifact=value)

    def get_cache_observation(self, request):
        if (guard := self._negotiate(request)): return guard
        value = self.observations.get(request.artifact_id)
        if value is None or not value.is_fresh():
            return self._response(request, outcome=OutcomeCode.STALE, message="observation is absent or stale",
                                  observation=value)
        return self._response(request, observation=value)

    def lookup_tokens(self, request):
        if (guard := self._gate(request, self.capabilities.token_lookup)): return guard
        key = request.tokens.token_ids or request.tokens.token_reference.reference_id
        coverage = self.token_fixtures.get(key)
        if coverage is None:
            return self._response(request, outcome=OutcomeCode.TEXT_FALLBACK, message="tokens are not cached",
                                  fallback_eligible=True)
        return self._response(request, token_coverage=coverage)

    def submit_operation(self, request):
        operation = INTENT_OPERATION_TYPES.get(type(request))
        if operation is None: raise TypeError("unknown operation intent")
        capability = getattr(self.capabilities, _OPERATION_CAPABILITY[operation])
        if (guard := self._gate(request, capability)): return guard
        logical = (operation.value, request.artifact_id, request.endpoint_id, request.endpoint_generation,
                   request.runtime_profile.value, request.compatibility_profile_id)
        existing = self._tasks.get(request.idempotency_key)
        if existing:
            if self._logical[request.idempotency_key] != logical:
                raise GatewayContractException(ContractErrorDetail(code=OutcomeCode.IDEMPOTENCY_CONFLICT,
                    message="idempotency key was used for a different logical request"))
            return self._response(request, operation=existing)
        task = CacheOperationTask(idempotency_key=request.idempotency_key, operation=operation,
            artifact_id=request.artifact_id, runtime_profile=request.runtime_profile,
            compatibility_profile_id=request.compatibility_profile_id, gateway_profile="mock",
            endpoint_id=request.endpoint_id, endpoint_generation=request.endpoint_generation)
        self._tasks[request.idempotency_key], self._logical[request.idempotency_key] = task, logical
        return self._response(request, operation=task)

    def complete(self, task_id, *, failed=False):
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
        if (guard := self._gate(request, self.capabilities.operation_status)): return guard
        _, task = self._find(request.task_id)
        if task is None: return self._response(request, outcome=OutcomeCode.STALE, message="operation was not found")
        return self._response(request, operation=task)

    def cancel_operation(self, request):
        if (guard := self._gate(request, self.capabilities.cancellation)): return guard
        key, task = self._find(request.task_id)
        if task is None: return self._response(request, outcome=OutcomeCode.STALE, message="operation was not found")
        if task.terminal: return self._response(request, operation=task)
        task = task.transition("cancelled"); self._tasks[key] = task
        return self._response(request, outcome=OutcomeCode.CANCELLED, message="operation cancelled", operation=task)

    def get_endpoints(self, request):
        return self._response(request, endpoints=self.endpoints)

    def get_tier_adapter_summary(self, request):
        if (guard := self._gate(request, self.capabilities.tier_capacity_usage)): return guard
        return self._response(request, adapter_summary=self.adapter_summary, tier_summary=self.tier_summary)

    def get_maintenance_status(self, request):
        if (guard := self._gate(request, self.capabilities.maintenance_eviction)): return guard
        return self._response(request, maintenance_summary=self.maintenance_summary)
