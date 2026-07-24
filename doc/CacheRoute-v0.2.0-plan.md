# CacheRoute v0.2.0 Evolution Plan

> Status: Planning draft  
> Current baseline: v0.1.9  
> Target release: v0.2.0  
> Core foundation: vLLM + LMCache  
> Core research directions: KDN control/data planes, knowledge-oriented KVCache maintenance, Proxy KVCache Management, parallel knowledge injection and compute queues, and multi-knowledge-block non-prefix fusion reuse

## 1. Overall Goal

CacheRoute v0.2.0 is not intended to reimplement a KVCache storage system or to prioritize a complex global scheduling algorithm. Its goal is to establish a control, execution, and maintenance framework for knowledge reuse on top of vLLM and LMCache.

v0.2.0 should form the following complete closed loop:

```text
Knowledge registration
  -> KVCache artifact construction
  -> KDN control-plane registration, validation, and maintenance
  -> KDN data-plane publication, transfer, and migration
  -> Proxy builds a request-level CachePlan / ExecutionGraph
  -> Knowledge-preparation queues and pure-compute queues progress in parallel
  -> LMCache / vLLM loads, reuses, fuses, or selectively recomputes
  -> Report hit, queueing, transfer, loading, compute, and quality results
  -> KDN retains, evicts, replicates, migrates, and prefetches based on feedback
```

v0.2.0 focuses on five interdependent tracks.

### 1.1 KDN Control Plane

The KDN control plane should evolve from the current combined state of “text knowledge base + KV dump files + `kv_ready` flag” into the authoritative catalog for knowledge objects and KVCache artifacts. It is responsible for:

- distinguishing KnowledgeObject, CacheArtifact, and CacheReplica;
- maintaining artifact compatibility, lifecycle, location, tier, capacity, and maintenance state;
- receiving data-plane capability registrations, health status, and task results;
- generating build, publish, replicate, migrate, prefetch, and eviction tasks;
- providing stable, lightweight, versioned query and task interfaces;
- avoiding large KV data transfers through control requests, and avoiding Redis internal keys, credentials, or large binary payloads in control-plane messages.

### 1.2 KDN Data Plane

The KDN data plane executes actual KVCache data operations and can be scaled, replaced, and fault-isolated independently:

- publish, read, transfer, replicate, migrate, verify, and delete artifacts;
- connect to LMCache, Legacy Redis, CPU, NVMe, P2P, NIXL, Mooncake, or other runtime backends;
- expose a unified DataPlaneEndpoint and asynchronous TransferTask abstraction;
- return actual byte counts, queueing time, transfer time, source/target tiers, and error categories;
- support horizontal scaling across multiple Data Workers, while the control plane maintains capability and load summaries;
- prevent data-plane failures from breaking the KDN catalog service, and prevent control-plane failures from immediately terminating already-authorized data tasks.

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

### 1.4 KDN KVCache Maintenance Policies

After the foundation is stable, KDN research should focus on:

- which knowledge is worth materializing and admitting as KVCache;
- which artifacts should be retained or evicted under capacity constraints;
- where hot artifacts should be replicated: another KDN, a resource pool, a storage tier, or near a specific Instance;
- when to prefetch, migrate, refresh, or rebuild;
- how to use Proxy queue feedback, network costs, compute savings, and multi-block co-occurrence;
- how to avoid cache pollution, maintenance oscillation, and background-task interference with online requests.

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
- Do not yet own fine-grained KV lifecycle, data transfer, or queue execution

KDN Control Plane
- Maintain authoritative knowledge, Artifact, Replica, policy, and task state
- Generate and track data-plane tasks
- Exchange only metadata, task tickets, capability summaries, and results

KDN Data Plane
- Execute actual KV publication, transfer, replication, migration, verification, and deletion
- Connect to LMCache or other backends through Adapters
- Do not own global maintenance policy or request routing

Proxy
- Maintain request-level and Instance-level KVCache working views
- Build CachePlan, FusionPlan, and ExecutionGraph
- Coordinate knowledge-preparation queues and compute queues
- Do not become the authoritative global KVCache metadata database

Instance
- Act as the execution adapter between Proxy and vLLM / LMCache
- Report capabilities, cache events, and execution results
- Do not own global cache-placement decisions

LMCache
- Own actual KVCache storage, loading, transfer, serialization, and vLLM integration
- CacheRoute must not duplicate lower-level capabilities already provided by LMCache

vLLM
- Own model execution, paged KV management, and engine-internal scheduling
- Proxy controls when request dependencies are satisfied and when requests are submitted, without modifying the vLLM internal Scheduler
```

### 2.2 KDN Control-Plane and Data-Plane Principles

1. Control-plane APIs do not directly carry large KVCache payloads.
2. The control plane returns Artifact, Replica, Endpoint, Lease, and Task IDs.
3. The data plane executes operations through short-lived task tickets or Leases.
4. Data Workers can register, unregister, and scale horizontally independently.
5. The control plane stores task state and result summaries, without polling or duplicating detailed transfer progress.
6. The data plane must be idempotent; repeated submission of the same task must not create duplicate replicas or damage existing data.
7. The control and data planes expose separate health, capacity, queue, and error statistics.
8. The Legacy Redis path is encapsulated as one DataPlane Adapter rather than remaining the only KDN data interface.

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

CacheRoute can already use vLLM + LMCache + Redis for KVCache construction and reuse experiments. Future work should continue using LMCache capabilities such as:

- the vLLM KV Connector;
- external KV matched-token queries;
- asynchronous load and save;
- CPU, disk, Redis, P2P, or other backends;
- non-prefix reuse and CacheBlend-like capabilities;
- KV events and runtime observability.

The key objective of v0.2.0 is not to replace the lower layer, but to establish stable CacheRoute control and execution interfaces so KDN and Proxy no longer depend on the internal representation of one LMCache backend.

## 4. v0.2.0 Target Architecture

```text
                              Scheduler
                                  |
                      global knowledge-aware route
                                  |
                                Proxy
  +-------------------+-----------+---------------------------+
  |                   |                                       |
Request Admission  Proxy KVCache Manager              Queue Coordinator
- validate         - local cache view                 - dependency graph
- choose fallback  - per-instance view                - resource budgets
- create trace     - CachePlan / FusionPlan            - event-driven release
  |                   |                                       |
  |                   +-------------------+-------------------+
  |                                       |
  |                         Knowledge Preparation Plane
  |                 +-------------+-------------+-------------+
  |                 |             |             |             |
  |             metadata       network KV    cache load   fusion prepare
  |              resolve        transfer        wait          tasks
  |                 |             |             |             |
  |                 +-------------+-------------+-------------+
  |                                       |
  +---------------------------- Compute Plane
                         +------------+------------+
                         |                         |
                    pure/residual Prefill       Decode
                         |                         |
                         +------------+------------+
                                      |
                              Instance / vLLM
                                      |
                                   LMCache

                         KDN Control Plane
       +----------------------+----------------------+------------------+
       |                      |                      |                  |
Knowledge Catalog    Artifact/Replica Catalog  Maintenance Engine  Task Registry
       |                      |                      |                  |
       +----------------------+-----------+----------+------------------+
                                          |
                            task ticket / lease / result
                                          |
                            KDN Data Plane Workers
                 +----------------+----------------+----------------+
                 |                |                |                |
          LMCache Adapter  Legacy Redis Adapter  P2P Adapter   other backends
```

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

Represents one concrete accessible location for an Artifact:

```text
replica_id
artifact_id
data_plane_id
backend_type
backend_instance_id
storage_tier
location
state
size_bytes
last_verified_at
last_access_at
access_count
health
```

### 5.4 DataPlaneEndpoint

```text
data_plane_id
endpoint
backend_types
transport_capabilities
storage_tiers
capacity
queue_depth
active_tasks
health
generation
last_heartbeat_at
```

### 5.5 DataPlaneTask

```text
task_id
idempotency_key
operation
artifact_id
source_replica
target_endpoint
target_instance
lease_id
state
priority
payload_bytes
queued_at
started_at
finished_at
result
error
```

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
| v0.1.10 | Contract and observability baseline | Compatibility fingerprints, control/data-plane contracts, Queue Trace |
| v0.1.11 | KDN control-plane catalog | KnowledgeObject / Artifact / Replica / Task Registry |
| v0.1.12 | KDN data-plane foundation | Data Worker, Runtime Adapter, Task Ticket, capability registration |
| v0.1.13 | KDN lifecycle and recovery | Atomic publication, Reconcile, control/data-plane fault isolation |
| v0.1.14 | Proxy KVCache Manager | Per-Instance cache view, CachePlan, Single-flight foundation |
| v0.1.15 | Injection and compute queue model | ExecutionGraph, resource queues, dependency release, compute fast path |
| v0.1.16 | Network/compute parallel pipeline | Work-conserving parallelism, link/Instance timelines, Overlap Benchmark |
| v0.1.17 | Queue generality and stability | Admission, backpressure, fairness, aging, adaptive concurrency, fault fallback |
| v0.1.18 | KDN maintenance policies | TTL/LRU, value, replication, migration, prefetch, Trace Replay |
| v0.1.19 | Multi-block non-prefix fusion | Matching plan, parallel preparation, selective recomputation, quality fallback |
| v0.2.0 | Integration and stable release | Complete closed loop, fault tests, benchmarks, stable interfaces, research baseline |

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

## v0.1.11: KDN Control-Plane Catalog

### Problem to Solve

Current knowledge records, KV state, and file locations are coupled and cannot support multi-model Artifacts, multiple replicas, or an independent data plane.

### Main Steps

1. Preserve legacy tables and add or abstract KnowledgeObject, CacheArtifact, CacheReplica, DataPlaneEndpoint, and Task Registry.
2. Establish one-to-many relationships: one KnowledgeObject to multiple Artifacts, and one Artifact to multiple Replicas.
3. Generate stable Artifact IDs and Replica IDs.
4. Map `KV_database/<kid>` to a Legacy Artifact / Replica without immediately moving files.
5. Extend query interfaces to:
   - query Artifacts by knowledge and compatibility;
   - query Replicas and DataPlaneEndpoints;
   - query capacity, state, and tasks;
   - preserve text-query interfaces.
6. Expose only coarse Artifact availability to Scheduler snapshots, without propagating large-scale replica details.
7. Add migration, catalog validation, and Debug APIs.

### Acceptance Criteria

- The same knowledge can register Artifacts for multiple models or configurations.
- The same Artifact can register multiple data-plane replicas.
- Legacy `kv_ready` can map to a Legacy Artifact.
- Control-plane queries do not require access to KV dump contents.

## v0.1.12: KDN Data-Plane Foundation

### Problem to Solve

The current KDN service handles catalog state, files, and Redis injection together, making backend replacement, independent scaling, and transfer-failure isolation difficult.

### Main Steps

1. Define Data Worker lifecycle and capability registration.
2. Define the Cache Runtime Adapter:
   - query;
   - publish;
   - transfer / prefetch;
   - wait / cancel;
   - verify;
   - evict;
   - collect stats.
3. Implement LMCacheRuntimeAdapter, preferring public APIs, events, or CLI interfaces.
4. Encapsulate current Redis injection as LegacyRedisAdapter.
5. Let the control plane create DataPlaneTasks and return Task Tickets / Leases, without forwarding large payloads or Redis credentials to Proxy.
6. Let Data Workers execute tasks and proactively report results, with idempotency, retry, and cancellation support.
7. Allow multiple Workers to register the same backend type and report capacity, concurrency, queue, and health.
8. Provide a Mock Adapter and fault injection for GPU-less CI.

### Acceptance Criteria

- The control plane and data plane can run as independent processes.
- Proxy does not need to understand LMCache Redis keys.
- Repeated submission of the same task does not create duplicate replicas.
- Data Worker failures return structured errors.
- The Legacy Redis path remains available for regression testing.

## v0.1.13: KDN Lifecycle, Consistency, and Recovery

### Problem to Solve

Catalog records, files, and backend replicas can become inconsistent. Control/data-plane restarts or interrupted tasks may leave incorrect READY states.

### Main Steps

1. Implement state machines for Artifact, Replica, and DataPlaneTask.
2. Use two-phase publication: BUILDING -> STAGING -> READY.
3. Validate Checksum, size, Manifest, and Schema Version.
4. Implement Reconcile for:
   - metadata records whose data is missing;
   - data whose metadata record is missing;
   - unfinished tasks, temporary directories, and expired Leases;
   - Worker generation changes;
   - damaged Replicas and orphaned data.
5. Recover task state after control-plane restart, and have data-plane Workers report unfinished tasks after reconnecting.
6. Use DELETING for removal and wait for references and tasks to be released.
7. When the control plane is unavailable, authorized tasks may finish within their Lease; when the data plane is unavailable, catalog queries remain available.
8. Expose recovery statistics, recent failures, and manual Reconcile tools.

### Acceptance Criteria

- Artifacts under construction are not reused incorrectly.
- Consistent state can be restored after independent control-plane and data-plane restarts.
- Artificially damaged replicas are detected and excluded from reuse.
- Duplicate tasks and expired Leases can be cleaned up.
- Deletion failures do not create falsely available objects.

## v0.1.14: Proxy KVCache Manager

### Problem to Solve

Proxy lacks a unified per-Instance cache view, request CachePlan, and shared preparation-task management.

### Main Steps

1. Introduce Proxy KVCache Manager with:
   - Artifact-summary cache;
   - per-Instance accessible, loading, loaded, failed, and expired views;
   - DataPlaneTask / Cache Load Task mapping;
   - CachePlan / FusionPlan management;
   - LMCache / Instance event ingestion.
2. Define local states: UNKNOWN, AVAILABLE_REMOTE, TRANSFERRING, LOADING, AVAILABLE_LOCAL, FAILED, and EXPIRED.
3. Converge `ProxyTask` cache fields into `cache_plan` and `cache_trace`, while retaining compatibility mirrors.
4. Implement Single-flight for the same Artifact and target Instance.
5. Invalidate local views when an Instance restarts, its generation changes, or it unregisters.
6. Add Debug APIs for CachePlans, cache views, shared tasks, and errors.

### Acceptance Criteria

- Proxy distinguishes globally present, transferring, target-loadable, and locally available states.
- Concurrent requests for the same target share one preparation task.
- Proxy does not reuse stale local state after an Instance restart.
- Current text and single-knowledge KV paths remain compatible.

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
   - each Data Worker;
   - optional per-tenant or per-experiment-group budgets.
2. Support priority, Aging, Deadline Hint, and Starvation Protection.
3. Support fragmentation or yielding for large KV tasks so they do not monopolize a link.
4. Provide one queue-policy interface for text, KV, Hybrid, and multi-block Fusion.
5. Support adaptive concurrency: adjust Transfer / Load concurrency based on observed throughput, queueing, and error rate, while preserving a static mode for experiments.
6. Establish fallback and circuit breaking for:
   - KDN control-plane unavailability;
   - overloaded Data Workers;
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

## v0.1.18: KDN KVCache Maintenance Policies

### Problem to Solve

After the catalog, data plane, and queue feedback are stable, KDN can safely research cache admission, eviction, replication, migration, and prefetching.

### Main Steps

1. Establish unified access and benefit statistics: hit count, hit tokens, Prefill saved, transfer cost, queue wait, failures, and references.
2. Establish Backend / Tier models for capacity, watermarks, reservation, and reclaimable space.
3. Implement baseline admission, TTL, LRU, Pin, and safe eviction.
4. Implement at least one explainable value-aware policy and compare it with LRU.
5. Support hot replicas, tier promotion/demotion, failure rollback, and last-replica protection.
6. Support budget-constrained prefetching using Proxy target Instances, queue-idle windows, and historical sequences.
7. Run background maintenance tasks under a separate low-priority budget so they do not compete without limits against online NET_KV work.
8. Provide Dry-run and Trace Replay to compare hit rate, capacity, transfer volume, compute savings, and queue interference offline.
9. Use multi-knowledge-block co-occurrence as an optional feature to prepare for v0.1.19.

### Acceptance Criteria

- TTL/LRU and at least one value-aware policy can be selected by configuration.
- Active references, hard pins, and the last healthy replica are not deleted incorrectly.
- Background maintenance does not destabilize online queues.
- Hot-replica and prefetch decisions are traceable.
- Trace Replay produces comparable results.

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

1. Freeze KnowledgeObject, CacheArtifact, CacheReplica, DataPlaneEndpoint, DataPlaneTask, CachePlan, FusionPlan, ExecutionGraph, and Trace Schema.
2. Complete migration and deprecation guidance for legacy `kv_ready` and Redis injection.
3. Complete end-to-end scenarios:
   - single-knowledge text;
   - single-knowledge KV;
   - network KV and pure computation in parallel;
   - Hybrid mixed workloads;
   - multi-knowledge partial hits and non-prefix fusion;
   - KDN/Data Worker/LMCache failure fallback;
   - KDN restart recovery;
   - Instance restart and local-state invalidation;
   - maintenance policies triggered by watermarks.
4. Establish fault tests for control-plane unavailability, data-plane unavailability, interrupted tasks, damaged files, transfer timeout, Instance removal, concurrent eviction, and migration failure.
5. Establish a unified Benchmark covering:
   - TTFT P50/P95/P99 and throughput;
   - KV hit-token ratio and residual Prefill;
   - network bytes, queue wait, and transfer time;
   - network/compute utilization and Overlap Ratio;
   - GPU Cache-wait Idle;
   - Pipeline Makespan against the serialized baseline;
   - cache capacity, write amplification, and maintenance counts;
   - fallback rate, error rate, fusion benefit, and quality.
6. Provide policy baselines:
   - serialized preparation;
   - text_bypass;
   - work-conserving parallelism;
   - static and adaptive concurrency;
   - no maintenance, TTL, LRU, and value-aware maintenance;
   - no fusion, prefix reuse, and non-prefix fusion.
7. Complete documentation for architecture, KDN planes, queueing mechanisms, maintenance policies, Fusion, deployment, migration, and experiment reproduction.
8. Proxy UI and KDN Debug APIs can display task graphs, resource queues, data-plane state, and key parallelism metrics; a complete KDN frontend is not a release blocker.
9. All experimental capabilities can be enabled or disabled independently, with explicit defaults and clear errors for invalid combinations.

### v0.2.0 Release Criteria

- KDN control and data planes can be deployed, scaled, and recovered independently.
- KDN reliably maintains multi-model, multi-configuration Artifacts and multiple replicas.
- Proxy has an independent KVCache Manager, CachePlan, and ExecutionGraph.
- Network KVCache transfer can execute in parallel with independent pure-compute tasks.
- The queueing mechanism provides Single-flight, admission, backpressure, fairness, cancellation, retry, and fallback.
- At least two knowledge blocks support non-prefix fusion.
- KDN provides at least TTL/LRU and one value-aware maintenance policy.
- vLLM / LMCache execution details are isolated through Adapters.
- Current text, single-knowledge, and Legacy paths remain compatible.
- Key fault scenarios have automated tests or reproducible scripts.
- Queue parallelism, maintenance policies, and fusion capabilities all have reproducible experimental results.

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

## 9. KDN Control-Plane and Data-Plane Interface Framework

### 9.1 Control-Plane Interface Categories

- Catalog Query;
- Artifact / Replica Lifecycle;
- DataPlane Registration / Heartbeat;
- Task Create / Cancel / Inspect;
- Lease Issue / Renew / Expire;
- Maintenance Decision / Dry-run;
- Event / Result Ingest;
- Reconcile / Repair.

### 9.2 Data-Plane Interface Categories

- Publish;
- Fetch / Prefetch;
- Copy / Replicate;
- Promote / Demote;
- Verify;
- Delete;
- Task Status / Result;
- Runtime Metrics.

### 9.3 Flexibility Enabled by Separation

- LMCache backend changes do not require changes to the KDN catalog model.
- One KDN control plane can manage multiple heterogeneous Data Workers.
- Data Workers can be deployed on KDN nodes, in Proxy resource pools, or near Instances.
- Different transfer backends can be selected according to capability and deployment environment.
- Maintenance policies generate tasks rather than operating backends directly.
- Network experiments can replace DataPlane Adapters without contaminating control APIs.
- Control and data planes can be load-tested, fault-injected, and scaled independently.

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

## 11. State Boundaries Across Proxy, KDN, and Runtime

### KDN Control Plane Is the Global Authoritative State

It maintains Artifact integrity, compatibility, Replicas, capacity, Pins, policies, tasks, and global access statistics.

### KDN Data Plane Is the Source of Truth for Data Tasks

It maintains actual data-operation progress, bytes, source/target locations, backend errors, and final results.

### Proxy Owns Short-Lived Execution State

It maintains target-Instance accessibility, shared preparation tasks, CachePlan/FusionPlan/ExecutionGraph, short-lived negative cache entries, queue state, and feedback buffers.

### Instance / LMCache Is the Runtime Source of Truth for Loading and Hits

It provides actual matched tokens, load completion, block errors, storage events, and asynchronous save completion.

A KDN `READY` response does not mean the target Instance has completed loading. A stale Proxy local view also does not mean the global Artifact should be deleted.

## 12. Testing and Experiment Requirements

### 12.1 Unit Tests

- Artifact / Replica / Task state machines;
- control/data-plane protocols and idempotency keys;
- ExecutionGraph dependency, cancellation, and fallback;
- Single-flight;
- queue priority, Aging, fairness, and backpressure;
- CachePlan / FusionPlan determinism;
- Trace fields and compatibility parsing.

### 12.2 Component Tests

- independent startup of the KDN catalog and Data Workers;
- Runtime Adapter Mock;
- recovery after independent control-plane or data-plane restart;
- Proxy KVCache Manager;
- QueueCoordinator multi-resource parallelism;
- Maintenance Dry-run and execution;
- LMCache event integration.

### 12.3 End-to-End Tests

- complete vLLM + LMCache + CacheRoute startup;
- text, prefix KV, Hybrid, partial KV, and multi-block fusion;
- network transfer and pure computation in parallel;
- automatic eviction, replication, migration, and prefetch;
- fault fallback and restart recovery.

### 12.4 Experiment Reproduction

Every experiment should preserve:

- configuration files and code version;
- model, LMCache, and vLLM versions;
- workload Trace;
- initial KDN state and Data Worker topology;
- queue and maintenance-policy parameters;
- request-level ExecutionGraph and results;
- aggregate metrics and exception records.

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
- develop a Mock Data Worker during v0.1.12;
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

These capabilities should be built on the trustworthy control plane, replaceable data plane, and parallel knowledge/compute queues delivered by v0.2.0.
