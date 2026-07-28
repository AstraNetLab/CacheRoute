# CacheRoute v0.2.0 Evolution Plan

> Status: Planning draft  
> Current release baseline: v0.1.9  
> Current development baseline: `v1` (vLLM 0.25.1 + LMCache 0.5.2 + PyTorch 2.11.0)  
> Compatibility path: `legacy` remains runnable but feature-frozen  
> Target release: v0.2.0  
> Core foundation: vLLM + LMCache  
> Core positioning: KDN knowledge control, a CacheRoute cache-service facade, an LMCache orchestration gateway, Proxy multi-resource execution orchestration, knowledge-aware cache policy, and multi-block reuse

## 0. Planning Decisions

This roadmap establishes the following long-term boundary:

> **KDN Server = Knowledge Control Plane + CacheRoute Cache Service Facade + LMCache Orchestration Gateway.**

The v1 high-frequency KV data path remains:

```text
vLLM == LMCacheMPConnector == LMCache MP == L1 / L2 adapters
```

KDN is independently deployable, scalable, and managed by Scheduler, but it is not the default v1 physical KV data server. It does not duplicate LMCache Token Database, chunk/hash/key generation, L1/L2 StorageManager, adapter cascades, Store/Prefetch Controller, serde, locking, capacity, or eviction.

KDN differentiates CacheRoute through:

1. KnowledgeObject, CacheArtifact, and knowledge-version semantics;
2. model, tokenizer, adapter, KV-layout, and LMCache Profile compatibility;
3. knowledge-level lookup, prefetch, pin, clear, and rebuild intents;
4. multi-LMCache-endpoint selection, idempotent tasks, audit, authorization, and fallback;
5. normalized LMCache observations with TTL, confidence, and request-value feedback;
6. Proxy CachePlan, ExecutionGraph, queues, and network-compute overlap.

### 0.1 Runtime Profile Policy

- `v1`: the only development path for new features; uses LMCache MP and public control/observation interfaces.
- `legacy`: preserves old startup, Redis scan/dump/restore/inject, request, and experiment paths; feature-frozen.
- `auto`: migration discovery at startup only; it must resolve and freeze one explicit Profile.
- A v1 request never silently enters a Legacy write path.
- Legacy data enters v1 only through explicit migration or rebuild.

### 0.2 Current Issue Treatment

| Item | Roadmap treatment |
|---|---|
| #148 / PR #149 / PR #151 | completed v1 environment, MP startup, and documentation baseline |
| #138 / PR #143 | completed Instance Capability Fingerprints |
| #139 | define v1 Runtime, Artifact, LMCache Observation, Operation Task, and Queue states |
| #140 | define the KDN Cache Service Facade and LMCache Gateway contracts |
| #141 | add unified Gateway, Tier, Adapter, Queue, and vLLM observability |
| #142 | add v1/Legacy dual-Profile and Gateway regression validation |
| Closed PRs | not treated as the implementation migration base for #139–#142 |

### 0.3 Non-Negotiable Principles

- CacheRoute does not duplicate LMCache Token DB, chunk index, allocator, serde, locks, or physical transfer implementation.
- KDN APIs exchange knowledge semantics, logical references, operation intents, observation summaries, and task state; they do not carry large KVCache payloads.
- LMCache release and interface differences appear only in Gateway Adapters, factories, and immutable Capability Snapshots.
- Scheduler, Proxy, KnowledgeObject, CacheArtifact, and ExecutionGraph do not import LMCache private classes.
- Redis belongs only to the Legacy boundary or to an adapter loaded by LMCache; it is not KDN identity.
- Unknown capabilities are not assumed to be supported. Missing capabilities return `unsupported`, `incompatible`, or explicit fallback.
- LMCache Runtime is authoritative for physical state; KDN and Proxy retain only sourced, timestamped, TTL-bound observations.

## 1. Overall CacheRoute, KDN, vLLM, and LMCache Structure

### 1.1 Legend

```text
==  high-frequency request or KV data hot path
--  control, management, policy, or observation API
|   containment or component hierarchy
```

### 1.2 Global Component, Data-Path, and Control-Path Diagram

```text
+------------------- CacheRoute Client / Workload -------------------+
|                                                                     |
|  OpenAI-compatible request                                          |
+==============================+======================================+
                               |
                               v
+------------------------- CacheRoute Scheduler ----------------------+
| - Proxy / Instance selection                                        |
| - KDN endpoint selection                                            |
| - coarse routing and admission                                      |
+==================+===========================+-----------------------+
                   |                           |
                   | request route             | Knowledge API
                   v                           v
+---------------- CacheRoute Proxy ------------+      +--------------- KDN Server ----------------+
| - request queue / single-flight             |      |                                               |
| - CachePlan / ExecutionGraph                 |      | +-- Knowledge Control Plane                 |
| - text fallback                              |      | |   - KnowledgeObject / version             |
+==================+===========================+      | |   - CacheArtifact / compatibility         |
                   |                                  | |   - desired state / policy / audit        |
                   | request execution                | |                                             |
                   v                                  | +-- Cache Service Facade                    |
+---------------- CacheRoute Instance ---------+      | |   - LookupArtifact / LookupTokens          |
| - Instance Capability                        |      | |   - Prefetch / Pin / Clear / Rebuild intent|
| - vLLM request forwarding                    |      | |   - operation status / normalized view     |
| - LMCache hit-token and remote-read report   |      | |                                             |
+==================+===========================+      | +-- LMCache Orchestration Gateway           |
                   |                                  |     - MPHTTPGateway                          |
                   | OpenAI request                   |     - MPCoordinatorGateway                   |
                   v                                  |     - MPSDKGateway                           |
+------------------------- vLLM ----------------+      |     - MPMetricsEventGateway                  |
| model execution / prefill / decode            |      +-------------------+---------------------------+
+==================+=============================+                          |
                   | LMCacheMPConnector KV path                             | LMCache public control APIs
                   v                                                        |
+---------------------- LMCache MP Runtime ---------------------------------+--------------------------+
|                                                                                                      |
|  +-- Token DB / token-hash lookup                                                                  |
|  +-- L1 memory tier                                                                                |
|  +-- L2 adapter cascade                                                                           |
|  |   +-- Redis / Valkey / Mooncake / NIXL / FS / object store / custom plugin                     |
|  +-- Store / Retrieve / Prefetch                                                                  |
|  +-- Pin / Unpin / Clear / operation status                                                       |
|  +-- capacity / quota / eviction / metrics / events                                                |
|                                                                                                      |
+======================================================================================================+

Control relations outside the KV hot path:
Scheduler / Proxy / Instance -- Knowledge API / Cache Service API --> KDN
KDN -- MP HTTP / Coordinator / SDK / Metrics / Events -------------> LMCache MP
LMCache MP -- observations / operation results ---------------------> KDN
KDN -- normalized observations / policy results --------------------> Scheduler / Proxy / Instance
```

The diagram captures two non-interchangeable facts:

1. `vLLM == LMCacheMPConnector == LMCache MP` is the v1 KV data hot path;
2. KDN manages and observes LMCache through `--` interfaces and does not sit in the per-chunk transfer path.

## 2. Formal Positioning of KDN Server

### 2.1 Three-Layer Structure

```text
KDN Server
|
+-- Knowledge Control Plane
|   |-- KnowledgeObject / version
|   |-- CacheArtifact / compatibility
|   |-- desired state / policy
|   |-- audit / authorization
|   +-- access value / request outcome
|
+-- CacheRoute Cache Service Facade
|   |-- cache and token observations
|   |-- prefetch / pin / clear / rebuild intent
|   |-- logical operation status
|   +-- structured fallback and errors
|
+-- LMCache Orchestration Gateway
    |-- CapabilityFactory / AdapterFactory
    |-- MP HTTP / Coordinator / SDK
    |-- Metrics / Events
    |-- Mock Gateway
    +-- LegacyCacheAdapter
```

The layers answer different questions:

- **Knowledge Control Plane**: why the cache exists, which knowledge it represents, and which policy applies;
- **Cache Service Facade**: which stable domain operations CacheRoute requires;
- **LMCache Orchestration Gateway**: how the active LMCache release and interfaces execute or observe the operation.

### 2.2 KDN Owns

- KnowledgeObject content, version, and semantics;
- KnowledgeObject-to-CacheArtifact and token-reference mappings;
- Artifact compatibility and invalidation reasons;
- desired Prefetch, Pin, Clear, and Rebuild state;
- coarse selection across LMCache Endpoints;
- CacheOperationTask idempotency, audit, authorization, cancellation, and fallback;
- normalized LMCache observations with TTL and confidence;
- hit value, compute savings, and maintenance feedback.

### 2.3 LMCache Owns

- token chunking, hashes, chunk keys, and physical KV objects;
- L1/L2 residency and adapter cascades;
- Store, Retrieve, Prefetch, Pin, Unpin, and Clear;
- serde, locking, capacity, quota, and eviction;
- physical operation completion;
- actual hit tokens, remote reads, metrics, and events.

### 2.4 KDN Is Not Redis or a Second LMCache

The following must not enter stable KDN domain models:

```text
Redis URL / password / raw key
LMCache private Python class
LMCache internal Chunk Key
physical KV payload
private serialized object
physical chunk-index copy
```

Legacy Redis operations are encapsulated behind `LegacyCacheAdapter`. v1 code does not extend the current Redis Injector with token lookup, tiers, adapters, prefetch, or pin logic.

## 3. KDN APIs and the LMCache Gateway

### 3.1 API Layering and Mapping Diagram

```text
CacheRoute callers
|-- Scheduler
|-- Proxy
|-- Instance
|-- management / experiment tools
|
+-- Knowledge API --------------------------------------------------------------+
|   |-- RegisterKnowledge                 == KDN domain implementation           |
|   |-- UpdateKnowledgeVersion            == KDN domain implementation           |
|   |-- ResolveKnowledge                  == KDN domain implementation           |
|   |-- ListCompatibleArtifacts           == KDN catalog + compatibility          |
|   |-- GetPolicyDecision                 == KDN policy                           |
|   +-- ReportRequestOutcome              == KDN statistics / feedback           |
|                                                                                |
+-- Cache Service API ----------------------------------------------------------+
    |-- GetCacheObservation   -- Gateway --> LMCache status / metrics / events   |
    |-- LookupArtifact        -- Gateway --> token lookup + KDN Artifact mapping |
    |-- LookupTokens          -- Gateway --> LMCache token/hash lookup           |
    |-- CreatePrefetchIntent  -- Gateway --> MP HTTP / Coordinator / SDK         |
    |-- CreatePinIntent       -- Gateway --> Pin API / Coordinator               |
    |-- CreateUnpinIntent     -- Gateway --> Unpin API / Coordinator             |
    |-- CreateClearIntent     -- Gateway --> cache-object clear/delete           |
    |-- CreateRebuildIntent   -- KDN task --> LMCache-backed rebuild workflow    |
    |-- GetOperationStatus    -- Gateway --> operation/task status               |
    |-- CancelOperation       -- Gateway --> cancellation when supported         |
    |-- GetLMCacheEndpoints   -- Gateway --> endpoint/config/capability discovery|
    |-- GetTierAndAdapterSummary -- Gateway --> L1/L2/adapter/config/metrics      |
    +-- GetMaintenanceStatus  -- Gateway --> quota/eviction/health observations  |
```

### 3.2 Mapping Rule

```text
CacheRoute Domain Request
        |
        v
KDN versioned API
        |
        v
CacheOperationTask / CacheReplicaObservation
        |
        v
LMCacheCompatibilityProfile + CapabilitySnapshot
        |
        +-- supported ----> versioned Gateway Adapter ----> LMCache public API
        |
        +-- unsupported --> structured unsupported / explicit text fallback
        |
        +-- incompatible -> reject reuse / migrate / rebuild
```

### 3.3 Knowledge API

```text
RegisterKnowledge
UpdateKnowledgeVersion
ResolveKnowledge
ListCompatibleArtifacts
GetPolicyDecision
ReportRequestOutcome
```

### 3.4 Cache Service API

```text
GetCacheObservation
LookupArtifact
LookupTokens
CreatePrefetchIntent
CreatePinIntent
CreateUnpinIntent
CreateClearIntent
CreateRebuildIntent
GetOperationStatus
CancelOperation
GetLMCacheEndpoints
GetTierAndAdapterSummary
GetMaintenanceStatus
```

Stable parameters use Knowledge IDs, Artifact IDs, token sequences or token references, Instance Capability, LMCache Endpoint IDs, and logical operation IDs.

### 3.5 Gateway Internal Structure

```text
KDN Cache Service Facade
          |
          v
+---------------- LMCache Orchestration Gateway ----------------+
|                                                               |
|  CapabilityFactory                                            |
|  |-- detect LMCache version / build                           |
|  |-- detect endpoint generation                               |
|  |-- probe routes / metrics / events                          |
|  +-- build immutable CapabilitySnapshot                       |
|                                                               |
|  AdapterFactory                                               |
|  |-- MPHTTPGateway --------> health/config/cache/prefetch API  |
|  |-- MPCoordinatorGateway -> multi-server/pin/quota/eviction   |
|  |-- MPSDKGateway ---------> typed lookup/operation calls      |
|  |-- MPMetricsEventGateway -> hit tokens/reads/events/status   |
|  |-- MockGateway ----------> CPU-only contract tests           |
|  +-- LegacyCacheAdapter ---> legacy Redis compatibility only   |
|                                                               |
|  optional                                                     |
|  +-- L2PluginGateway ------> only for a proven capability gap  |
+---------------------------------------------------------------+
          |
          v
LMCache MP public interfaces and loaded adapters
```

### 3.6 Startup Capability Discovery

At startup, the v1 Gateway should:

1. query LMCache version, build ID, and runtime mode;
2. query config, connector, and loaded adapters;
3. probe required HTTP routes, SDK methods, metrics, and events;
4. build an immutable `CapabilitySnapshot`;
5. validate chunk size, hash, layout, serde, tier, and completion profiles;
6. create an `EndpointGeneration`;
7. record the Profile in Instance Capability and traces.

Unknown capability is never treated as supported. An LMCache route rename or minor-release change replaces a Gateway Adapter rather than changing KDN domain objects.

## 4. v1, Legacy, and Auto Boundaries

### 4.1 Runtime Profile Split Diagram

```text
                         process startup
                               |
                               v
                    CACHEROUTE_RUNTIME_PROFILE
                               |
              +----------------+----------------+
              |                                 |
           explicit                           auto
        v1 / legacy                             |
              |                        detect environment once
              |                                 |
              +----------------+----------------+
                               |
                         freeze profile
                               |
          +====================+====================+
          |                                         |
          v                                         v
+--------------------- v1 ----------------+  +---------------- Legacy ----------------+
| new development                         |  | compatibility-only                     |
|                                         |  |                                        |
| KDN Cache Service Facade                |  | LegacyCacheAdapter                     |
|        -- LMCache Gateway               |  |        -- Redis scan/dump/restore      |
|        -- MP HTTP/Coordinator/SDK       |  |        -- historical KV injection      |
|        -- Metrics/Events                |  |        -- legacy startup/request       |
|                                         |  |                                        |
| vLLM == LMCacheMPConnector == LMCache MP|  | old vLLM/LMCache/Redis path            |
+-----------------------------------------+  +----------------------------------------+
          |                                         |
          +-- no implicit Legacy write fallback ----+
          +-- migration/rebuild must be explicit ---+
```

### 4.2 v1

- All new features target v1 only.
- The Gateway uses LMCache public control and observation interfaces.
- New code does not scan, copy, or infer Redis keys directly.
- Missing capabilities produce structured failure or explicit text fallback.
- Actual reuse is confirmed through hit-token or remote-read observation.

### 4.3 Legacy

- Preserve Redis scan/dump/restore/inject, old startup, and old request paths.
- Feature-freeze the path and accept only availability, security, critical-defect, and compatibility fixes.
- Legacy keys and directories do not become v1 Artifact identities.
- Legacy physical operations appear only inside `LegacyCacheAdapter`.

### 4.4 Auto

```text
auto --> v1
```

or:

```text
auto --> legacy
```

The resolved Profile is immutable for the process lifetime and cannot change dynamically based on requests or key existence.

## 5. Authority and Overall Role Boundaries

| Information | Authority |
|---|---|
| KnowledgeObject content, version, and semantics | KDN Knowledge Control Plane |
| KnowledgeObject-to-CacheArtifact relationship | KDN Knowledge Control Plane |
| Artifact compatibility and invalidation reason | KDN Knowledge Control Plane |
| desired Prefetch, Pin, Clear, and Rebuild state | KDN Policy |
| LMCache Endpoint, interfaces, and capability Profile | Gateway Capability Snapshot |
| tokens, chunks, hashes, keys, physical KV, layout, and serde | LMCache Runtime |
| L1/L2, adapters, capacity, quota, and eviction | LMCache Runtime |
| physical operation completion | LMCache Runtime Observation |
| actual local hit tokens | Instance-side LMCache |
| request waiting, bypass, and compute release | Proxy |
| coarse Proxy, Instance, and KDN Endpoint selection | Scheduler |

Every physical observation carries:

```text
observation_source
observed_at
expires_at
endpoint_generation
lmcache_profile_id
adapter_or_tier
confidence
```

## 6. Core Objects

### 6.1 RuntimeProfile

```text
profile_id
resolved_mode
source
resolved_at
immutable
```

Persisted active modes are `v1`, `legacy`, or `mock/test`; `auto` is startup input only.

### 6.2 LMCacheCompatibilityProfile

```text
profile_id
lmcache_version_range
integration_family
protocol_version
configuration_schema_version
connector_profile
key_format_version
layout_profile
serde_profile
chunk_size_profile
supported_operations
batching_capabilities
locking_model
completion_model
event_model
cancellation_model
status
validated_at
```

Recommended `integration_family` values:

```text
mp_http_api
mp_coordinator
mp_sdk
mp_metrics_events
mp_l2_plugin
legacy_redis
mock
unknown_future
```

Profile status:

```text
experimental
validated
default
deprecated
unsupported
```

### 6.3 LMCacheEndpoint

```text
endpoint_id
runtime_profile
lmcache_profile_id
endpoint_generation
api_endpoints
loaded_adapters
capability_snapshot
health
capacity_summary
last_observed_at
```

### 6.4 KnowledgeObject

```text
knowledge_id
content_hash
content_version
text_location
embedding
embedding_model
semantic_metadata
tokenization_hints
created_at
updated_at
```

### 6.5 CacheArtifact

```text
artifact_id
knowledge_id
capability_fingerprint
model_fingerprint
tokenizer_fingerprint
adapter_fingerprint
kv_layout_profile
kv_dtype
parallelism_profile
lmcache_data_profile
key_format_version
serde_profile
desired_state
policy_state
created_at
updated_at
```

An Artifact is a logical materialization identity under a knowledge and compatibility environment. It does not store KV bytes.

### 6.6 CacheReplicaObservation

```text
observation_id
artifact_id
lmcache_endpoint_id
runtime_profile
lmcache_profile_id
adapter_or_tier
observed_state
hit_coverage
health
observation_source
observed_at
expires_at
endpoint_generation
confidence
```

It is a TTL-bound physical observation, not a CacheRoute-owned replica or chunk index.

### 6.7 CacheOperationTask

```text
task_id
idempotency_key
operation
artifact_id
endpoint_id
runtime_profile
lmcache_profile_id
state
priority
requested_at
started_at
finished_at
observed_bytes
observed_tokens
result_source
result
error
```

### 6.8 CachePlan / FusionPlan

```text
request_id
target_instance_id
knowledge_blocks
matched_artifacts
lmcache_endpoints
cache_observations
lookup_tasks
prefetch_tasks
fusion_mode
recompute_ranges
fallback_mode
plan_state
trace_context
```

### 6.9 ExecutionGraph

```text
node_id
request_id
work_type
resource_class
depends_on
share_key
priority
deadline
estimated_cost
actual_cost
state
fallback
```

Resource classes:

```text
CONTROL
KDN_LOOKUP
LMCACHE_GATEWAY
NET_KV
CACHE_LOAD
PREFILL
DECODE
FUSION
```

## 7. Iteration Overview

| Version | Theme | Main delivery |
|---|---|---|
| v0.1.10 | v1/Legacy contract and observation baseline | RuntimeProfile, Gateway Profile, core states, traces, Legacy projection |
| v0.1.11 | Knowledge Control + LMCache Observation | Knowledge/Artifact, token mapping, endpoint/adapter/tier observations |
| v0.1.12 | LMCache-backed KDN Cache Service MVP | MP HTTP/Coordinator Gateway, Lookup/Prefetch/Pin/Clear |
| v0.1.13 | Multi-tier, multi-adapter, and release compatibility | adapter cascade observation, capacity/eviction observation, compatibility matrix, recovery/rebuild |
| v0.1.14 | Proxy KVCache Manager | short-lived Instance view and single-flight from KDN/LMCache observations |
| v0.1.15 | Injection and compute queue model | ExecutionGraph, resource queues, Compute Fast Path |
| v0.1.16 | Parallel network and compute | work-conserving pipeline and overlap benchmark |
| v0.1.17 | Queue stability and generality | admission, backpressure, fairness, aging, adaptive concurrency |
| v0.1.18 | KDN knowledge-aware policy | Prefetch/Pin/Clear/Rebuild intents, value model, replay |
| v0.1.19 | Multi-block non-prefix fusion | parallel token/artifact lookup, selective recomputation, quality fallback |
| v0.2.0 | Integrated research baseline | v1 default, Legacy preserved, cross-LMCache compatibility, complete experiment loop |

## 8. Per-Version Plan

## v0.1.10: v1/Legacy Contract and Observation Baseline

### Goal

Freeze stable vocabulary for later work:

- RuntimeProfile;
- LMCacheCompatibilityProfile;
- LMCacheEndpoint and CapabilitySnapshot;
- CacheArtifact and CacheReplicaObservation;
- CacheOperationTask;
- QueueWork, trace sources, and stages;
- read-only Legacy `kv_ready` and Redis compatibility projection.

### Acceptance

- Completed #138 Capability remains compatible.
- `auto` resolves and freezes at startup.
- v1 operations cannot silently invoke a Legacy write adapter.
- Core objects contain no KV bytes, raw Redis keys, credentials, or LMCache private classes.
- Token lookup, prefetch, pin, and clear are represented as LMCache-backed operations.
- CPU-only tests use Mock Gateways and require no external services.

## v0.1.11: Knowledge Control and LMCache Observation

### Main Steps

1. Implement KnowledgeObject and version management.
2. Allow one KnowledgeObject to map to multiple CacheArtifacts.
3. Map KnowledgeObjects to token references and Artifacts.
4. Evaluate Artifact compatibility through Capability and LMCache Data Profiles.
5. Separate Desired State from LMCache Observation.
6. Build LMCacheEndpoint, Adapter, and Tier registries.
7. Record source, Profile, Generation, timestamp, and TTL for every physical observation.
8. Let Scheduler consume only coarse knowledge and Endpoint availability.
9. Map Legacy `kv_ready` into a read-only observation with `compatibility=unknown`.

### Acceptance

- One knowledge item supports multiple models, adapters, and LMCache Profiles.
- KDN does not access or copy physical KV data.
- Expired observations are no longer authoritative.
- Redis does not appear in stable v1 domain models.

## v0.1.12: LMCache-Backed KDN Cache Service MVP

### Main Steps

1. Implement versioned KDN Knowledge and Cache Service APIs.
2. Implement `MPHTTPGateway`.
3. Implement the minimum `MPCoordinatorGateway` capability set.
4. Implement LookupTokens, GetCacheObservation, Prefetch, Pin, Unpin, Clear, and OperationStatus.
5. Build CapabilityFactory and AdapterFactory.
6. Implement Mock Gateways for CPU-only CI.
7. Validate actual reuse using LMCache hit-token or remote-read observations.
8. Return `unsupported` or explicit fallback when a capability is missing.
9. Do not implement a physical KV store or per-chunk data path in KDN.

### Acceptance

- vLLM and LMCache MP retain the direct data path.
- KDN maps stable domain operations to LMCache public interfaces.
- Gateway replacement does not change KnowledgeObject, CacheArtifact, or CachePlan.
- Failure can fall back to text computation with a structured reason.
- Legacy behavior remains unchanged.

## v0.1.13: Multi-Tier, Multi-Adapter, and LMCache Release Compatibility

### Main Steps

1. Discover and observe multiple L2 adapters and tiers.
2. Reuse LMCache adapter cascades, capacity, quota, and eviction.
3. Build a Compatibility Matrix and Gateway Conformance Suite.
4. Support baseline, latest, Legacy, and unknown-future Profiles.
5. Implement Endpoint Generation, reconnect, and observation invalidation.
6. Implement Profile upgrade, downgrade, and deprecation status.
7. Migrate or rebuild incompatible key/layout/serde data.
8. Add an L2 Plugin only after proving a real LMCache capability gap.
9. Add periodic validation for LMCache minor releases.

### Acceptance

- At least two adapter/tier configurations are representable.
- LMCache interface changes modify only Gateway Adapters.
- Incompatible upgrades never silently reuse old Artifacts.
- KDN does not implement its own adapter cascade, capacity, or eviction thread.

## v0.1.14: Proxy KVCache Manager

### Main Steps

1. Build an Instance Cache Observation View.
2. Sources include KDN observations, LMCache events, Gateway results, and actual hits.
3. States include UNKNOWN, REMOTE_AVAILABLE, PREPARING, LOCAL_AVAILABLE, STALE, and FAILED.
4. Implement single-flight per Artifact/Instance.
5. Invalidate on Endpoint, Instance, or Profile Generation changes.
6. Proxy does not copy the LMCache chunk index.

### Acceptance

- Proxy distinguishes remote availability, preparation, local availability, and staleness.
- One preparation task serves concurrent waiters.
- Actual hits are confirmed through LMCache-native observations.

## v0.1.15: Knowledge Injection and Compute Queue Model

- Compile CachePlan into ExecutionGraph.
- Include Control, KDN Lookup, LMCache Gateway, Network KV, Cache Load, Prefill, Decode, and Fusion nodes.
- Define dependency, Share Key, priority, deadline, cost, and fallback.
- Text tasks use a Compute Fast Path.
- Scheduler does not execute fine-grained nodes.

## v0.1.16: Parallel Network KV and Pure Compute

- Create independent concurrency domains for Control, Gateway, Network, Cache Load, and Compute.
- Overlap network KV with other-request Prefill/Decode.
- Remain work-conserving while requests wait for KV.
- Add network-compute Gantt and Overlap Ratio.
- Support cancellation, timeout, and fallback.

## v0.1.17: Queue Generality and Stability

- Admission control and backpressure.
- Fairness, aging, and starvation guards.
- Adaptive concurrency.
- Single-flight lifecycle.
- Test across models, Instances, KDNs, bandwidths, and workload mixes.
- Policy plugins cannot break state-machine correctness.

## v0.1.18: KDN Knowledge-Aware Cache Policy

### Inputs

- knowledge access frequency and co-occurrence;
- LMCache token lookup, metrics, and events;
- Endpoint, adapter, and tier capacity and health;
- Proxy waiting and GPU idle;
- network cost and compute savings;
- build, refresh, and migration cost;
- Artifact compatibility and version;
- online and background load.

### Outputs

```text
BUILD
PREFETCH
PIN
UNPIN
CLEAR
REFRESH
REBUILD
MIGRATE
REPLICATE_INTENT
```

### Requirements

- Every decision has a Reason Code.
- Prevent pollution and oscillation.
- Prioritize online SLOs.
- Support shadow, replay, and controlled enablement.
- Do not operate on LMCache or Provider private keys.
- Compile knowledge-policy intents into LMCache public operations.

## v0.1.19: Multi-Knowledge-Block Non-Prefix Fusion

- Resolve multiple knowledge blocks per request.
- Parallelize Artifact Resolve and token/cache lookup.
- Plan Full/Partial/Overlap/Reorder uniformly.
- Use LMCache non-prefix reuse, CacheBlend, or an equivalent public capability.
- Selectively recompute required tokens.
- Add multi-block preparation to ExecutionGraph.
- Fall back to text on unsupported capability, quality failure, or timeout.
- Compare serial loading, parallel loading, pure text, and single-prefix reuse.

## v0.2.0: Integration, Stability, and Research Baseline

v0.2.0 is complete when:

- v1 is the default development and experiment path;
- Legacy remains runnable with an explicit deprecation policy;
- KDN deploys independently as Knowledge Control + Cache Service Facade + LMCache Gateway;
- the vLLM-LMCache MP data hot path does not cross KDN business services;
- at least baseline and latest LMCache Profiles are validated;
- at least two adapter/tier configurations are represented;
- Proxy uses short-lived observations rather than an authoritative Block Index;
- network KV and pure compute overlap;
- queues support single-flight, backpressure, fairness, cancellation, and fallback;
- at least two knowledge blocks support non-prefix reuse;
- KDN includes at least one knowledge-value policy;
- critical failure and upgrade scenarios have reproducible tests;
- text, single-knowledge, and Legacy paths remain compatible.

## 9. LMCache Evolution Compatibility Test Framework

### 9.1 Contract Tests

Run the same domain and Gateway Contract Tests against:

- Mock MP HTTP Profile;
- Mock Coordinator Profile;
- Mock SDK Profile;
- Mock Metrics/Event Profile;
- current validated v1 Profile;
- Legacy Profile;
- unknown-future Profile.

### 9.2 Compatibility Matrix

```text
CacheRoute version
runtime profile
vLLM version/profile
LMCache version/profile
Gateway adapters
storage adapters/tiers
validated operations
hit-observation mechanism
known limitations
status
```

### 9.3 Upgrade Scenarios

- LMCache minor-release upgrade;
- HTTP route, SDK method, or metric rename;
- completion-model change;
- key-format, layout, or serde change;
- Endpoint restart and Generation change;
- adapter addition, removal, or order change;
- old and new Profiles coexisting;
- Profile deprecation and rollback;
- explicit Legacy-to-v1 migration or rebuild.

### 9.4 Failure Principles

- Unknown capability is not supported by default.
- Incompatible Artifacts are not loaded.
- Gateway failure does not corrupt the knowledge catalog.
- KDN control-plane failure does not alter the running LMCache data path.
- v1 never silently performs a Legacy write operation.
- Proxy may fall back to text on failure.
- Upgrade failure can return to the previous validated Profile.

## 10. Queue and Cache Research Metrics

- TTFT P50/P95/P99;
- throughput and completion time;
- Knowledge Resolve Wait;
- LMCache Gateway Request/Operation Time;
- Token Lookup Coverage;
- Hit Tokens and Remote Reads;
- Prefetch/Pin/Clear success rate;
- Endpoint/Adapter/Tier capacity and health;
- Network-Compute Overlap Ratio;
- GPU Idle Due to Cache Wait;
- Head-of-Line Blocking Time;
- single-flight saved tasks and bytes;
- Profile negotiation failure rate;
- incompatible rebuild and fallback rate;
- result consistency across LMCache upgrades.

## 11. State Boundaries

### KDN Knowledge Control Plane

Authoritative for knowledge, Artifacts, policy, Desired State, Profile support, and historical value.

### KDN Cache Service Facade

Authoritative for logical CacheRoute operations, idempotency, task state, audit, and structured outcomes, but not for physical KV.

### LMCache Gateway

Maintains the active Endpoint Capability Snapshot, release adapters, and short-lived invocation observations; it is not a second source of physical truth.

### LMCache Runtime

Authoritative for tokens, chunks, keys, physical KV, L1/L2, adapters, serde, locks, capacity, eviction, and low-level operation results.

### Proxy

Maintains request-level plans, short-lived Instance/LMCache observations, shared preparation tasks, and queues.

### Instance / vLLM

Authoritative for actual hit tokens, model execution, Prefill, and Decode outcomes.

## 12. Testing and Experiment Requirements

### Unit Tests

- RuntimeProfile resolution and freeze;
- object IDs and state transitions;
- LMCacheCompatibilityProfile;
- CapabilitySnapshot;
- secret/private-key rejection;
- observation TTL and Endpoint Generation;
- CacheOperationTask idempotency;
- CachePlan/FusionPlan;
- ExecutionGraph;
- trace provenance.

### CPU-Only Component Tests

- Mock HTTP/Coordinator/SDK/Metrics Gateways;
- Knowledge and Cache Service contracts;
- supported/unsupported/incompatible/fallback behavior;
- read-only Legacy projection;
- proof that v1 does not call a Legacy write path;
- two adapter/tier representations;
- generic pytest collection makes no external request.

### GPU End-to-End Tests

- vLLM + LMCache MP + CacheRoute;
- token lookup, warm prefetch, and operation status;
- cold request with no cache read;
- warm request with hit-token or remote-read evidence;
- deterministic cold-versus-hit output equality;
- Endpoint restart and Generation invalidation;
- text, single-knowledge KV, Hybrid, and Legacy regression.

### Experiment Reproduction

Store:

- CacheRoute, vLLM, and LMCache versions;
- Runtime and Compatibility Profiles;
- Gateway Adapters and Capability Snapshot;
- workload and Endpoint/Adapter/Tier topology;
- queue and policy parameters;
- ExecutionGraph;
- request-level traces and results;
- aggregate metrics and anomalies.

## 13. Version Dependencies

```text
v0.1.10 contracts + gateway vocabulary
                 |
v0.1.11 knowledge + LMCache observation
                 |
v0.1.12 LMCache-backed cache service MVP
                 |
v0.1.13 multi-tier + release compatibility
                 |
v0.1.14 observed Proxy manager
                 |
v0.1.15 execution graph
                 |
v0.1.16 overlap pipeline
                 |
v0.1.17 queue stability
        +--------+--------+
        |                 |
v0.1.18 policy     v0.1.19 fusion/tools
        |                 |
        +--------+--------+
                 |
              v0.2.0
```

## 14. Long-Term KDN Evolution

After v0.2.0, KDN should evolve:

1. from one service into Knowledge Control, Cache Service, and multiple Gateway Workers;
2. from one LMCache Endpoint into multi-Endpoint and multi-region orchestration;
3. from static Profiles into automatic capability negotiation and conformance;
4. from coarse Artifacts into multi-block, partial, and composed knowledge cache;
5. from rule policies into SLO- and uncertainty-aware policies;
6. in continuous alignment with new LMCache MP, Coordinator, SDK, Adapter, Metrics, and Event capabilities;
7. by adding a CacheRoute-specific data extension only after proving LMCache extension mechanisms cannot satisfy the need;
8. while preserving isolation among Knowledge API, Cache Service Domain, Gateway Adapters, and LMCache Runtime.

Regardless of how LMCache evolves, CacheRoute's long-term core remains:

> **connect knowledge semantics, LMCache-native cache capabilities, cache policy, and compute-queue orchestration into an observable, extensible, and reproducible experimental loop.**
