# Public API and data models

[Back to handbook](README.md). Each `## API:` section is a machine-checkable
catalog entry. **Exports** follows the module's explicit `__all__`; names that
are merely importable are not automatically supported. Canonical Pydantic
models are frozen, reject extra fields, revalidate `model_copy`, serialize enums
and UTC timestamps with `model_dump(mode="json")`/`model_dump_json()`, and do no
network or backend I/O unless stated otherwise.

## API: `cacheroute.runtime`

- **Status:** Current public domain API.
- **Exports:** `RuntimeProfile`.
- **Use / non-goals:** resolve runtime compatibility identity; it does not probe installed services.
- **Values/defaults/validation:** `v1`, `legacy`, `test/mock`, `auto`; `auto` is accepted only by `resolve_startup(value=None, v1_available=True)` and resolves to v1 or Legacy. `normalize` accepts the aliases listed under compatibility below.
- **Evidence:** [`runtime/__init__.py`](../../src/cacheroute/runtime/__init__.py), [`profiles.py`](../../src/cacheroute/runtime/profiles.py), [`test_runtime_compat.py`](../../test/test_runtime_compat.py).
- **Example:** `from cacheroute.runtime import RuntimeProfile; assert RuntimeProfile.resolve_startup("auto") is RuntimeProfile.V1`

## API: `cacheroute.runtime.state`

- **Status:** Current public foundation API.
- **Exports:** `Snapshot`, `StateTransitionError`, `StrEnum`.
- **Use / non-goals:** immutable state bases, string enums, structured transition errors; `canonical_id`, clocks and validators are internal because they are absent from `__all__`.
- **Fields/serialization:** `Snapshot` forbids extras, normalizes any `runtime_profile`, rejects persisted `auto`, validates copies, and provides `to_json()`. `StateTransitionError.to_dict()` returns error/model/current/requested/allowed state data.
- **Evidence:** [`state.py`](../../src/cacheroute/runtime/state.py), [`test_domain_state_migration.py`](../../test/test_domain_state_migration.py).
- **Example:** `from cacheroute.runtime.state import StateTransitionError, Snapshot, StrEnum`

## API: `cacheroute.topology`

- **Status:** Current public domain API; `cacheroute.topology.lmcache` exposes the same names.
- **Exports:** `LMCacheEndpoint`, `LMCacheGatewayProfile`.
- **Fields/defaults/validators:** endpoint fields are `endpoint_id: str | None` (computed), required non-empty `name`, `runtime_profile=V1`, required `gateway_profile`, required non-empty `compatibility_profile_id`, `generation: int=1` (minimum 1), and optional `adapter`/`tier`. ID is deterministically `endpoint_` plus 32 lowercase hex characters from `name`; supplied IDs must match. `next_generation()` returns a validated copy.
- **Enum wire values:** `mp_http_api`, `mp_coordinator`, `mp_sdk`, `mp_metrics_events`, `legacy_gateway`, `mock`, `unknown_future`.
- **Use / non-goals:** logical endpoint identity/incarnation, not discovery or connection I/O.
- **Evidence:** [`topology/__init__.py`](../../src/cacheroute/topology/__init__.py), [`lmcache.py`](../../src/cacheroute/topology/lmcache.py), [`test_domain_state_migration.py`](../../test/test_domain_state_migration.py).
- **Example:** `from cacheroute.topology import LMCacheEndpoint, LMCacheGatewayProfile; endpoint = LMCacheEndpoint(name="local", gateway_profile=LMCacheGatewayProfile.MOCK, compatibility_profile_id="mock-v1")`

## API: `cacheroute.cache`

- **Status:** Current public logical-domain API; `cacheroute.cache.models` exposes the same names.
- **Exports:** `CacheArtifact`, `CacheOperationState`, `CacheOperationTask`, `CacheOperationType`, `CacheReplicaObservation`, `ObservationConfidence`, `ObservationSource`, `ObservationState`.
- **Enums:** operation types `lookup`, `prefetch`, `pin`, `unpin`, `clear`, `rebuild`, `observe`; operation states `pending`, `running`, `retry_wait`, `succeeded`, `failed`, `cancelled`; observation states `pending`, `available`, `unavailable`, `unknown`, `partial`; confidence `low`, `medium`, `high`; sources `http_api`, `coordinator`, `sdk`, `metrics_event`, `legacy_projection`, `mock`.
- **Artifact fields:** computed `artifact_id`; required `knowledge_id`, `model_profile`, `tokenizer_profile`, `cache_data_profile`, `compatibility_profile_id`; defaults `artifact_version="1"`, `adapters=()`, `runtime_profile=V1`, `schema_version="v1"`, UTC `created_at`. Adapters must be unique, non-empty and canonically ordered. ID is deterministic `artifact_` plus 32 lowercase hex characters over the serialized identity.
- **Observation fields/invariants:** `observation_id` is deterministic; `artifact_id`/`endpoint_id` match source patterns; generation is non-negative; provenance, source/expiry UTC times, confidence and Legacy metadata are explicit. Non-Legacy observations require an observed time, future expiry, and generation >0. Legacy projections alone use generation 0, Legacy profiles/source/uncertainty, and optional Legacy KV metadata. `is_fresh` and `applies_to` are read-only checks.
- **Operation fields/invariants:** `task_id` defaults to `cacheop_` plus 32 random lowercase hex characters; required non-empty idempotency/compatibility data and artifact; runtime defaults v1, state pending, attempt 0, UTC timestamps. Endpoint ID/generation are paired, write/gateway compatibility is validated, and `transition` rejects invalid/backwards transitions.
- **Use / non-goals:** logical snapshots and lifecycle only; no LMCache/Redis execution or authoritative physical index.
- **Evidence:** [`models.py`](../../src/cacheroute/cache/models.py), [`test_domain_state_migration.py`](../../test/test_domain_state_migration.py), [`test/kdn/test_domain_models.py`](../../test/kdn/test_domain_models.py).
- **Example:** `from cacheroute.cache import CacheOperationState, CacheOperationType; assert CacheOperationState.SUCCEEDED.terminal`

## API: `cacheroute.routing`

- **Status:** Current public logical-domain API; `cacheroute.routing.queue` exposes the same names.
- **Exports:** `QueueState`, `QueueWork`.
- **Fields/defaults/validators:** work ID defaults to `queuework_` plus 32 random lowercase hex; required non-empty `idempotency_key` and `cache_task_id` matching `cacheop_…`; state defaults `queued`; timestamps default UTC. Values are `queued`, `claimed`, `executing`, `retry_wait`, `completed`, `failed`, `cancelled`; validated transitions cannot move time backwards.
- **Use / non-goals:** reusable lifecycle state, not the process-global Proxy queue.
- **Evidence:** [`queue.py`](../../src/cacheroute/routing/queue.py), [`test_domain_state_migration.py`](../../test/test_domain_state_migration.py).
- **Example:** `from cacheroute.routing import QueueState, QueueWork; work = QueueWork(idempotency_key="demo", cache_task_id="cacheop_" + "0" * 32)`

## API: `cacheroute.runtime.profiles`

- **Status:** Current public implementation-module API.
- **Exports:** `RuntimeProfile`; identical object re-exported by `cacheroute.runtime`.
- **Evidence:** [`profiles.py`](../../src/cacheroute/runtime/profiles.py), [`test_runtime_compat.py`](../../test/test_runtime_compat.py).
- **Example:** `from cacheroute.runtime.profiles import RuntimeProfile`

## API: `cacheroute.topology.lmcache`

- **Status:** Current public implementation-module API.
- **Exports:** `LMCacheEndpoint`, `LMCacheGatewayProfile`; fields, values and invariants are cataloged under `cacheroute.topology`.
- **Evidence:** [`lmcache.py`](../../src/cacheroute/topology/lmcache.py), [`test_domain_state_migration.py`](../../test/test_domain_state_migration.py).
- **Example:** `from cacheroute.topology.lmcache import LMCacheEndpoint`

## API: `cacheroute.cache.models`

- **Status:** Current public implementation-module API.
- **Exports:** `CacheArtifact`, `CacheOperationState`, `CacheOperationTask`, `CacheOperationType`, `CacheReplicaObservation`, `ObservationConfidence`, `ObservationSource`, `ObservationState`; details are cataloged under `cacheroute.cache`.
- **Evidence:** [`models.py`](../../src/cacheroute/cache/models.py), [`test_domain_state_migration.py`](../../test/test_domain_state_migration.py).
- **Example:** `from cacheroute.cache.models import CacheArtifact`

## API: `cacheroute.routing.queue`

- **Status:** Current public implementation-module API.
- **Exports:** `QueueState`, `QueueWork`; details are cataloged under `cacheroute.routing`.
- **Evidence:** [`queue.py`](../../src/cacheroute/routing/queue.py), [`test_domain_state_migration.py`](../../test/test_domain_state_migration.py).
- **Example:** `from cacheroute.routing.queue import QueueWork`

## API: `cacheroute.contracts`

- **Status:** Current public version namespace.
- **Exports:** `v1`.
- **Use / non-goals:** selects the stable contract version; it is not a flat re-export of every contract.
- **Evidence:** [`contracts/__init__.py`](../../src/cacheroute/contracts/__init__.py), [`test_contract_foundation.py`](../../test/test_contract_foundation.py).
- **Example:** `from cacheroute.contracts import v1`

## API: `cacheroute.contracts.v1.common`

- **Status:** Current public wire API.
- **Exports:** `KDN_CONTRACT_VERSION`, `GATEWAY_CONTRACT_VERSION`, `ENDPOINT_ID_PATTERN`, `SupportState`, `utc_now`, `ContractModel`, `VersionedMessage`, `GatewayTargetedRequest`, `TokenReference`, `TokenInput`.
- **Constants/enums:** versions are `kdn.v1` and `lmcache-gateway.v1`; endpoint pattern is `^endpoint_[0-9a-f]{32}$`; support values are `supported`, `unsupported`, `unknown` and only supported is truthy.
- **Fields/defaults/validators:** `VersionedMessage` requires resolved non-auto runtime; defaults contract version, `request_id="req_" + uuid4().hex`, `correlation_id=None`, and UTC timestamp. Only UTC and exact `kdn.v1` validate. `GatewayTargetedRequest` adds non-empty compatibility ID, endpoint ID and generation >=0; zero is Legacy-only. `TokenReference` requires non-empty opaque reference and optional non-negative count. `TokenInput` requires exactly one of a non-empty tuple of non-negative token IDs or a reference.
- **Use / non-goals:** immutable JSON-safe envelopes and token vocabulary, not handlers/storage.
- **Evidence:** [`common.py`](../../src/cacheroute/contracts/v1/common.py), [`test_contract_foundation.py`](../../test/test_contract_foundation.py).
- **Example:** `from cacheroute.contracts.v1.common import TokenInput; tokens = TokenInput(token_ids=(1, 2))`

## API: `cacheroute.contracts.v1.errors`

- **Status:** Current public wire API.
- **Exports:** `OutcomeCode`, `ContractErrorDetail`, `ContractError` (identity alias of `ContractErrorDetail`).
- **Enum/fields:** outcomes are `success`, `unsupported`, `incompatible`, `stale`, `partial`, `failed`, `cancelled`, `text_fallback`, `idempotency_conflict`. Error requires `code` and non-empty `message`; defaults `contract_version="kdn.v1"`, `retryable=False`, `fallback_eligible=False`; version must match exactly.
- **Use / non-goals:** safe failures; backend exception objects never cross the wire.
- **Evidence:** [`errors.py`](../../src/cacheroute/contracts/v1/errors.py), [`test/kdn/test_cache_service_contracts.py`](../../test/kdn/test_cache_service_contracts.py).
- **Example:** `from cacheroute.contracts.v1.errors import ContractError, OutcomeCode; error = ContractError(code=OutcomeCode.FAILED, message="safe failure")`

## API: `cacheroute.contracts.v1.knowledge`

- **Status:** Current public wire API.
- **Exports:** `KnowledgeDescriptor`, `KnowledgeResponse`; request/response pairs `RegisterKnowledge*`, `UpdateKnowledge*`, `ResolveKnowledge*`, `ListCompatibleArtifacts*`, `QueryArtifactCompatibility*`, `ReportRequestOutcome*`.
- **Actual names:** `RegisterKnowledgeRequest`, `RegisterKnowledgeResponse`, `UpdateKnowledgeRequest`, `UpdateKnowledgeResponse`, `ResolveKnowledgeRequest`, `ResolveKnowledgeResponse`, `ListCompatibleArtifactsRequest`, `ListCompatibleArtifactsResponse`, `QueryArtifactCompatibilityRequest`, `QueryArtifactCompatibilityResponse`, `ReportRequestOutcomeRequest`, `ReportRequestOutcomeResponse`.
- **Fields/defaults:** descriptor adds required non-empty `knowledge_id`, `revision="1"`, `content_reference=None`. Resolve/list require knowledge ID; compatibility query requires `CacheArtifact`; outcome report requires knowledge ID/outcome and optional operation ID. `KnowledgeResponse` defaults success, optional knowledge/artifact/compatible/error, and `artifacts=()`.
- **Aliases/invariants:** every named response is the identical `KnowledgeResponse` class. Success forbids error; non-success requires matching error code; text fallback requires `fallback_eligible=True`.
- **Use / non-goals:** storage-neutral facade vocabulary; defining it does not wire root KDN handlers.
- **Evidence:** [`knowledge.py`](../../src/cacheroute/contracts/v1/knowledge.py), [`test_contract_service_migration.py`](../../test/test_contract_service_migration.py).
- **Example:** `from cacheroute.contracts.v1.knowledge import ResolveKnowledgeRequest; from cacheroute.runtime import RuntimeProfile; request = ResolveKnowledgeRequest(runtime_profile=RuntimeProfile.V1, knowledge_id="demo")`

## API: `cacheroute.contracts.v1.cache_service`

- **Status:** Current public wire API.
- **Exports — requests:** `ArtifactRequest`, `GetCacheObservationRequest`, `LookupArtifactRequest`, `LookupTokensRequest`, `OperationIntentRequest`, `CreatePrefetchIntentRequest`, `CreatePinIntentRequest`, `CreateUnpinIntentRequest`, `CreateClearIntentRequest`, `CreateRebuildIntentRequest`, `GetOperationStatusRequest`, `CancelOperationRequest`, `GetLMCacheEndpointsRequest`, `GetTierAndAdapterSummaryRequest`, `GetMaintenanceStatusRequest`.
- **Exports — summaries/types:** `TokenCoverage`, `SummaryBase`, `AdapterSummary`, `TierLevel`, `CapacityUsageObservation`, `TierSummary`, `MaintenanceSummary`.
- **Exports — responses/constants:** `CacheServiceResponse`, `GatewayTargetedResponse`, `GetCacheObservationResponse`, `LookupArtifactResponse`, `LookupTokensResponse`, `OperationResponse`, `CreatePrefetchIntentResponse`, `CreatePinIntentResponse`, `CreateUnpinIntentResponse`, `CreateClearIntentResponse`, `CreateRebuildIntentResponse`, `GetOperationStatusResponse`, `CancelOperationResponse`, `GetLMCacheEndpointsResponse`, `GetTierAndAdapterSummaryResponse`, `GetMaintenanceStatusResponse`, `INTENT_OPERATION_TYPES`.
- **Request fields:** artifact requests require `artifact_…`; lookup tokens adds `TokenInput`; intents add non-empty idempotency key; status/cancel require `cacheop_…`; all targeted requests inherit runtime, request/correlation/time and endpoint provenance. Endpoint listing is not targeted.
- **Summary fields/invariants:** coverage requires total >=0 and ordered, non-overlapping ranges within total. All summaries carry non-empty source, UTC observed time, runtime/compatibility/endpoint provenance, `SupportState`, and `partial=False`; generation 0 is Legacy-only. Adapter/tier names are unique/non-empty. Unsupported/unknown summaries carry no measurements. `TierLevel` values are `l1`, `l2`; used capacity cannot exceed capacity and nested provenance/tier membership must match. Maintenance fields are optional active/eviction/detail.
- **Response fields/defaults:** envelope defaults success and contains optional target provenance, artifact, observation, operation, endpoint tuple, coverage, summaries and error. Target payloads require complete provenance; nested runtime/compatibility/endpoint/generation must match. Success forbids errors, non-success requires a matching error, stale cannot carry a fresh observation, cancellation requires cancelled/terminal semantics, and text fallback must be eligible.
- **Typed success invariants:** observation success requires fresh observation; artifact/token/operation success requires its payload; each intent response requires its exact operation kind; endpoint success requires endpoints; tier success requires adapter and tier summaries; maintenance success requires summary. `INTENT_OPERATION_TYPES` maps each intent request class to its operation enum.
- **Use / non-goals:** logical Cache Service facade, not physical blocks, backend exceptions, handlers, or proof of deployed wiring.
- **Evidence:** [`cache_service.py`](../../src/cacheroute/contracts/v1/cache_service.py), [`test/kdn/test_cache_service_contracts.py`](../../test/kdn/test_cache_service_contracts.py), [`test_contract_service_migration.py`](../../test/test_contract_service_migration.py).
- **Example:** `from cacheroute.contracts.v1.cache_service import GetLMCacheEndpointsRequest; from cacheroute.runtime import RuntimeProfile; request = GetLMCacheEndpointsRequest(runtime_profile=RuntimeProfile.V1)`

## API: `cacheroute.contracts.v1`

- **Status:** Current stable aggregate API.
- **Exports:** all names from `common`, `errors`, `knowledge`, and `cache_service` listed above: the three constants; `SupportState`, `utc_now`, bases/token types; error types; every knowledge request/response; every cache-service request/summary/response; and `INTENT_OPERATION_TYPES`.
- **Use / non-goals:** preferred aggregate import for v1 contracts; it adds no separate behavior.
- **Evidence:** [`v1/__init__.py`](../../src/cacheroute/contracts/v1/__init__.py), [`test_contract_foundation.py`](../../test/test_contract_foundation.py).
- **Example:** `from cacheroute.contracts.v1 import ResolveKnowledgeRequest, OutcomeCode, TokenInput`

## API: `cacheroute.compat.runtime`

- **Status:** Current public compatibility API.
- **Exports:** `RUNTIME_PROFILE_AUTO`, `RUNTIME_PROFILE_LEGACY`, `RUNTIME_PROFILE_TEST_MOCK`, `RUNTIME_PROFILE_V1`, `SUPPORTED_RUNTIME_PROFILES`, `classify_lmcache_redis_key`, `filter_supported_keys`, `normalize_runtime_profile`, `resolve_scan_match`.
- **Defaults/aliases:** normalization uses explicit value, otherwise `CACHEROUTE_RUNTIME_PROFILE`, otherwise `auto`; aliases `old`/`v0`→Legacy, `modern`/`new`/`current`→v1, `mock`/`test`→`test/mock`; unknown values fail. Legacy scan defaults `vllm@*`, other profiles `*`; an explicit non-sentinel pattern wins. Test/mock cannot select Redis.
- **Serialization/behavior:** plain strings, sets and bytes; key classification returns `legacy`, `v1`, or `None` without decoding exceptions crossing the API.
- **Use / non-goals:** select compatible Redis key layouts; not canonical cache state or Redis I/O.
- **Evidence:** [`compat/runtime.py`](../../src/cacheroute/compat/runtime.py), [`test_runtime_compat.py`](../../test/test_runtime_compat.py).
- **Example:** `from cacheroute.compat.runtime import normalize_runtime_profile; assert normalize_runtime_profile("modern") == "v1"`

## API: `cacheroute.compat`

- **Status:** Current public re-export API.
- **Exports:** `runtime` plus the same nine constants/functions as `cacheroute.compat.runtime` above; `runtime` is included by the computed `__all__`.
- **Compatibility:** `cacheroute_compat` and `cacheroute_compat.runtime` are deprecated identity-preserving forwards scheduled for removal in 0.3.0; `core.runtime_compat` is Transitional.
- **Evidence:** [`compat/__init__.py`](../../src/cacheroute/compat/__init__.py), [`test_runtime_compat.py`](../../test/test_runtime_compat.py), [`test_wheel_install.py`](../../test/test_wheel_install.py).
- **Example:** `from cacheroute.compat import resolve_scan_match; assert resolve_scan_match("legacy", None) == "vllm@*"`

## API: `cacheroute_compat`

- **Status:** Deprecated forwarding package; removal milestone 0.3.0.
- **Exports:** exact ten-name `cacheroute.compat.__all__` (`runtime` plus the nine runtime constants/functions); every object must be identical.
- **Use / non-goals:** old import compatibility only; contains no implementation.
- **Evidence:** [`cacheroute_compat/__init__.py`](../../src/cacheroute_compat/__init__.py), [`test_runtime_compat.py`](../../test/test_runtime_compat.py).
- **Example:** `import cacheroute_compat, cacheroute.compat; assert cacheroute_compat.normalize_runtime_profile is cacheroute.compat.normalize_runtime_profile`

## API: `cacheroute_compat.runtime`

- **Status:** Deprecated forwarding module; removal milestone 0.3.0.
- **Exports:** exact nine-name `cacheroute.compat.runtime.__all__`, with object identity.
- **Evidence:** [`cacheroute_compat/runtime.py`](../../src/cacheroute_compat/runtime.py), [`test_wheel_install.py`](../../test/test_wheel_install.py).
- **Example:** `from cacheroute_compat.runtime import normalize_runtime_profile`

## API: `KDN contract forwarding modules`

- **Status:** Transitional identity-preserving service compatibility.
- **Exports:** `kdn_server.contracts` forwards the canonical common/error/knowledge/cache-service names listed above (except common's `ENDPOINT_ID_PATTERN`/`utc_now`). `kdn_server.contracts.knowledge` additionally preserves historical auxiliary exports `Literal`, Pydantic `Field`/`model_validator`, `CacheArtifact`, `VersionedMessage`, `ContractError`, and `OutcomeCode`. `kdn_server.contracts.cache_service` additionally preserves its explicitly listed stdlib/Pydantic/domain auxiliary exports. `common` and `errors` forward their imported canonical names although they have no explicit `__all__`.
- **Compatibility:** forwarded contract objects must be identical and retain fields, validation and wire serialization. These shims do not own business logic and have no removal date beyond the focused KDN migration milestone.
- **Evidence:** [`kdn_server/contracts/__init__.py`](../../kdn_server/contracts/__init__.py), [`knowledge.py`](../../kdn_server/contracts/knowledge.py), [`cache_service.py`](../../kdn_server/contracts/cache_service.py), [`test_contract_service_migration.py`](../../test/test_contract_service_migration.py), [`test_core_forward_export.py`](../../test/test_core_forward_export.py).
- **Example:** `from kdn_server.contracts.knowledge import ResolveKnowledgeRequest; from cacheroute.contracts.v1.knowledge import ResolveKnowledgeRequest as Canonical; assert ResolveKnowledgeRequest is Canonical`

## API: `cacheroute.observability`

- **Status:** Current dependency-light namespace, with an empty `__all__`.
- **Exports:** none. It is intentionally usable only as a namespace marker today.
- **Use / non-goals:** accepted owner for observability; importing it does not provide production instrumentation, propagation, collectors or exporters.
- **Evidence:** [`observability/__init__.py`](../../src/cacheroute/observability/__init__.py), [`test_namespace_layout.py`](../../test/test_namespace_layout.py).
- **Example:** `import cacheroute.observability; assert cacheroute.observability.__all__ == []`

## API: `cacheroute.observability.v1`

- **Status:** In review in PR #179 and absent from the current main baseline.
- **Exports:** none available on this branch. PR #179's proposed v1 contracts,
  clocks, process-local collector and Legacy projection must not be imported or
  described as Current until merged.
- **Non-goals/current limitations:** production instrumentation and cross-process propagation are not implemented by PR #179.
- **Evidence:** absence under [`src/cacheroute/observability`](../../src/cacheroute/observability/) and the namespace check in [`test_namespace_layout.py`](../../test/test_namespace_layout.py).
- **Example/reference:** review-only reference: [PR #179](https://github.com/AstraNetLab/CacheRoute/pull/179).
