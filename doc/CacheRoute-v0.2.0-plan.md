# CacheRoute v0.2.0 Evolution Plan

> Status: Planning draft  
> Current baseline: v0.1.9  
> Target release: v0.2.0  
> Core foundation: vLLM + LMCache  
> Core research directions: LMCache-aligned KDN control/data separation, knowledge-aware cache policy, LMCache-observed Proxy KVCache Management, parallel knowledge injection and compute queues, and multi-knowledge-block non-prefix fusion reuse

## 0. Current Implementation Status and Design Alignment

The v0.1.10 implementation has started. The roadmap must therefore evolve without discarding completed work:

| Item | Current status | Roadmap treatment |
|---|---|---|
| #138 / PR #143 | completed and merged | retain the Instance capability fingerprint contract |
| PR #145 | completed and merged | retain the synchronized capability documentation and package baseline |
| #139 / PR #147 | implementation in progress | keep the policy-neutral state models, but clarify that Artifact and Replica are logical CacheRoute views over LMCache-managed data |
| #140 | open | revise toward an LMCache-aligned management/adapter protocol rather than a second cache-storage protocol |
| #141 | open | make LMCache lookup, controller, event, and runtime observations first-class trace sources |
| #142 | open | validate LMCache-aligned adapters and ensure legacy scripts do not break CPU-only collection |

This update introduces one non-negotiable architectural rule:

> **LMCache owns the physical KVCache storage and transfer mechanisms. CacheRoute owns knowledge semantics, policy, orchestration, queueing, and reproducible experimentation.**

CacheRoute may maintain logical Artifact and Replica records, desired state, policy state, and short-lived observations. It must not implement a parallel physical KV store, duplicate LMCache's chunk index, or treat KDN filesystem/Redis metadata as the long-term source of truth.

## 1. Overall Goal

CacheRoute v0.2.0 is not intended to reimplement a KVCache storage system or to prioritize a complex global scheduling algorithm. Its goal is to establish a control, execution, and maintenance framework for knowledge reuse on top of vLLM and LMCache.

v0.2.0 should form the following complete closed loop:

```text
Knowledge registration
  -> KVCache artifact construction
  -> KDN control-plane registration, validation, and maintenance
  -> LMCache lookup, publication, transfer, and tier operations through adapters
  -> Proxy builds a request-level CachePlan / ExecutionGraph
  -> Knowledge-preparation queues and pure-compute queues progress in parallel
  -> LMCache / vLLM loads, reuses, fuses, or selectively recomputes
  -> Report hit, queueing, transfer, loading, compute, and quality results
  -> KDN updates policy intent and invokes supported LMCache operations based on feedback
```

v0.2.0 focuses on five interdependent tracks.

### 1.1 KDN Control Plane

The KDN control plane evolves into the authoritative **knowledge-semantic and policy catalog**, not a physical KVCache store. It is responsible for:

- distinguishing KnowledgeObject, CacheArtifact, and CacheReplica as logical management objects;
- mapping a knowledge object and an Instance capability fingerprint to LMCache-addressable token/hash/object references;
- maintaining compatibility, desired lifecycle, policy state, placement intent, Pins, budgets, and historical value statistics;
- discovering LMCache capabilities and ingesting lookup, worker, health, event, and task-result observations;
- generating high-level build, publish, prefetch, move, pin, clear, refresh, and fallback intents;
- providing stable, lightweight, versioned query and orchestration interfaces;
- never carrying large KV payloads, backend credentials, LMCache internal keys, or a duplicate chunk index in control-plane messages.

The KDN control plane is authoritative for **why** a cache object should exist and how it relates to knowledge. LMCache is authoritative for **whether and where** the physical KV data currently exists.

### 1.2 LMCache-Aligned KDN Data Access Plane

The KDN data-access plane is an orchestration and adaptation layer over LMCache. It does not implement its own storage engine.

Its responsibilities are:

- invoke LMCache-supported lookup, retrieve/prefetch, move/copy, pin/unpin, clear/delete, health, object-enumeration, and task-status operations where available;
- use LMCache storage and transport backends such as CPU memory, local disk, Redis/Valkey, Mooncake, InfiniStore, S3, NIXL, GDS, or storage plugins;
- expose a stable CacheRoute adapter so policy and queue code do not depend on one LMCache mode or backend;
- normalize actual bytes, queueing time, transfer time, matched tokens, cache location/tier, worker health, and structured errors;
- support LMCache in-process/controller interfaces and LMCache MP HTTP/coordinator interfaces behind capability negotiation;
- allow Legacy Redis and filesystem injection only as explicitly marked compatibility adapters;
- preserve fault isolation: LMCache operation failures must not corrupt the KDN knowledge catalog, while temporary KDN control-plane failure must not invalidate already-running LMCache work.

A CacheRoute DataPlaneTask is therefore a **logical orchestration task whose executor is normally LMCache**, not a custom CacheRoute storage worker. A future custom backend should be implemented through LMCache's storage-plugin/remote-connector interfaces unless there is a demonstrated capability gap.

### 1.3 Parallel Knowledge Injection and Compute Queues

This is a core characteristic of CacheRoute v0.2.0 and a major systems contribution that differentiates it from ordinary KVCache routers.

The Proxy should not treat “knowledge preparation completed” as a single serial barrier that every request must cross before computation. Instead, it should explicitly model and advance the following work in parallel:

- KDN metadata resolution;
- network KVCache transfer;
- LMCache local loading;
- Prefill computation for pure text or residual tokens;
- Decode execution;
- partial preparation and fusion dependencies across multiple knowledge blocks.

The queueing mechanism should achieve the following:

- network transfer can overlap with pure computation for other requests;
- text requests that do not depend on KV can take a compute fast path;
- requests waiting for KV do not block requests that are immediately computable;
- concurrent requests for the same artifact share one preparation task;
- different links, Instances, and resource classes can progress independently;
- scheduling policies remain pluggable, while correctness, dependency enforcement, and resource limits are guaranteed by a unified queueing foundation;
- the mechanism remains generally applicable across models, bandwidths, storage backends, knowledge-block counts, and injection ratios.

### 1.4 KDN Knowledge-Aware KVCache Policies

After the integration foundation is stable, KDN research should focus on policy above LMCache:

- which knowledge is worth materializing or admitting as KVCache;
- which LMCache-managed objects should be pinned, retained, moved, prefetched, or cleared under capacity constraints;
- which storage tier or target Instance should receive a warm copy, using only operations exposed by LMCache;
- when to refresh or rebuild an Artifact after model, tokenizer, adapter, layout, or knowledge-version changes;
- how to use Proxy queue feedback, LMCache lookup/events, network cost, compute savings, and multi-block co-occurrence;
- how to avoid pollution, oscillation, and background-operation interference with online requests;
- how to evaluate policy decisions independently from the concrete LMCache backend.

CacheRoute policies produce **desired actions and priorities**. LMCache remains responsible for physical eviction, storage allocation, serialization, chunk indexing, transfer, and backend-specific execution.

### 1.5 Multi-Knowledge-Block Non-Prefix Matching and Fusion Reuse

v0.2.0 should support:

- multiple independent knowledge blocks in a single request;
- identifying reusable knowledge at arbitrary Prompt positions rather than only as one continuous prefix;
- unified planning for full hits, partial hits, overlapping hits, and reordered blocks;
- fusion through LMCache non-prefix reuse, CacheBlend, or an equivalent capability;
- selective recomputation of required tokens to avoid quality errors from naïvely concatenating KV states;
- integrating multi-block loading tasks into the knowledge-preparation queues and parallelizing them where possible;
- reliable fallback to text recomputation when the runtime lacks support, quality checks fail, or execution errors occur.

## 2. Overall Requirements and Boundaries

### 2.1 Role Boundaries

```text
Scheduler
- Select the target Proxy / KDN resource pool
- Retain global knowledge-aware and resource-aware candidate generation
- Do not own fine-grained cache lifecycle, physical storage, or queue execution

KDN Control Plane
- Own knowledge identity, Artifact compatibility, desired state, policy, and orchestration history
- Map knowledge requirements to LMCache-addressable cache references
- Generate and track logical management intents and CacheRoute tasks
- Never become a physical KV store or duplicate LMCache's chunk/location index

KDN LMCache Adapter / Data Access Plane
- Translate CacheRoute intents into supported LMCache Controller, CacheEngine, MP HTTP, coordinator, or plugin operations
- Normalize capabilities, observations, task results, and errors
- Do not implement an independent cache backend when LMCache already provides one

Proxy
- Build CachePlan, FusionPlan, and ExecutionGraph
- Maintain short-lived per-Instance cache observations obtained from LMCache lookup/controller/events
- Coordinate knowledge-preparation and compute queues
- Do not maintain a second authoritative Instance cache directory

Instance
- Integrate Proxy with vLLM and LMCache
- Expose capability identity and a stable cache-observation/control surface
- Forward LMCache hit, load, event, health, and task information

LMCache
- Own physical KVCache objects, chunk indexing, storage tiers, serialization, eviction mechanisms, loading, transfer, and vLLM connectivity
- Provide the primary source of truth for cache residency and runtime operations

vLLM
- Own model execution, paged KV management, and engine-internal scheduling
- Accept requests only after CacheRoute request dependencies are satisfied
```

### 2.2 LMCache Alignment and Control/Data Separation Principles

1. CacheRoute must not implement a physical KVCache store that competes with LMCache.
2. KnowledgeObject and CacheArtifact are CacheRoute semantic objects; CacheReplica is a logical reference to an LMCache-observed location or object, not a copy of LMCache data.
3. The physical cache source of truth is LMCache lookup/controller/MP APIs, KV events, or runtime acknowledgements.
4. KDN desired state and policy state must be separated from LMCache observed state.
5. All LMCache interactions pass through a capability-aware adapter. Unsupported operations return structured `unsupported` results and trigger a safe fallback.
6. CacheRoute never depends on raw Redis keys, credentials, private serialization formats, or backend-internal chunk layouts as stable contracts.
7. CacheRoute should prefer LMCache public management APIs: lookup, health, object/status inspection, prefetch/retrieve, move/copy, pin/unpin, clear/delete, and completion checks.
8. Legacy direct Redis/filesystem behavior remains read-only or compatibility-only until migrated; it is not the target architecture.
9. If a required backend is missing, extend LMCache through its storage-plugin or remote-connector interfaces before adding a CacheRoute-specific store.
10. Control and data failures are isolated: catalog/policy state remains recoverable, and LMCache task outcomes are reconciled rather than guessed.

### 2.3 Queueing and Execution Principles

1. **Dependency correctness first**: a request can enter a compute phase only after its required dependencies are satisfied.
2. **Work conservation**: when executable work exists and a resource is available, the QueueCoordinator should not leave that resource idle.
3. **Resource separation**: network, Cache Load, Prefill, and Decode maintain separate concurrency budgets and timelines.
4. **Avoid head-of-line blocking**: slow KV tasks must not block text or local-hit tasks that do not depend on them.
5. **Single-flight**: duplicate preparation for the same Artifact and target is merged into one shared task.
6. **Event-driven release**: state changes actively wake dependents instead of relying on high-frequency polling.
7. **Cancellation and fallback**: cancellation or timeout releases references and switches to text or partial reuse according to policy.
8. **Policy/mechanism separation**: the queueing foundation guarantees state-machine correctness, dependency enforcement, and resource safety; policies only determine priority, quota, bypass, and concurrency.
9. **Measure first**: predicted and actual values are recorded separately so parallelism benefits can be reproduced experimentally.
10. **Compatible fast paths**: pure text, single-knowledge prefix KV, and current IWS flows are simple special cases of the unified execution graph.

### 2.4 Engineering Principles

- Each release must run and be validated independently; incremental iterations should replace one-shot large refactors.
- Preserve the current text-injection and Redis-injection experimental paths until replacement paths pass end-to-end validation.
- New fields are optional by default, and old requests and legacy KDN data continue to work.
- Every state transition must be observable rather than occurring only implicitly in logs.
- Maintenance and queue policies must be pluggable, disableable, and reproducible, and must not be scattered across API handlers.
- Runtime failures must have explicit degradation paths, with request correctness taking priority.
- `demo_*.py` files remain responsible only for startup and argument parsing; business logic stays in production modules.

### 2.5 Not Prioritized Within v0.2.0

- layered Pareto scheduling;
- reinforcement learning or online Bandit decisions;
- complete Prefill / Decode disaggregation;
- a self-developed RDMA transfer engine;
- mandatory full migration to LMCache MP;
- cross-region, multi-tenant, production-grade control planes;
- a CacheRoute replacement for LMCache storage.

Complex global scheduling should be implemented only after cache objects, data-plane tasks, queue events, and maintenance feedback are stable.

## 3. Existing Foundation

### 3.1 KDN Foundation

The current KDN already provides:

- a SQLite text-knowledge index and content-hash-based `kid`;
- text, Embedding, length, and KV status metadata;
- `KV_database/<kid>`, Manifest, and KV dump data;
- text registration, query, deletion, snapshot, and KV construction interfaces;
- a Legacy injection path that writes dump contents into target Redis;
- KDN registration, heartbeats, network-queue simulation, and basic transfer statistics.

Major limitations include:

- control APIs, catalog state, file management, and data transfer are concentrated in one service;
- one `kid` can express only one coarse KV state;
- `kv_ready` cannot represent building, transferring, failed, stale, or deleting states;
- KV dumps, SQLite records, and remote backends can become inconsistent;
- KDN depends directly on LMCache Redis keys and serialization formats;
- data tasks lack independent Workers, capability registration, Leases, recovery, and fault isolation;
- there are no replica, tier, capacity, access-statistics, or maintenance-policy models.

### 3.2 Proxy and Queue Foundation

The current Proxy already provides:

- a local Instance pool and `round_robin` / `least_load` strategy interfaces;
- Proxy-maintained `inflight`, queue-depth, and predicted-backlog metrics;
- prepare / ready queues and per-Instance reservation timelines;
- KDN text queries and `kv_ready` / `text_only` / `miss` classification;
- KDN-to-Instance KV transfer prediction and link reservation;
- cache state and request Trace fields in `ProxyTask`;
- `ordered` / `text_bypass` ready-release policies;
- an IWS foundation for text and KVCache injection decisions.

The existing mechanism has already shown that CacheRoute can explicitly manage “knowledge preparation” and “compute waiting,” but it still has the following limitations:

- the prepare phase contains multiple resource requirements but is represented mainly as one coarse queue;
- dependencies and resource budgets for network transfer, LMCache Load, Prefill, and Decode are not modeled uniformly;
- text bypass is only a local release rule rather than a general work-conserving multi-queue mechanism;
- network-KV and pure-compute parallelism lacks stable metrics and experimental baselines;
- duplicate Artifact loads, cancellation, retry, and shared waiting still need systematic treatment;
- multiple knowledge blocks are only classified and concatenated as text, without an ExecutionGraph or FusionPlan;
- Proxy lacks a unified KVCache Manager and per-Instance cache view.

### 3.3 vLLM + LMCache Foundation

CacheRoute already performs KVCache build and reuse experiments through vLLM + LMCache + Redis. The target architecture should directly leverage LMCache's existing capabilities:

- vLLM KV Connector integration;
- token/hash-based cache lookup and matched-prefix reporting;
- asynchronous load, retrieve, prefetch, save, and event reporting;
- local CPU, local disk, Redis/Valkey, Mooncake, InfiniStore, S3, NIXL, GDS, and plugin-based storage backends;
- Controller operations such as Lookup, Move, Pin, Clear, Health, and completion checks;
- MP HTTP/coordinator APIs for status, object inspection, prefetch, configuration discovery, metrics, and multi-server coordination;
- non-prefix reuse and CacheBlend-style selective recomputation;
- KV events and worker/runtime observability.

The key v0.2.0 task is not to replace these mechanisms. It is to build stable CacheRoute semantic and orchestration interfaces over them.

Known integration risks must be explicit:

- LMCache in-process/controller and MP APIs may differ, so adapters require capability negotiation;
- not every API exposes exact per-Instance GPU residency, so observed state may have confidence and freshness fields;
- LMCache public APIs evolve, so CacheRoute contracts must wrap them rather than copying internal classes or keys;
- legacy dump directories and Redis injection can be used for regression only and must not define the future data model.

## 4. v0.2.0 Target Architecture

```text
                              Scheduler
                                  |
                      global knowledge-aware route
                                  |
                                Proxy
  +-------------------+-----------+-----------------------------+
  |                   |                                         |
Request Admission  CachePlan / FusionPlan Builder         Queue Coordinator
- validate         - knowledge-to-token layout            - dependency graph
- choose fallback  - query KDN semantic catalog           - resource budgets
- create trace     - query LMCache observed state         - event-driven release
  |                   |                                         |
  |                   +---------------------+-------------------+
  |                                         |
  |                           Knowledge Preparation Plane
  |                   +-----------+-----------+-------------+
  |                   |           |           |             |
  |               metadata     LMCache      cache load   fusion prepare
  |                resolve      lookup /      wait          tasks
  |                            prefetch
  |                                         |
  +------------------------------ Compute Plane
                         +------------+------------+
                         |                         |
                    pure/residual Prefill       Decode
                         |                         |
                         +------------+------------+
                                      |
                              Instance / vLLM
                                      |
                                   LMCache
                 +--------------------+----------------------+
                 |                    |                      |
             local CPU/disk       remote backends       P2P/transport
                                 Redis/Valkey,          NIXL, Mooncake,
                                 S3, plugins, ...       other LMCache paths

                         KDN Control Plane
       +----------------------+----------------------+------------------+
       |                      |                      |                  |
Knowledge Catalog    Artifact Intent Catalog   Policy Engine      Task/Trace Registry
       |                      |                      |                  |
       +----------------------+-----------+----------+------------------+
                                          |
                           LMCache Integration Adapter
              lookup / status / prefetch / move / pin / clear / events
                                          |
                                     LMCache APIs
```

The architecture deliberately avoids a CacheRoute-owned storage tier. KDN can be deployed as a remote knowledge service, but physical KV data remains inside storage and transport units managed by LMCache.

## 5. Core Objects and Execution Model

### 5.1 KnowledgeObject

Represents model-independent knowledge content:

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

### 5.2 CacheArtifact

Represents a KVCache artifact generated for a specific model and runtime configuration:

```text
artifact_id
knowledge_id
model_fingerprint
tokenizer_fingerprint
adapter_fingerprint
kv_layout_version
kv_dtype
tp_size
pp_size
chunk_size
token_count
token_ranges
total_bytes
checksum
state
created_at
updated_at
```

### 5.3 CacheReplica

A CacheReplica is a **logical observation/reference** that associates an Artifact with an LMCache-managed cache location. It does not contain KV bytes and is not a replacement for the LMCache index.

```text
replica_id
artifact_id
provider                 # normally lmcache; legacy only for compatibility
lmcache_mode             # controller / mp / in_process / unknown
lmcache_instance_id
worker_id
backend_type             # LMCache-reported adapter/backend type
storage_tier
location_ref             # opaque, non-secret, provider-defined reference
observed_state
health
observation_source       # lookup / event / status / legacy / inferred
observed_at
expires_at
confidence
```

The `location_ref` must remain opaque. CacheRoute must not parse or persist private Redis keys, credentials, serialization payloads, or backend-internal block formats.

### 5.4 LMCacheEndpoint

```text
endpoint_id
api_mode                  # controller / mp_http / coordinator / in_process
endpoint
lmcache_version
supported_operations
storage_adapters
transport_capabilities
instance_ids
health
capacity_summary
queue_summary
generation
last_heartbeat_at
```

### 5.5 DataPlaneTask

A DataPlaneTask is a CacheRoute orchestration record for an LMCache operation.

```text
task_id
idempotency_key
operation                 # LOOKUP / PREFETCH / MOVE / PIN / UNPIN / CLEAR / VERIFY / STATUS
artifact_id
source_replica_ref
target_endpoint_id
target_instance_id
provider_task_id
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

The task state belongs to CacheRoute orchestration. Physical execution state and cache residency are reconciled from LMCache responses/events.

### 5.6 CachePlan / FusionPlan

```text
request_id
target_instance_id
knowledge_blocks
matched_artifacts
missing_blocks
source_replicas
load_tasks
fusion_mode
recompute_ranges
fallback_mode
plan_state
trace_context
```

### 5.7 ExecutionGraph

ExecutionGraph is the unified input to the Proxy queueing mechanism. Each node represents one unit of work, and each edge represents a dependency:

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

Recommended `resource_class` values:

```text
CONTROL        KDN queries and plan resolution
NET_KV         network KVCache transfer
CACHE_LOAD     LMCache local loading and confirmation
PREFILL        pure-text or residual-token computation
DECODE         Decode occupancy and completion tracking
FUSION         multi-block fusion and selective-recompute preparation
```

## 6. Iteration Overview

| Version | Theme | Main Deliverables |
|---|---|---|
| v0.1.10 | Contract and observability baseline | capability fingerprints, logical state contracts, LMCache-aligned protocol vocabulary, Queue Trace |
| v0.1.11 | KDN semantic catalog | KnowledgeObject / Artifact Intent / logical Replica references |
| v0.1.12 | LMCache integration plane | capability discovery, lookup/status/events, management adapter, Legacy compatibility adapter |
| v0.1.13 | desired/observed lifecycle and recovery | reconciliation against LMCache, freshness/confidence, idempotent task recovery |
| v0.1.14 | Proxy KVCache Manager | LMCache-observed per-Instance cache view, CachePlan, Single-flight |
| v0.1.15 | injection and compute queue model | ExecutionGraph, resource queues, dependency release, compute fast path |
| v0.1.16 | network/compute parallel pipeline | work-conserving overlap, link/Instance timelines, overlap benchmark |
| v0.1.17 | queue generality and stability | admission, backpressure, fairness, aging, adaptive concurrency, fault fallback |
| v0.1.18 | knowledge-aware cache policy | LMCache-driven pin/move/prefetch/clear policy, value model, Trace Replay |
| v0.1.19 | multi-block non-prefix fusion | matching, parallel LMCache preparation, selective recomputation, quality fallback |
| v0.2.0 | integrated research baseline | complete closed loop, fault tests, stable interfaces, reproducible results |

## 7. Per-Version Plan

## v0.1.10: Contract and Observability Baseline

### Problem to Solve

All later capabilities depend on unified object identity, compatibility, control/data-plane task semantics, and queue-stage Trace fields.

### Main Steps

1. Define fingerprints for model, Tokenizer, Adapter, KV layout, precision, and parallel configuration.
2. Extend Instance registration to report vLLM, LMCache, and KV capabilities.
3. Define state enums for Artifact, Replica, DataPlaneTask, and Queue Work.
4. Define versioned protocols for the KDN control and data planes:
   - Endpoint registration;
   - task submission;
   - Lease;
   - status query;
   - result reporting;
   - idempotency key.
5. Standardize request Trace fields for:
   - KDN query;
   - plan construction;
   - control-plane waiting;
   - network queueing and transfer;
   - Cache Load;
   - Prefill queueing and computation;
   - Decode;
   - fusion and fallback.
6. Add `predicted_*`, `actual_*`, and `source` fields to prevent predicted and measured values from being mixed.
7. Preserve compatibility with legacy `kv_ready`, legacy requests, and the Legacy Redis path.

### Acceptance Criteria

- Incompatible Instances or Artifacts can be identified.
- Control/data-plane messages have explicit versions.
- A single request exposes stable timing breakdowns for knowledge preparation and computation.
- Current injection decisions and forwarding results are unchanged.

## v0.1.11: KDN Semantic Catalog and Logical Cache References

### Problem to Solve

The current knowledge row, `kv_ready`, dump path, and Redis injection state are coupled. CacheRoute needs a semantic catalog without duplicating LMCache's physical cache index.

### Main Steps

1. Keep the Legacy table and introduce KnowledgeObject and CacheArtifact intent records.
2. Define a one-to-many relationship from knowledge versions to compatibility-specific Artifacts.
3. Represent CacheReplica only as an LMCache-observed logical reference with source, freshness, and confidence.
4. Generate stable Artifact and Replica IDs without using raw LMCache/Redis keys as identity inputs.
5. Map `KV_database/<kid>` and `kv_ready` to an explicitly Legacy, compatibility-unknown observation.
6. Add catalog queries by knowledge ID, capability fingerprint, and desired Artifact variant.
7. Add an observation-ingest interface for later LMCache lookup/events.
8. Expose only coarse Artifact availability to Scheduler; detailed residency remains Proxy/KDN internal.

### Acceptance Criteria

- one knowledge object can register multiple compatibility-specific Artifact intents;
- logical Replica references serialize without KV payloads, credentials, or private backend keys;
- the catalog distinguishes desired state from observed LMCache state;
- Legacy `kv_ready` maps to a read-only compatibility view;
- no new CacheRoute storage backend, chunk index, or physical eviction implementation is introduced.

## v0.1.12: LMCache-Aligned Remote Data-Plane Integration

### Problem to Solve

CacheRoute currently reaches remote KV through Legacy Redis injection and filesystem dump assumptions. It should instead use LMCache as the physical storage and transfer plane.

### Main Steps

1. Define an `LMCacheManagementAdapter` with capability discovery and structured results.
2. Support the available public operations by mode:
   - lookup and matched-token/location query;
   - health, worker, status, object, adapter, and metrics inspection;
   - retrieve/prefetch and completion status;
   - move/copy where supported;
   - pin/unpin where supported;
   - clear/delete where supported;
   - KV event ingestion.
3. Support Controller/in-process and MP HTTP/coordinator modes through separate implementations behind one contract.
4. Return `unsupported` rather than emulating an operation incorrectly when a mode lacks a capability.
5. Wrap current direct Redis/filesystem injection as `LegacyCompatibilityAdapter` and keep it disabled from new policy code by default.
6. Normalize actual tokens, bytes, locations, queue/operation duration, provider task IDs, and errors.
7. Add Mock LMCache adapters for CPU-only CI and deterministic fault injection.
8. Document which fields are observed, inferred, or Legacy-derived.

### Acceptance Criteria

- CacheRoute can query cache availability through an LMCache public interface or test adapter;
- Proxy and KDN code do not require LMCache private Redis keys or serialization formats;
- at least lookup/status plus one asynchronous preparation operation are covered by the normalized adapter;
- unsupported LMCache capabilities produce structured fallback decisions;
- no independent CacheRoute physical KV store is created;
- Legacy injection remains available for regression only.

## v0.1.13: Desired/Observed Lifecycle, Reconciliation, and Recovery

### Problem to Solve

CacheRoute desired state, Legacy metadata, and LMCache-observed residency may diverge. A logical `READY` flag must not be treated as proof of physical availability.

### Main Steps

1. Separate `desired_state`, `observed_state`, `health`, `observation_source`, `observed_at`, and `expires_at`.
2. Keep immutable Artifact/Replica/DataPlaneTask state contracts introduced in v0.1.10.
3. Reconcile logical records against LMCache lookup/status/events rather than scanning CacheRoute-owned storage as the target design.
4. Use two-phase logical publication: build intent -> validate compatibility -> LMCache store/save observation -> publish usable Artifact.
5. Recover idempotent tasks by provider task ID and idempotency key.
6. Invalidate stale Instance observations on LMCache endpoint or Instance generation change.
7. Keep Legacy filesystem reconciliation in a separate compatibility module.
8. Expose disagreement counters, stale observations, unsupported operations, and recent reconciliation failures.

### Acceptance Criteria

- KDN `READY` never implies target-Instance residency without a fresh LMCache observation;
- control-plane restart can rebuild observed state from LMCache or mark it unknown safely;
- stale/failed LMCache observations block unsafe reuse but preserve text fallback;
- Legacy mapping remains read-only and cannot become the long-term source of truth;
- retries do not duplicate logical work or physical LMCache operations where idempotency is supported.

## v0.1.14: Proxy KVCache Manager as an LMCache-Observed View

### Problem to Solve

Proxy needs per-Instance cache awareness for planning, but it must not duplicate LMCache's cache manager or maintain an independent authoritative cache directory.

### Main Steps

1. Introduce Proxy KVCache Manager as a thin observed-state and orchestration component.
2. Populate the view from:
   - LMCache lookup results;
   - Controller/MP status and worker information;
   - KV events and load/save acknowledgements;
   - CacheRoute-submitted preparation task results.
3. Store freshness, confidence, and source on every observation.
4. Define local states such as UNKNOWN, AVAILABLE_REMOTE, PREFETCHING, LOADING, AVAILABLE_LOCAL, FAILED, and EXPIRED as Proxy projections, not LMCache replacements.
5. Generate CachePlan/FusionPlan from KDN semantic metadata plus LMCache-observed state.
6. Implement Single-flight for the same Artifact, target Instance, and compatible LMCache operation.
7. Invalidate observations on Instance/LMCache generation change, timeout, or contradictory events.
8. Use short-lived negative caching and query coalescing to avoid overloading LMCache management APIs.
9. Expose a Debug API showing source, age, confidence, provider task, and fallback.

### Acceptance Criteria

- Proxy distinguishes KDN desired availability, LMCache remote availability, loading, and fresh target-local availability;
- cache residency claims identify an LMCache query/event source and observation time;
- concurrent requests share preparation without hiding LMCache task results;
- stale views expire safely to UNKNOWN rather than remaining falsely READY;
- no second physical cache index, eviction engine, or storage allocator is implemented in Proxy.

## v0.1.15: Knowledge Injection and Compute Queue Model

### Problem to Solve

The existing prepare / ready queues do not uniformly represent control, network, Cache Load, and compute dependencies, and therefore cannot systematically prevent slow KV tasks from causing head-of-line blocking.

### Main Steps

1. Compile CachePlan into ExecutionGraph.
2. Define independent physical or logical work queues:
   - CONTROL Resolve Queue;
   - NET_KV Transfer Queue;
   - CACHE_LOAD Queue;
   - PREFILL Compute Queue;
   - DECODE Tracking Queue;
   - FUSION Prepare Queue.
3. QueueCoordinator maintains node dependencies, reference counts, cancellation propagation, and event wakeups.
4. Pure-text and local-hit tasks use the Compute Fast Path and do not enter remote-KV waiting.
5. Preserve external prepare / ready semantics, but let ExecutionGraph determine when a request becomes Ready internally.
6. Establish independent concurrency budgets and basic timelines for every resource class.
7. When one shared preparation node completes, wake all waiting requests in a batch.
8. Record queueing, execution, dependency waiting, and blocking reasons for every node.
9. Provide compatibility mappings for legacy `ordered` / `text_bypass`.

### Acceptance Criteria

- Text tasks are no longer blocked by unrelated slow KV tasks.
- A request is not submitted for computation before its dependencies are satisfied.
- Shared tasks execute only once.
- Request cancellation correctly releases graph-node references.
- ExecutionGraph can be inspected and reproduced through Debug APIs.

## v0.1.16: Parallel Network-KV and Pure-Compute Pipeline

### Problem to Solve

After the queue model is established, network data preparation and GPU computation must actually overlap to reduce idle time caused by GPU waiting for KV, network waiting for submission, and serial barriers.

### Main Steps

1. Implement a work-conserving QueueCoordinator:
   - continuously issue NET_KV work while network capacity is available;
   - continuously release computable work while Prefill resources are available;
   - blockage in one resource class does not block other resource classes.
2. Maintain independent timelines for:
   - each KDN/DataPlane link;
   - Cache Load for each target Instance;
   - each Instance Prefill Slot;
   - Decode occupancy summaries.
3. Support network transfer in parallel with Prefill/Decode for other requests.
4. Support parallel preparation of multiple knowledge blocks for one request across different links or Workers.
5. Support Transfer Coalescing and Single-flight to reduce small-task overhead and duplicate bytes.
6. Support bounded Look-ahead: prepare upcoming KV while executable compute work still exists, subject to bandwidth and memory budgets.
7. Use event-driven wakeups rather than fixed-interval polling as the primary release mechanism.
8. Define and measure:
   - network-compute overlap ratio;
   - GPU idle due to cache wait;
   - network idle with queued transfer;
   - serialized baseline time;
   - pipeline makespan;
   - overlap saved time;
   - TTFT and throughput changes.
9. Establish three comparison baselines: serialized, simple text_bypass, and full parallel execution.

### Acceptance Criteria

- Other computable requests continue executing during KV transfer.
- Multiple links and multiple Instances are not serialized by one global lock.
- When parallelism exists in the workload, Pipeline Makespan outperforms the serialized baseline.
- Parallel execution preserves request-order constraints and response correctness.
- Parallelism benefits can be reproduced through Trace and Benchmark results.

## v0.1.17: Queue Generality, Stability, and Policy Interfaces

### Problem to Solve

Parallelism alone is not enough across different models, backends, bandwidths, and injection ratios. The system also needs admission, backpressure, fairness, fault handling, and adaptive concurrency.

### Main Steps

1. Establish hierarchical admission and backpressure for:
   - total requests;
   - each Instance;
   - each link;
   - each LMCache management endpoint or worker group;
   - optional per-tenant or per-experiment-group budgets.
2. Support priority, Aging, Deadline Hint, and Starvation Protection.
3. Support fragmentation or yielding for large KV tasks so they do not monopolize a link.
4. Provide one queue-policy interface for text, KV, Hybrid, and multi-block Fusion.
5. Support adaptive concurrency: adjust Transfer / Load concurrency based on observed throughput, queueing, and error rate, while preserving a static mode for experiments.
6. Establish fallback and circuit breaking for:
   - KDN control-plane unavailability;
   - overloaded LMCache endpoints or worker groups;
   - network timeout;
   - LMCache Load failure;
   - Instance removal;
   - exhausted retry budget.
7. Ensure retries never gain unbounded priority over new requests, preventing retry storms.
8. Expose policy plugins: Priority Policy, Bypass Policy, Concurrency Policy, and Admission Policy.
9. Establish a generality experiment matrix covering:
   - different models and KV sizes;
   - single/multiple KDNs;
   - single/multiple Instances;
   - low/high bandwidth and different RTTs;
   - text/KV/Hybrid ratios;
   - uniform, bursty, hot-spot, and long-tail workloads.
10. Focus on mechanism stability; do not introduce Pareto or learning-based global scheduling in this release.

### Acceptance Criteria

- Text tasks do not starve permanently under heavy KV load.
- KV tasks receive a configurable service share under heavy text load.
- Overload produces explicit reject, degrade, or backpressure outcomes.
- Faults do not cause permanent hangs, reference leaks, or infinite retries.
- The same mechanism covers single-knowledge, Hybrid, and multi-knowledge preparation.
- Experiments can switch policies independently and reproduce results.

## v0.1.18: Knowledge-Aware Policy over LMCache

### Problem to Solve

After semantic identity, LMCache observations, and queue feedback stabilize, KDN can research knowledge-aware cache policy without implementing storage mechanisms already owned by LMCache.

### Main Steps

1. Build unified value statistics from hit tokens, saved Prefill, transfer/load cost, queue wait, failures, and observation confidence.
2. Discover storage adapters, capacity summaries, quotas, and supported management operations from LMCache.
3. Implement admission and retention intent; translate feasible actions to LMCache Pin/Unpin, Prefetch, Move/Copy, Clear/Delete, quota, or backend operations.
4. Use LMCache's existing eviction mechanisms as the physical baseline; do not create a competing block-level eviction engine in CacheRoute.
5. Implement at least one explainable knowledge-value policy and compare it with LMCache's configured baseline behavior.
6. Protect online work with budgets for background prefetch/move/clear operations.
7. Treat unsupported operations and stale capacity observations as policy constraints.
8. Provide Dry-run and Trace Replay that simulate decisions independently of one backend.
9. Feed policy outcomes back into CachePlan and queue experiments without bypassing LMCache.

### Acceptance Criteria

- policies issue only supported LMCache operations through the adapter;
- CacheRoute can compare no-policy, LMCache baseline, and knowledge-aware policy behavior;
- policy decisions and physical LMCache outcomes are separately traceable;
- background policy work does not destabilize online queues;
- no CacheRoute-owned physical cache store or duplicate chunk eviction loop is introduced.

## v0.1.19: Multi-Knowledge-Block Non-Prefix Fusion

### Problem to Solve

Multiple knowledge blocks are currently handled mainly through text concatenation and cannot express non-prefix positions, partial hits, overlap, or preparation from multiple sources.

### Main Steps

1. Represent request knowledge as an ordered Knowledge Block list and construct Prompt Layout.
2. Query compatible Artifacts and Replicas for each block.
3. Classify full, partial, non-prefix, overlapping, and missing matches.
4. Construct a Coverage Map to prevent duplicate coverage of the same token.
5. Generate FusionPlan with Artifact, source, target, recompute ranges, order, fallback, and risk.
6. Compile FusionPlan into ExecutionGraph:
   - multiple blocks may transfer in parallel;
   - the same Artifact shares one task;
   - downstream nodes trigger after local dependencies are satisfied;
   - required blocks complete before fusion.
7. Integrate LMCache non-prefix reuse, CacheBlend, or equivalent public interfaces.
8. Support selective recomputation and quality protection.
9. On unsupported capability or failure, degrade in order to single-prefix KV, partial KV + text, and full text.
10. Establish experiments across block count, order, hit ratio, network tier, and recomputation ratio.

### Acceptance Criteria

- At least two knowledge blocks support non-prefix fusion reuse.
- Multi-block preparation uses queue parallelism without creating duplicate-task storms.
- Actual hit tokens, recomputed tokens, transfer cost, and fusion cost are observable.
- Quality or runtime failures trigger correct fallback.
- Results are correct and reproducible against pure-text and single-prefix baselines.

## v0.2.0: Integration, Stability, and Research-Baseline Release

### Main Steps

1. Freeze KnowledgeObject, CacheArtifact intent, logical CacheReplica observation, LMCacheEndpoint, DataPlaneTask, CachePlan, FusionPlan, ExecutionGraph, and Trace schemas.
2. Publish an LMCache capability matrix for supported modes and operations.
3. Complete migration guidance for Legacy `kv_ready`, dump directories, and direct Redis injection.
4. Complete end-to-end scenarios:
   - single-knowledge text and KV reuse;
   - LMCache lookup-driven local/remote hit planning;
   - network KV preparation and pure computation in parallel;
   - Hybrid mixed workloads;
   - multi-block partial hit and non-prefix fusion;
   - unsupported-operation and stale-observation fallback;
   - KDN, LMCache endpoint, and Instance restart recovery;
   - knowledge-aware policy issuing LMCache-supported operations.
5. Establish fault tests for KDN unavailability, LMCache management endpoint unavailability, stale lookup results, task interruption, transfer timeout, Instance generation change, and fallback races.
6. Establish a unified Benchmark covering TTFT, throughput, matched/recomputed tokens, queue breakdown, network bytes, overlap ratio, GPU cache-wait idle, provider-operation duration, observation freshness, fallback rate, and quality.
7. Compare serialized preparation, text_bypass, work-conserving parallelism, static/adaptive concurrency, LMCache baseline, and CacheRoute knowledge-aware policy.
8. Ensure Proxy UI and KDN Debug APIs show logical desired state separately from LMCache-observed state.
9. Keep every experimental capability independently configurable with safe defaults.

### v0.2.0 Release Criteria

- LMCache is the sole target physical KVCache storage/transfer plane;
- KDN stores knowledge semantics, logical Artifact intent, policy, and orchestration history rather than KV data structures;
- Proxy KVCache Manager derives per-Instance state from LMCache public queries/events or clearly marked inference;
- CacheRoute supports at least one LMCache management mode end to end and provides structured fallback for unsupported operations;
- network KV preparation overlaps independent compute work safely;
- queueing provides Single-flight, admission, backpressure, fairness, cancellation, retry, and fallback;
- at least two knowledge blocks support non-prefix fusion with quality protection;
- knowledge-aware policy has reproducible results against an LMCache baseline;
- Legacy paths remain compatible but are clearly separated from the target architecture;
- key faults have automated tests or reproducible scripts.

## 8. Knowledge Injection and Compute Queue Research Framework

### 8.1 Core Research Question

CacheRoute’s differentiating capability is not simply choosing text or KV. It is:

> Given that knowledge preparation incurs network, storage, and loading latency, while model computation incurs GPU queueing and execution latency, how can dependency-aware, multi-resource queue orchestration maximize overlap among knowledge transfer, cache loading, and pure computation while preserving correctness, fairness, and reliable fallback?

### 8.2 Required System Invariants

- Computation whose dependencies are unsatisfied cannot execute early.
- Work that does not depend on a slow task cannot be blocked by unrelated dependencies.
- A shared preparation task executes only once.
- Blocking in one resource class must not freeze other resource classes.
- Cancellation, failure, and timeout propagate through the dependency graph.
- Fallback must not inject the same knowledge twice.
- Resource budgets, reference counts, and task states eventually converge.
- The same input, catalog snapshot, and policy parameters produce a reproducible plan.

### 8.3 Policy Interfaces

```text
AdmissionPolicy
PriorityPolicy
BypassPolicy
ConcurrencyPolicy
RetryPolicy
FallbackPolicy
ReleasePolicy
```

Policy inputs include task type, dependencies, estimated cost, actual queues, links, Instances, cache state, Deadline Hint, and experiment labels. Policy outputs may adjust only priority, budget, bypass, fallback, and concurrency; they cannot bypass state-machine correctness.

### 8.4 Key Evaluation Metrics

- TTFT and tail latency;
- throughput and completion time;
- Network-Compute Overlap Ratio;
- GPU Idle Due to Cache Wait;
- Network Idle With Pending Work;
- Queue Wait Breakdown;
- Pipeline Makespan / Serialized Makespan;
- Head-of-line Blocking Time;
- fairness across Text, KV, and Hybrid;
- task and byte savings from Single-flight;
- fallback, cancellation, retry, and task-leak rates.

### 8.5 Priority Experiments

1. Fix request count and vary the text/KV ratio.
2. Fix compute capacity and vary link bandwidth and RTT.
3. Fix the network and vary knowledge-block size and hit rate.
4. Scale from one KDN and one Instance to multiple KDNs and multiple Instances.
5. Compare uniform, bursty, hot-spot, and long-tail Artifacts.
6. Compare serialized, text_bypass, static parallel, and adaptive parallel execution.
7. Measure online interference with background maintenance disabled and enabled.
8. Vary multi-block order, sharing, and parallel-loading ratio.

## 9. LMCache Integration and KDN Interface Framework

### 9.1 KDN Semantic and Policy Interfaces

- Knowledge Catalog Query;
- Artifact Intent and Compatibility Query;
- Desired-State / Policy-State Update;
- CachePlan Input Query;
- Maintenance Decision / Dry-run;
- Task Create / Cancel / Inspect;
- Event / Observation Ingest;
- Reconcile / Repair;
- Trace and Experiment Export.

### 9.2 LMCache Adapter Capability Categories

- Capability / Configuration Discovery;
- Lookup and Matched-Token/Location Query;
- Worker / Instance / Endpoint Health;
- Object / Backend / Tier Status;
- Retrieve / Prefetch and Completion;
- Move / Copy / Replicate where supported;
- Pin / Unpin where supported;
- Clear / Delete where supported;
- KV Event Ingest;
- Runtime Metrics and Structured Errors.

### 9.3 Adapter Rules

- use public LMCache Controller, CacheEngine, MP HTTP/coordinator, and plugin interfaces;
- negotiate capabilities rather than assuming all modes expose identical APIs;
- return `unsupported`, `unknown`, or `stale` explicitly;
- keep provider object references opaque and non-secret;
- do not copy LMCache's internal token database, chunk index, serializer, or eviction implementation;
- prefer extending LMCache plugins/connectors for new storage backends;
- isolate Legacy direct Redis/filesystem behavior in a compatibility adapter.

### 9.4 Flexibility Enabled by This Boundary

- LMCache backend changes do not require changes to KDN knowledge semantics;
- CacheRoute policy can operate across heterogeneous LMCache backends;
- Proxy can query actual Instance cache state without owning the physical index;
- Controller and MP deployments can coexist behind adapters;
- experiments can replace policy and queue strategies independently of storage implementation;
- LMCache improvements automatically become available to CacheRoute through the adapter capability layer.

## 10. KDN Maintenance-Policy Research Framework

### 10.1 Policy Inputs

- Artifact size, token count, and construction cost;
- recent and long-term access frequency;
- hit tokens and actual Prefill savings;
- network queueing, transfer, Cache Load, and selective-recompute costs;
- storage tiers, target-Instance distribution, and replica failure domains;
- capacity watermarks, online tasks, and maintenance budgets;
- Pin, experiment, and tenant constraints;
- multi-knowledge-block co-occurrence;
- predicted values and confidence.

### 10.2 Policy Outputs

```text
ADMIT / REJECT_BUILD
KEEP / EVICT
PIN / UNPIN
REPLICATE / REMOVE_REPLICA
PROMOTE_TIER / DEMOTE_TIER
PREFETCH / CANCEL_PREFETCH
REFRESH / REBUILD
```

### 10.3 Evaluation Metrics

- request TTFT, tail latency, and throughput;
- KV hit tokens and saved GPU time;
- capacity utilization, write amplification, and cache churn;
- network transfer volume and interference with online queues;
- prefetch accuracy and pollution rate;
- multi-knowledge-block fusion benefit;
- failure recovery and policy stability.

## 11. State Boundaries Across Proxy, KDN, and LMCache

### KDN Control Plane Is Authoritative for Knowledge Semantics and Intent

It owns KnowledgeObject identity/version, Artifact compatibility, desired state, policy constraints, Pins as intent, experiment metadata, and orchestration history.

### LMCache Is Authoritative for Physical Cache State

It owns cache-object/chunk existence, locations, storage tiers, physical Pins, load/save/move/clear execution, worker health, and backend-specific errors.

### CacheRoute DataPlaneTask Is an Orchestration Record

It tracks a requested LMCache operation, provider task/event identity, timeout, retry budget, and normalized result. It does not replace LMCache execution state.

### Proxy Owns Short-Lived Request and Instance Observations

It maintains CachePlan/FusionPlan/ExecutionGraph, shared preparation references, and a TTL-bounded view derived from LMCache lookup/status/events. Every observation records source, time, freshness, and confidence.

### Instance / vLLM Is Authoritative for Model Execution

It reports actual submission, Prefill/Decode execution, matched/recomputed tokens where exposed, and request completion.

A KDN Artifact marked logically usable does not prove physical residency. A Proxy observation expiring does not delete an LMCache object. A successful policy decision does not count as a successful cache operation until LMCache confirms it.

## 12. Testing and Experiment Requirements

### 12.1 Unit Tests

- immutable Artifact / logical Replica / DataPlaneTask / QueueWork state contracts;
- LMCache adapter capability negotiation and structured unsupported results;
- desired-state versus observed-state reconciliation;
- observation source, freshness, confidence, and expiry;
- ExecutionGraph dependency, cancellation, and fallback;
- Single-flight and LMCache query coalescing;
- CachePlan / FusionPlan determinism;
- Trace predicted/actual/source separation;
- Legacy read-only mapping.

### 12.2 Component Tests

- KDN semantic catalog with Mock LMCache adapter;
- Controller-mode and MP-mode adapter fixtures where practical;
- lookup/status/event-driven Proxy KVCache view;
- recovery after KDN or LMCache endpoint restart;
- QueueCoordinator multi-resource parallelism;
- policy Dry-run versus normalized LMCache execution result;
- no dependency on private Redis keys or serialization formats.

### 12.3 End-to-End Tests

- complete vLLM + LMCache + CacheRoute startup;
- text, prefix KV, Hybrid, partial KV, and multi-block fusion;
- LMCache lookup-driven cache planning;
- network preparation and pure computation in parallel;
- supported policy operations and unsupported-operation fallback;
- stale observation, endpoint failure, and restart recovery;
- Legacy path regression without making Legacy the target architecture.

### 12.4 v0.1.10 Regression Gate

- #138 capability tests remain passing;
- #139 state models remain storage-neutral and immutable;
- #140 protocol mocks reflect LMCache-aligned operations;
- #141 traces identify LMCache observation sources;
- `test/test_kv_injector_reuse.py` no longer performs external network requests during generic pytest collection;
- core CPU-only tests can run without a GPU or live LMCache server.

### 12.5 Experiment Reproduction

Every experiment stores:

- configuration and code revision;
- vLLM and LMCache version/mode;
- enabled LMCache storage and transport adapters;
- workload Trace and initial knowledge catalog;
- KDN policy and queue parameters;
- request-level ExecutionGraph;
- raw LMCache observations/events and normalized CacheRoute records;
- aggregate metrics, fallback reasons, and anomalies.

## 13. Version Dependencies and Parallel-Development Guidance

```text
v0.1.10
   |
v0.1.11
   |
v0.1.12
   |
v0.1.13
   |
v0.1.14
   |
v0.1.15
   |
v0.1.16
   |
v0.1.17
   +-------------------------+
   |                         |
v0.1.18                  v0.1.19 planning/tooling
   |                         |
   +------------+------------+
                |
             v0.1.19
                |
             v0.2.0
```

Work that can proceed in parallel:

- prepare Trace Schema and capability fingerprints during v0.1.10;
- develop catalog-migration tools during v0.1.11;
- develop Mock LMCache Controller/MP adapters during v0.1.12;
- prepare the ExecutionGraph test model during v0.1.14;
- establish serialized and parallel Benchmarks throughout v0.1.15–v0.1.17;
- design maintenance-policy interfaces and multi-block workloads in parallel after v0.1.17;
- v0.1.18 background tasks must reuse the low-priority budgets and backpressure introduced in v0.1.17;
- v0.1.19 must reuse ExecutionGraph rather than creating a second fusion queue.

## 14. After v0.2.0

After v0.2.0, build on stable cache facts, data tasks, and queue feedback to pursue:

1. `kv_aware` Proxy Instance routing;
2. joint candidate selection across KDN, Proxy, and Instance;
3. layered Pareto filtering;
4. SLO-aware and uncertainty-aware scheduling;
5. LMCache MP / P2P and high-performance data planes;
6. Prefill / Decode or Encoder / Prefill / Decode disaggregation;
7. multi-tenant quotas, fairness, and production-grade high availability.

These capabilities should be built on trustworthy knowledge semantics, an LMCache-aligned integration plane, fresh runtime observations, and parallel knowledge/compute queues delivered by v0.2.0. CacheRoute should continue tracking LMCache public API evolution and retire compatibility adapters when stable equivalents become available.