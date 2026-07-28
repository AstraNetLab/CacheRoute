# CacheRoute v0.2.0: v1 KDN Alignment With LMCache-Native Capabilities

> Status: architecture amendment; this document has priority when interpreting conflicting wording in the existing v0.2.0 plans
> Runtime baseline: vLLM 0.25.1 + LMCache 0.5.2 + PyTorch 2.11.0
> Development policy: new functionality targets `v1`; `legacy` remains runnable but feature-frozen

## 1. Why This Amendment Is Needed

After migration to the current vLLM and LMCache MP environment, LMCache provides substantially more complete cache-data and maintenance capabilities than the previous stack:

- Token Database and token/hash lookup;
- the direct vLLM `LMCacheMPConnector` data path;
- L1 and persistent L2 storage;
- cascaded lookup and store across multiple L2 adapters;
- asynchronous L1-to-L2 store and L2-to-L1 prefetch;
- store and prefetch policies;
- independent L1/L2 capacity, usage, and eviction;
- cache-object enumeration and deletion;
- warm prefetch, pin/unpin, and operation status;
- MP HTTP API, Coordinator, SDK, metrics, and events;
- multi-server, L2-event, quota, and maintenance coordination.

CacheRoute should not duplicate simplified versions of these features inside KDN. Doing so would create a second source of physical cache truth, diverge from LMCache token/chunk/layout semantics, and make v1/Legacy compatibility much harder to maintain.

## 2. Revised Formal Positioning

> **KDN Server = Knowledge Control Plane + CacheRoute Cache Service Facade + LMCache Orchestration Gateway.**

KDN remains independently deployable, scalable, and schedulable. In v1, however, it is not another remote KV data server by default.

### 2.1 Global Component, Data-Path, and Control-Path Diagram

Legend:

```text
==  high-frequency request or KV data hot path
--  control, management, policy, or observation API
|   containment or component hierarchy
```

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

### 2.2 Data Hot Path

```text
vLLM
  == LMCacheMPConnector
  == LMCache MP
      |-- L1
      |-- cascaded L2 adapters
```

Frequent lookup, store, retrieve, prefetch, and KV transfer do not cross KDN business services.

### 2.3 CacheRoute Control Path

```text
Scheduler / Proxy / Instance
          -- KDN Knowledge API / Cache Service API
          --> KDN Cache Service Facade
          --> LMCache Orchestration Gateway
          -- MP HTTP / Coordinator / SDK / Metrics / Events
          --> LMCache MP
```

KDN owns:

- KnowledgeObject identity and version;
- CacheArtifact identity and compatibility;
- KnowledgeObject-to-token/artifact mapping;
- desired state and cache policy;
- lookup, prefetch, pin, clear, and rebuild intents;
- idempotent tasks, audit, authorization, structured errors, and fallback;
- normalized short-lived LMCache observations;
- request outcomes, cache value, and maintenance feedback.

LMCache owns:

- token chunking, hashes, and keys;
- physical KV objects and layouts;
- L1/L2 residency;
- adapter cascades;
- serde;
- locking and unlocking;
- store, retrieve, and prefetch;
- capacity accounting and eviction;
- physical operation completion.

## 3. Stable KDN Service Interfaces

KDN still needs stable APIs, but they are CacheRoute domain services rather than another physical KV storage protocol.

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

Mapping rule:

```text
CacheRoute Domain Request
        |
        v
KDN versioned API
        |
        v
CacheOperationTask / Observation
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

### 3.2 Knowledge API

```text
RegisterKnowledge
UpdateKnowledgeVersion
ResolveKnowledge
ListCompatibleArtifacts
GetPolicyDecision
ReportRequestOutcome
```

### 3.3 Cache Service API

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

Stable domain models must not expose Redis keys, Redis credentials, LMCache-private Python objects, internal chunk keys, physical KV payloads, or private serialized objects.

## 4. v1 and Legacy Boundaries

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

- all new functionality is developed only for `v1`;
- use LMCache MP and public control/observation interfaces;
- isolate release differences behind adapters, factories, and immutable capability snapshots;
- new code does not scan or copy Redis keys directly;
- missing capabilities produce `unsupported`, `incompatible`, or explicit text fallback;
- v1 requests never silently switch to a Legacy write path.

### 4.3 Legacy

- preserve current Redis scan/dump/restore/inject behavior;
- preserve old startup, request, and experiment flows;
- feature-freeze the path and accept only availability, security, critical defect, and compatibility fixes;
- encapsulate all physical operations behind `LegacyCacheAdapter` or an equivalent boundary;
- do not use Legacy keys or directories as v1 Artifact identities;
- move Legacy data into v1 only through explicit migration or rebuild.

### 4.4 Auto

`auto` is migration discovery only. Startup must resolve it into one explicit frozen profile:

```text
auto --> v1
```

or:

```text
auto --> legacy
```

A process or request must not switch primary execution semantics dynamically based on which key layout happens to exist.

## 5. LMCache Gateway

The Gateway is the only module allowed to know concrete LMCache release and interface details.

### 5.1 Gateway Internal Structure Diagram

```text
KDN Cache Service Facade
          |
          v
+---------------- LMCache Orchestration Gateway ----------------+
|                                                               |
|  CapabilityFactory                                            |
|  |-- detect LMCache version / build                           |
|  |-- detect endpoint generation                               |
|  |-- build immutable CapabilitySnapshot                       |
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

### 5.2 Recommended Adapters

```text
MPHTTPGateway
MPCoordinatorGateway
MPSDKGateway
MPMetricsEventGateway
MockGateway
LegacyCacheAdapter
```

Optional:

```text
L2PluginGateway
```

An L2 Plugin is justified only when CacheRoute requires a backend capability that LMCache does not already provide. It must still follow LMCache adapter contracts.

### 5.3 Startup Capability Discovery

The v1 Gateway should:

1. query LMCache version and build ID;
2. query config and loaded adapters;
3. probe required HTTP routes, metrics, and events;
4. build an immutable Capability Snapshot;
5. validate connector, chunk size, hash, layout, serde, and tier profiles;
6. create an Endpoint Generation;
7. record the profile in Instance Capability and traces.

Unknown capability is never treated as supported.

### 5.4 Stable Objects

```text
RuntimeProfile
LMCacheCompatibilityProfile
LMCacheEndpoint
CacheArtifact
CacheReplicaObservation
CacheOperationTask
QueueWork
CachePlan
ExecutionGraph
```

`CacheReplicaObservation` is a TTL-bound observation, not a KDN-owned physical replica.

## 6. Revised Version Route

| Version | Revised theme | Main delivery |
|---|---|---|
| v0.1.10 | v1/Legacy contract and observation baseline | RuntimeProfile, Gateway Profile, states, traces, Legacy projection |
| v0.1.11 | Knowledge Control + LMCache Observation | Knowledge/Artifact, token mapping, endpoint/adapter/tier observations |
| v0.1.12 | LMCache-backed KDN Cache Service MVP | MP HTTP/Coordinator Gateway, Lookup/Prefetch/Pin/Clear |
| v0.1.13 | Multi-tier, multi-adapter, and release compatibility | adapter cascade, capacity/eviction observation, compatibility matrix, recovery/rebuild |
| v0.1.14 | Proxy KVCache Manager | short-lived Instance view and single-flight from KDN/LMCache observations |
| v0.1.15-v0.1.17 | execution queues and network-compute overlap | ExecutionGraph, backpressure, fairness, concurrency, overlap |
| v0.1.18 | KDN knowledge-aware policy | Prefetch/Pin/Clear/Rebuild intents and value model |
| v0.1.19 | multi-block fusion | parallel token/artifact lookup, selective recomputation, quality fallback |
| v0.2.0 | integrated research baseline | v1 default, Legacy preserved, cross-LMCache compatibility |

## 7. Capabilities v1 KDN Must Not Reimplement

v1 KDN does not implement:

- a Token Database;
- chunk hashing or physical key generation;
- L1/L2 StorageManager;
- multi-adapter cascade lookup;
- L1/L2 eviction threads;
- Store/Prefetch Controller;
- KV serde;
- KV lock/unlock;
- a physical cache-object directory;
- simplified versions of LMCache warm prefetch, pin, or clear.

KDN may implement:

- knowledge-level value evaluation;
- decisions about which Artifact to warm, pin, clear, or rebuild;
- compilation of policy intents into LMCache operations;
- coarse selection and orchestration across LMCache Endpoints;
- normalized observations with TTL and confidence;
- release-compatibility gates and fallback;
- request-level experiment traces.

## 8. Testing Principles

### v1

- Mock Gateway CPU-only contract tests;
- MP HTTP Gateway tests;
- Coordinator Gateway tests;
- two LMCache adapter/tier configurations;
- token lookup and warm prefetch;
- cache-object, capacity, and eviction observation;
- LMCache Endpoint restart and generation changes;
- actual hit-token and remote-read metrics;
- LMCache minor-version conformance tests.

### Legacy

- old startup path;
- Redis scan/dump/restore/inject;
- old request formats;
- text and fallback paths;
- Legacy changes must not affect v1 tests;
- v1 changes must not break the minimal Legacy regression set.

## 9. Interpretation Priority

This amendment supersedes the following wording in the existing v0.2.0 plans:

- KDN Remote Cache Serving Plane as the default v1 data hot path;
- LMCache treating KDN as its default remote KV store;
- KDN implementing provider cascades, capacity, or eviction;
- new functionality being developed simultaneously for v1 and Legacy.

Existing plans for knowledge policy, Proxy ExecutionGraph, network-compute overlap, multi-block fusion, and experiment metrics remain valid unless explicitly changed here.
