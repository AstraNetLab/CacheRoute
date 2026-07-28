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

### 2.1 Data Hot Path

```text
vLLM
  <-> LMCacheMPConnector
  <-> LMCache MP
      <-> L1
      <-> cascaded L2 adapters
```

Frequent lookup, store, retrieve, prefetch, and KV transfer do not cross KDN business services.

### 2.2 CacheRoute Control Path

```text
Scheduler / Proxy / Instance
          -> KDN Cache Service Facade
          -> LMCache Orchestration Gateway
          -> LMCache MP HTTP / Coordinator / SDK / Metrics / Events
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

### 3.1 Knowledge API

```text
RegisterKnowledge
UpdateKnowledgeVersion
ResolveKnowledge
ListCompatibleArtifacts
GetPolicyDecision
ReportRequestOutcome
```

### 3.2 Cache Service API

```text
GetCacheObservation
LookupArtifact
LookupTokens
CreatePrefetchIntent
CreatePinIntent
CreateClearIntent
CreateRebuildIntent
GetOperationStatus
GetLMCacheEndpoints
GetTierAndAdapterSummary
GetMaintenanceStatus
```

Stable parameters use Knowledge IDs, Artifact IDs, token sequences or token references, Instance Capability, LMCache Endpoint IDs, and logical operation IDs.

Stable domain models must not expose Redis keys, Redis credentials, LMCache-private Python objects, internal chunk keys, physical KV payloads, or private serialized objects.

## 4. v1 and Legacy Boundaries

### 4.1 v1

- all new functionality is developed only for `v1`;
- use LMCache MP and public control/observation interfaces;
- isolate release differences behind adapters, factories, and immutable capability snapshots;
- new code does not scan or copy Redis keys directly;
- missing capabilities produce `unsupported`, `incompatible`, or explicit text fallback;
- v1 requests never silently switch to a Legacy write path.

### 4.2 Legacy

- preserve current Redis scan/dump/restore/inject behavior;
- preserve old startup, request, and experiment flows;
- feature-freeze the path and accept only availability, security, critical defect, and compatibility fixes;
- encapsulate all physical operations behind `LegacyCacheAdapter` or an equivalent boundary;
- do not use Legacy keys or directories as v1 Artifact identities;
- move Legacy data into v1 only through explicit migration or rebuild.

### 4.3 Auto

`auto` is migration discovery only. Startup must resolve it into one explicit frozen profile:

```text
auto -> v1
```

or:

```text
auto -> legacy
```

A process or request must not switch primary execution semantics dynamically based on which key layout happens to exist.

## 5. LMCache Gateway

The Gateway is the only module allowed to know concrete LMCache release and interface details.

### 5.1 Recommended Adapters

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

### 5.2 Startup Capability Discovery

The v1 Gateway should:

1. query LMCache version and build ID;
2. query config and loaded adapters;
3. probe required HTTP routes, metrics, and events;
4. build an immutable Capability Snapshot;
5. validate connector, chunk size, hash, layout, serde, and tier profiles;
6. create an Endpoint Generation;
7. record the profile in Instance Capability and traces.

Unknown capability is never treated as supported.

### 5.3 Stable Objects

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
