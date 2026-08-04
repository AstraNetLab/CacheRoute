# Public API and data models

[Back to handbook](README.md). This catalog follows explicit `__all__` values;
imported implementation helpers are not automatically public. Canonical models
are frozen, reject extra fields, validate copies, and serialize through Pydantic.

## Module catalog

| Import path | Owner | Status / stability | Supported exports | Purpose and non-goals | Focused evidence |
|---|---|---|---|---|---|
| `cacheroute` | canonical namespace | Current, intentionally empty | none | Namespace root; not a convenience re-export surface. | [`src/cacheroute/__init__.py`](../../src/cacheroute/__init__.py) |
| `cacheroute.runtime` | runtime | Current public | `RuntimeProfile` | Resolved runtime identity; not deployment probing. | [`profiles.py`](../../src/cacheroute/runtime/profiles.py), [`test_runtime_compat.py`](../../test/test_runtime_compat.py) |
| `cacheroute.runtime.state` | runtime | Current selected public | `Snapshot`, `StateTransitionError`, `StrEnum` | Immutable state foundation; helper functions are internal despite being importable. | [`state.py`](../../src/cacheroute/runtime/state.py), [`test_domain_state_migration.py`](../../test/test_domain_state_migration.py) |
| `cacheroute.topology` | topology | Current public | `LMCacheEndpoint`, `LMCacheGatewayProfile` | Logical endpoint identity; not live discovery. | [`lmcache.py`](../../src/cacheroute/topology/lmcache.py) |
| `cacheroute.cache` | cache | Current public | `CacheArtifact`, `CacheReplicaObservation`, `CacheOperationTask` and their state/source/type enums | Logical models; no LMCache/Redis operations. | [`models.py`](../../src/cacheroute/cache/models.py) |
| `cacheroute.routing` | routing | Current public | `QueueState`, `QueueWork` | Reusable lifecycle state; not Proxy process queue implementation. | [`queue.py`](../../src/cacheroute/routing/queue.py) |
| `cacheroute.contracts` | contracts | Current public | `v1` | Version namespace only. | [`contracts/__init__.py`](../../src/cacheroute/contracts/__init__.py) |
| `cacheroute.contracts.v1` | contracts | Current stable v1 surface | common, error, knowledge, and cache-service exports | Immutable JSON wire vocabulary; not handlers or backend APIs. | [`v1/__init__.py`](../../src/cacheroute/contracts/v1/__init__.py), [`test_contract_foundation.py`](../../test/test_contract_foundation.py) |
| `cacheroute.contracts.v1.common` | contracts | Current public | versions, endpoint pattern, support state, base messages and token input | Common envelopes and storage-neutral token input. | [`common.py`](../../src/cacheroute/contracts/v1/common.py) |
| `cacheroute.contracts.v1.errors` | contracts | Current public | `OutcomeCode`, `ContractErrorDetail`, `ContractError` | Safe wire failures, never backend exceptions. | [`errors.py`](../../src/cacheroute/contracts/v1/errors.py) |
| `cacheroute.contracts.v1.knowledge` | contracts | Current public | knowledge descriptors, request/response aliases | Storage-neutral knowledge facade contracts, not registration implementation. | [`knowledge.py`](../../src/cacheroute/contracts/v1/knowledge.py), [`test_contract_service_migration.py`](../../test/test_contract_service_migration.py) |
| `cacheroute.contracts.v1.cache_service` | contracts | Current public | cache requests/responses, summaries, enums, intent mapping | Logical facade contracts; excludes physical block/index vocabulary. | [`cache_service.py`](../../src/cacheroute/contracts/v1/cache_service.py), [`test/kdn/test_cache_service_contracts.py`](../../test/kdn/test_cache_service_contracts.py) |
| `cacheroute.compat` / `cacheroute.compat.runtime` | compat | Current public compatibility | profile constants and normalization/key-layout helpers | Compatibility selection, not canonical domain state. | [`compat/runtime.py`](../../src/cacheroute/compat/runtime.py) |
| `cacheroute_compat` / `.runtime` | compatibility shim | Deprecated; remove at 0.3.0 | identity-preserving forwards of `cacheroute.compat` | Old import only; no implementation. | [`cacheroute_compat/__init__.py`](../../src/cacheroute_compat/__init__.py), [`test_runtime_compat.py`](../../test/test_runtime_compat.py) |
| `kdn_server.contracts` and submodules | KDN forwarding shims | Transitional | canonical v1 contract objects plus documented auxiliary forwards | Old service imports; no duplicate models. | [`kdn_server/contracts`](../../kdn_server/contracts/), [`test_contract_service_migration.py`](../../test/test_contract_service_migration.py) |
| `cacheroute.observability` | observability | Current empty namespace | none | Reserved dependency-light owner, not evidence of wired tracing. | [`observability/__init__.py`](../../src/cacheroute/observability/__init__.py) |
| `cacheroute.observability.v1` | observability | In review (PR #179), absent here | none on current baseline | Do not import or describe as current until merged. | [`test_namespace_layout.py`](../../test/test_namespace_layout.py) |

## Runtime, topology, cache, and routing models

`RuntimeProfile` wire values are `v1`, `legacy`, `test/mock`, and startup-only
`auto`. `normalize` accepts compatibility aliases; `resolve_startup("auto")`
chooses `v1` when available and otherwise `legacy`.

`LMCacheEndpoint` fields are `endpoint_id: str | None` (computed), `name: str`,
`runtime_profile=RuntimeProfile.V1`, required `gateway_profile` and
`compatibility_profile_id`, `generation: int=1` (minimum 1), and optional
`adapter`/`tier`. Its ID is deterministic `endpoint_` plus 32 lowercase hex
characters from the endpoint name. Gateway values are `mp_http_api`,
`mp_coordinator`, `mp_sdk`, `mp_metrics_events`, `legacy_gateway`, `mock`, and
`unknown_future`.

`CacheArtifact` requires knowledge/model/tokenizer/cache-data/compatibility
identity; defaults are artifact version `1`, adapters `()`, runtime `v1`, schema
`v1`, and current UTC creation time. Its deterministic ID is `artifact_` plus 32
hex characters. `CacheReplicaObservation` binds an artifact to an endpoint
incarnation and freshness window. Observation states are `pending`, `available`,
`unavailable`, `unknown`, `partial`; confidence is `low`, `medium`, `high`;
sources are `http_api`, `coordinator`, `sdk`, `metrics_event`,
`legacy_projection`, `mock`. Legacy projections alone may use generation zero.

`CacheOperationTask.task_id` is `cacheop_` plus 32 lowercase hex characters.
Operations are `lookup`, `prefetch`, `pin`, `unpin`, `clear`, `rebuild`,
`observe`; states are `pending`, `running`, `retry_wait`, `succeeded`, `failed`,
`cancelled`. It defaults to pending, attempt zero, runtime v1, and UTC timestamps;
transition rules reject backwards time and invalid terminal transitions.

`QueueWork.work_id` is `queuework_` plus 32 lowercase hex characters and requires
an idempotency key and `cacheop_…` task ID. States are `queued`, `claimed`,
`executing`, `retry_wait`, `completed`, `failed`, `cancelled`, with validated
transitions. These formats are source-defined, not inferred from examples.

## Contract v1 details

`VersionedMessage` defaults `contract_version="kdn.v1"`, `request_id` to
`req_` plus 32 hex characters, `correlation_id=None`, and `timestamp` to UTC;
`runtime_profile` is required and cannot be `auto`. Requests targeting a gateway
also require non-empty compatibility profile, `endpoint_…` ID, and generation;
generation zero is Legacy-only. `TokenInput` requires exactly one of a non-empty
tuple of non-negative inline token IDs or a `TokenReference`.

`SupportState` values are `supported`, `unsupported`, `unknown`. `OutcomeCode`
values are `success`, `unsupported`, `incompatible`, `stale`, `partial`,
`failed`, `cancelled`, `text_fallback`, and `idempotency_conflict`. Non-success
knowledge responses require a matching error; text fallback must explicitly be
fallback-eligible. Cache-service success responses validate the payload and
endpoint/artifact/operation provenance. Full fields and validators remain
canonical in the linked source rather than duplicated here.

## Copyable examples

```python
from cacheroute.runtime import RuntimeProfile
from cacheroute.topology import LMCacheEndpoint, LMCacheGatewayProfile

profile = RuntimeProfile.resolve_startup("auto", v1_available=True)
endpoint = LMCacheEndpoint(
    name="local-lmcache",
    runtime_profile=profile,
    gateway_profile=LMCacheGatewayProfile.MP_HTTP_API,
    compatibility_profile_id="local-v1",
)
print(endpoint.model_dump(mode="json"))
```

```python
from cacheroute.contracts.v1 import ResolveKnowledgeRequest
from cacheroute.runtime import RuntimeProfile

request = ResolveKnowledgeRequest(
    runtime_profile=RuntimeProfile.V1,
    knowledge_id="manual-example",
)
wire_json = request.model_dump_json()
```

```python
from cacheroute.compat import normalize_runtime_profile, resolve_scan_match

assert normalize_runtime_profile("modern") == "v1"
assert resolve_scan_match("legacy", None) == "vllm@*"
```

## Public implementation-module paths

The explicit export lists also support these focused implementation imports:
`cacheroute.runtime.profiles`, `cacheroute.topology.lmcache`,
`cacheroute.cache.models`, and `cacheroute.routing.queue`. Their exports are the
same named objects described for their package re-export above.
