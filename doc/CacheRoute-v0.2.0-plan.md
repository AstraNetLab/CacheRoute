# CacheRoute v0.2.0 Evolution Plan

> Status: Planning draft  
> Current release baseline: v0.1.9  
> Implementation approach: restart from the v0.1.10 Issue sequence without inheriting closed-PR implementations  
> Target release: v0.2.0  
> Core foundation: vLLM + LMCache  
> Core positioning: an independent knowledge-aware KDN remote-cache server, an LMCache evolution-compatibility layer, Proxy multi-resource execution orchestration, knowledge-aware cache policy, and multi-block reuse

> **v1/Legacy and LMCache-native amendment:** after the runtime migration, v1 KDN is interpreted as `Knowledge Control Plane + CacheRoute Cache Service Facade + LMCache Orchestration Gateway`. vLLM and LMCache MP retain the direct data path; new features target v1 only, while Legacy remains runnable but feature-frozen. The authoritative amendment is `doc/CacheRoute-v0.2.0-v1-lmcache-alignment.md`.

## 0. Planning Decisions

This roadmap establishes the following long-term boundary:

> **KDN Server = Knowledge Control Plane + LMCache-Compatible Remote Cache Serving Plane.**

KDN is an independently deployable and scalable server entity managed as a resource by CacheRoute. It is neither an alias for Redis nor a second general-purpose KVCache store implemented by CacheRoute.

KDN has two responsibilities:

1. provide CacheRoute with knowledge semantics, Artifact management, policy, maintenance, and observations;
2. provide LMCache with remote KVCache lookup, store, load, and asynchronous serving operations.

Physical KVCache chunking, serialization, transfer, storage backends, and low-level eviction should reuse or align with LMCache public capabilities whenever possible. KDN differentiates CacheRoute at the knowledge and policy layers rather than by reimplementing Redis, Mooncake, S3, NIXL, or filesystem cache engines.

### 0.1 Current Issue Treatment

| Item | Roadmap treatment |
|---|---|
| #138 / PR #143 | complete; retain Instance Capability Fingerprints |
| #139 | restart from the Issue; define storage-neutral core states and logical objects |
| #140 | revise toward dual KDN interfaces and LMCache Compatibility Profiles |
| #141 | include KDN Serving, LMCache Profile, and Provider observation sources |
| #142 | add cross-profile and cross-version contract/regression validation |
| Closed PRs | not treated as an implementation migration base in this roadmap |

### 0.2 Non-Negotiable Principles

- KDN must be an independent server without making any one storage implementation part of KDN's identity.
- Redis may be an early validation provider or Legacy compatibility path only.
- KDN exposes stable remote-cache semantics to LMCache, not Redis keys, directories, or private serialization.
- KDN's internal Provider layer aligns with public LMCache extension contracts.
- CacheRoute does not duplicate LMCache's chunk index, allocator, serde, or block-transfer implementation.
- LMCache version changes must not propagate into KDN Knowledge APIs, Proxy CachePlan, or Scheduler logic.
- Version and capability differences are represented through Compatibility Profiles and capability negotiation.
- Missing or incompatible capabilities produce explicit `unsupported`, `incompatible`, or fallback outcomes; they are never silently emulated.

## 1. Formal Positioning of KDN Server

### 1.1 Definition

KDN Server is a knowledge-aware remote cache service. It receives Lookup, Store, Load/Retrieve, and related calls from Instance-side LMCache while providing CacheRoute with a knowledge catalog and policy control.

KDN is more than a data backend. An ordinary remote backend knows keys and values; KDN additionally understands:

- the KnowledgeObject represented by the cache;
- knowledge content and version;
- model, tokenizer, adapter, and KV-layout compatibility;
- CacheArtifact construction and invalidation;
- multi-knowledge-block co-occurrence;
- cache value, Pin, prefetch, and retention intent;
- network cost, compute savings, and queue impact;
- quality protection and text fallback.

### 1.2 Three-Layer Structure

```text
KDN Server
|
+-- Knowledge Control Plane
|   - KnowledgeObject / version
|   - CacheArtifact identity
|   - compatibility and policy
|   - desired state
|   - maintenance decisions
|   - access and value statistics
|
+-- Remote Cache Serving Plane
|   - LMCache-facing Lookup
|   - Store / Publish
|   - Load / Retrieve
|   - Prefetch
|   - Pin / Unpin
|   - Remove / Clear
|   - asynchronous task status
|   - health and metrics
|
+-- Provider Compatibility Layer
    - LMCache MP L2 Adapter profile
    - LMCache native_plugin profile
    - Remote Storage Plugin profile
    - Legacy in-process/Controller profile
    - Mock provider
    - backend-specific provider packages
```

The layers answer different questions:

- **Knowledge Control Plane**: why the cache exists, which knowledge it represents, and which policy should apply;
- **Remote Cache Serving Plane**: which remote-cache services LMCache can invoke;
- **Provider Compatibility Layer**: how the current LMCache version and provider execute those operations.

### 1.3 Two External Interfaces

#### CacheRoute-Facing Knowledge Management API

Used by Scheduler, Proxy, management tools, and KDN policy modules:

```text
RegisterKnowledge
UpdateKnowledgeVersion
ResolveKnowledge
ListCompatibleArtifacts
GetArtifactObservation
GetServingCandidates
CreatePlacementIntent
CreatePrefetchIntent
PinKnowledge
ClearKnowledge
GetPolicyDecision
GetMaintenanceStatus
ReportRequestOutcome
```

This interface exchanges knowledge, policy, logical references, observation summaries, and task state. It does not transfer large KVCache payloads.

#### LMCache-Facing Remote Cache Serving API

Used by Instance-side LMCache or its plugins:

```text
Handshake / Capabilities
Lookup / BatchedLookup
Store / Publish
Load / Retrieve
Prefetch
Pin / Unpin
Remove / Clear
Unlock
TaskStatus / Completion
Health / Metrics
```

The interface must:

- remain independent of a concrete backend;
- support synchronous and asynchronous completion models;
- support batching;
- make lock, lease, cancellation, and idempotency semantics explicit;
- return hit coverage, source, timing, and structured errors;
- not require LMCache to understand KnowledgeObject or upper-layer policy.

### 1.4 KDN Is Not Redis

The first runnable KDN may use Redis, but the following must not enter the stable protocol:

- Redis URL;
- Redis password;
- internal Redis key;
- Redis pipeline details;
- Redis as Replica identity;
- Redis-specific TTL or transaction semantics.

A uniform Provider description should represent:

```text
provider_type
provider_profile
provider_version
capabilities
namespace
location_ref
health
capacity_summary
queue_summary
```

The provider can later be replaced by Mooncake, NIXL, S3, filesystem, object storage, a native connector, or another LMCache-supported/extended backend without changing the KDN Knowledge API.

## 2. Relationship Between KDN and LMCache

### 2.1 Data-Path Relationship

```text
vLLM Instance
    |
    v
Instance-side LMCache
    |
    | KDN Connector / L2 Adapter
    v
Independent KDN Server
    |
    +-- knowledge-aware serving decisions
    +-- namespace / artifact mapping
    +-- request and maintenance accounting
    |
    v
KDN Provider Compatibility Layer
    |
    +-- LMCache-aligned adapter/provider
    +-- supported storage or transport backend
```

Instance-side LMCache treats KDN as a retrievable remote cache service. KDN maps upper-layer knowledge identity into a physical cache reference that a Provider can execute.

KDN does not require every LMCache request to run complex policy logic. The data hot path is separated from the knowledge-policy path:

- ordinary Lookup/Load uses a fast Serving Path;
- policy changes, maintenance, rebuild, and placement use an asynchronous Control Path;
- the Serving Path may consume versioned snapshots and policy results published by the control plane.

### 2.2 Authority Boundary

| Information | Authority |
|---|---|
| KnowledgeObject content, version, and semantics | KDN |
| KnowledgeObject-to-CacheArtifact relationship | KDN |
| Artifact compatibility and invalidation reason | KDN |
| desired Pin, prefetch, retention, and placement intent | KDN Policy |
| LMCache client capability and interface Profile | LMCache Compatibility Layer |
| physical KV data, layout, serde, and chunk index | LMCache/Provider |
| physical object existence and operation completion | Provider runtime observation |
| actual local hit tokens at the Instance | Instance-side LMCache |
| request waiting, bypass, and compute release | Proxy |
| global Proxy/KDN resource-pool selection | Scheduler |

KDN may cache physical observations, but they carry:

```text
observation_source
observed_at
expires_at
provider_generation
lmcache_profile_id
confidence
```

### 2.3 Provider Alignment Rules

KDN Providers must not invent a KV-data abstraction unrelated to LMCache. The priority is:

1. use an LMCache MP L2 Adapter or public equivalent;
2. use `native_plugin` or a public native-connector contract for high-performance native backends;
3. use the current recommended Remote Storage Plugin for external distributed storage;
4. retain in-process Remote Connector, Controller, or old-configuration adapters only for compatibility;
5. when LMCache lacks a required capability, prefer contributing through its extension mechanism;
6. discuss a CacheRoute-specific data mechanism only after showing that LMCache extensions cannot reasonably provide it.

## 3. Compatibility With LMCache Evolution

LMCache is evolving from in-process mode toward standalone MP Server, multi-level L1/L2, asynchronous Store/Lookup/Load, and plugin-based adapters. CacheRoute must not make one point-in-time Python class, module path, or HTTP endpoint part of its long-term architecture.

### 3.1 Compatibility-Layer Goal

```text
Stable CacheRoute/KDN Contracts
             |
             v
LMCache Compatibility Layer
             |
   +---------+-----------+----------------+
   |                     |                |
MP L2 Profile      Native Profile   Legacy Profile
   |                     |                |
Current LMCache     high-performance   old deployment
```

The layer isolates:

- LMCache version;
- runtime mode;
- request/response types;
- Adapter class paths;
- ZMQ/HTTP/in-process call differences;
- asynchronous completion mechanisms;
- lock and unlock semantics;
- key/hash and layout differences;
- event and observation formats;
- deprecated configurations and interfaces.

### 3.2 LMCacheCompatibilityProfile

```text
profile_id
lmcache_version_range
integration_family
integration_mode
protocol_version
key_format_version
layout_profile
serde_profile
supported_operations
batching_capabilities
locking_model
completion_model
event_model
cancellation_model
configuration_schema_version
status
validated_at
```

Recommended `integration_family` values:

```text
mp_l2_plugin
mp_native_plugin
remote_storage_plugin
controller_api
in_process_legacy
mock
```

Profile status:

```text
experimental
validated
default
deprecated
unsupported
```

### 3.3 Handshake and Capability Negotiation

When KDN and an LMCache Connector connect, they exchange:

- KDN Serving Protocol Version;
- LMCache Compatibility Profile;
- supported operations;
- maximum batch size;
- Key/Layout/Serde Profiles;
- synchronous or asynchronous completion model;
- Lock/Unlock/Lease semantics;
- Event/Metric support;
- Provider Generation;
- recommended fallback.

An uncertain capability is never assumed to be supported.

### 3.4 Prefer Public Interfaces

- Reference LMCache public interfaces only inside stable adapters.
- Do not import LMCache private classes into KDN domain models, Proxy queues, or Scheduler.
- Private or experimental interfaces belong in independent adapters with explicit version gates.
- An LMCache interface rename replaces an adapter rather than KnowledgeObject, CachePlan, or ExecutionGraph.
- Do not make deprecated `remote_url`, old in-process mode, or one module path a stable KDN configuration field.

### 3.5 Data Compatibility and Upgrade

Artifact identity includes or references:

```text
model_fingerprint
tokenizer_fingerprint
adapter_fingerprint
kv_layout_profile
kv_dtype
parallelism_profile
lmcache_data_profile
key_format_version
serde_profile
```

When LMCache is upgraded:

1. compare Compatibility Profiles;
2. reuse data when it is directly readable;
3. create a migration task when migration is required and supported;
4. rebuild an incompatible Artifact;
5. forbid silent reuse and fall back to text when compatibility is unknown;
6. retain old-Profile observation and a rollback window.

### 3.6 Support Policy

Each CacheRoute release declares:

- minimum supported LMCache version or capability Profile;
- default validated version;
- latest experimentally validated version;
- deprecated Profiles;
- known-incompatible combinations;
- Compatibility Matrix;
- upgrade and rollback guidance.

Tests cover at least:

```text
baseline validated LMCache profile
latest validated LMCache profile
one deprecated/legacy profile
mock future profile with unknown capabilities
```

## 4. Overall Role Boundaries

```text
Scheduler
- Select Proxy / KDN resource pools
- Consume coarse knowledge and resource summaries
- Do not handle physical cache keys, blocks, or transfer tasks

Proxy
- Resolve Knowledge
- Build CachePlan / FusionPlan / ExecutionGraph
- Maintain a short-lived Instance Cache Observation
- Coordinate KDN Serving, network, Cache Load, Prefill, and Decode
- Do not build an authoritative Block Index

KDN Knowledge Control Plane
- Authority for knowledge, Artifacts, policy, and desired state
- Maintain KDN Endpoints, Providers, and LMCache Profiles
- Generate maintenance and serving intents

KDN Remote Cache Serving Plane
- Receive LMCache remote-cache requests
- Execute fast Lookup/Store/Load
- Return structured hits and task results
- Do not run complex global policy on the hot path

KDN Provider Compatibility Layer
- Adapt current LMCache extension contracts and concrete Providers
- Isolate version, configuration, and completion-model differences

LMCache
- Instance-side cache client, L1/L2 management, and vLLM Connector
- Define public extension interfaces and data-layout capabilities
- Provide actual hit and load observations

vLLM
- Own model execution, Paged KV, and engine-internal scheduling
```

## 5. v0.2.0 Target Architecture

```text
                               Scheduler
                                   |
                    global knowledge/resource routing
                                   |
                                 Proxy
        +--------------------------+--------------------------+
        |                          |                          |
 Knowledge Resolver          KVCache Manager          Queue Coordinator
        |                    observed Instance View     ExecutionGraph
        |                          |                          |
        +--------------------------+--------------------------+
                                   |
                    KDN Knowledge Management API
                                   |
                        Independent KDN Server
        +--------------------------+--------------------------+
        |                                                     |
 Knowledge Control Plane                         Remote Cache Serving Plane
 - Knowledge Catalog                             - Handshake / Capability
 - Artifact Catalog                              - Lookup / BatchedLookup
 - Policy Engine                                 - Store / Publish
 - Desired State                                 - Load / Retrieve
 - Maintenance Planner                           - Prefetch / Pin / Clear
 - Statistics                                    - Task status / metrics
        |                                                     |
        +-----------------------+-----------------------------+
                                |
                   Provider Compatibility Layer
         +----------------------+------------------------------+
         |                      |                              |
   MP L2 Adapter          Native Plugin                Legacy Adapter
         |                      |                              |
       Provider A             Provider B                  Redis/file path
```

Key data flow:

```text
Instance LMCache
    -> KDN Lookup
    -> KDN Provider Lookup
    -> KDN returns coverage / task reference
    -> LMCache Load/Retrieve
    -> Instance confirms actual hit
    -> Proxy releases dependent compute
```

## 6. Core Objects

### 6.1 KnowledgeObject

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

### 6.2 CacheArtifact

```text
artifact_id
knowledge_id
capability_fingerprint
artifact_variant
kv_layout_profile
lmcache_data_profile
key_format_version
desired_state
policy_state
created_at
updated_at
```

An Artifact is the logical materialization identity under a knowledge and compatibility environment. It does not store KV bytes.

### 6.3 CacheReplicaObservation

```text
replica_id
artifact_id
kdn_endpoint_id
provider_id
provider_profile
location_ref
observed_state
health
observation_source
observed_at
expires_at
provider_generation
lmcache_profile_id
confidence
```

A Replica is a short-lived observation/reference, not a physical replica implemented by CacheRoute.

### 6.4 KDNServingEndpoint

```text
endpoint_id
serving_protocol_version
supported_lmcache_profiles
supported_operations
provider_profiles
max_batch_size
locking_model
completion_model
health
capacity_summary
queue_summary
generation
last_heartbeat_at
```

### 6.5 LMCacheCompatibilityProfile

Use the definition in Section 3.2.

### 6.6 KDNServingTask

```text
task_id
idempotency_key
operation
artifact_id
endpoint_id
provider_id
provider_task_id
state
priority
lease
requested_at
started_at
finished_at
observed_bytes
observed_tokens
result_source
result
error
```

### 6.7 CachePlan / FusionPlan

```text
request_id
target_instance_id
knowledge_blocks
matched_artifacts
kdn_candidates
cache_observations
lookup_tasks
load_tasks
fusion_mode
recompute_ranges
fallback_mode
plan_state
trace_context
```

### 6.8 ExecutionGraph

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
KDN_SERVE
NET_KV
CACHE_LOAD
PREFILL
DECODE
FUSION
```

## 7. Iteration Overview

| Version | Theme | Main delivery |
|---|---|---|
| v0.1.10 | Contract and observation baseline | Capability, core states, dual KDN vocabulary, LMCache Profile, Trace |
| v0.1.11 | KDN Knowledge Control Plane | KnowledgeObject, Artifact Catalog, Desired/Observed State |
| v0.1.12 | Independent KDN Serving Plane MVP | LMCache-facing server, Provider SPI, Redis/Mock validation |
| v0.1.13 | Multi-Provider and LMCache evolution compatibility | MP/Profile adapters, compatibility matrix, second provider, recovery |
| v0.1.14 | Proxy KVCache Manager | LMCache/KDN-observed Instance view and single-flight |
| v0.1.15 | Injection and compute queue model | ExecutionGraph, resource queues, Compute Fast Path |
| v0.1.16 | Parallel network and compute | Work-conserving pipeline and overlap benchmark |
| v0.1.17 | Queue stability and generality | Admission, backpressure, fairness, aging, adaptive concurrency |
| v0.1.18 | KDN knowledge-aware policy | Pin/Prefetch/Placement/Clear intents, value model, replay |
| v0.1.19 | Multi-block non-prefix fusion | Parallel lookup, selective recomputation, quality fallback |
| v0.2.0 | Integrated research baseline | Stable interfaces, cross-version compatibility, complete experiment loop |

## 8. Per-Version Plan

## v0.1.10: Contract and Observation Baseline

### Goal

Freeze the stable vocabulary required by later work without implementing the complete KDN Server:

- Instance Capability;
- CacheArtifact and CacheReplicaObservation;
- KDNServingEndpoint;
- KDNServingTask;
- LMCacheCompatibilityProfile;
- QueueWork;
- Trace sources and stages;
- Legacy compatibility mapping.

### Acceptance

- completed #138 Capability remains compatible;
- core objects contain no KV bytes, raw Redis keys, credentials, or LMCache private classes;
- KDN Knowledge API and LMCache-facing Serving API are distinct;
- LMCache Profiles represent MP, Plugin, Legacy, and unknown capabilities;
- Trace distinguishes KDN, Provider, LMCache, Proxy, and vLLM sources;
- CPU-only tests require no external vLLM, Redis, or LMCache cluster.

## v0.1.11: KDN Knowledge Control Plane

### Main Steps

1. Implement KnowledgeObject and version management.
2. Allow one KnowledgeObject to map to multiple CacheArtifacts.
3. Evaluate Artifact compatibility through Capability and LMCache Data Profiles.
4. Separate Desired State from Provider Observation.
5. Build KDN Endpoint and Provider registries.
6. Map knowledge into a KDN Serving Namespace/Location Reference.
7. Let Scheduler consume only coarse knowledge availability.
8. Map Legacy `kv_ready` into `compatibility=unknown`.

### Acceptance

- one knowledge item supports multiple models, adapters, and LMCache Profiles;
- the control plane does not access or copy physical KV data;
- expired Provider observations are no longer authoritative;
- Redis does not appear in stable Knowledge domain models.

## v0.1.12: Independent KDN Remote Cache Serving Plane MVP

### Main Steps

1. Start an independent KDN Server.
2. Implement Serving Handshake and Capability Negotiation.
3. Implement a minimum set of Lookup, Store, Load/Retrieve, and TaskStatus.
4. Define a Provider SPI aligned with public LMCache L2/Remote Storage semantics.
5. Implement a Mock Provider.
6. Implement the first real Provider; Redis may be used only as a Provider.
7. Implement an Instance-side LMCache KDN Connector/Adapter.
8. Keep complex policy queries out of the data hot path.
9. Record actual bytes, hit coverage, queueing, and operation time.

### Acceptance

- LMCache can treat KDN as a remote cache service;
- KDN Server is decoupled from a concrete Provider;
- replacing Mock/Redis does not change the Serving Protocol;
- Redis keys and credentials do not enter CacheRoute APIs;
- failure falls back to text computation.

## v0.1.13: Multi-Provider and LMCache Evolution Compatibility

### Main Steps

1. Prefer an LMCache MP L2 Plugin Profile.
2. Support at least one compatibility Profile such as Remote Storage Plugin or Legacy.
3. Add a second real Provider to prove Redis independence.
4. Build a Compatibility Matrix and Profile Conformance Suite.
5. Allow different LMCache Profiles to register concurrently.
6. Implement Profile upgrade, downgrade, and deprecation status.
7. Implement Provider generation, reconnect, and task recovery.
8. Migrate or rebuild incompatible Key/Layout/Serde data.
9. Add a periodic process for validating the latest LMCache Profile.

### Acceptance

- KDN runs with at least two Provider configurations;
- MP Profile is the default evolution direction;
- old Profiles are explicitly compatible or rejected;
- LMCache interface changes require only Compatibility Adapter updates;
- incompatible upgrades do not silently reuse old Artifacts.

## v0.1.14: Proxy KVCache Manager

### Main Steps

1. Build an Instance Cache Observation View.
2. Sources include KDN Lookup, LMCache events, Load results, and actual hits.
3. Every observation carries time, source, Profile, Generation, and TTL.
4. States include UNKNOWN, REMOTE_AVAILABLE, PREPARING, LOCAL_AVAILABLE, STALE, and FAILED.
5. Implement single-flight per Artifact/Instance.
6. Invalidate observations when Instance, KDN, or Provider generation changes.
7. Proxy does not copy a Provider Chunk Index.

### Acceptance

- Proxy distinguishes KDN availability, Provider hit, loading, and Instance-local availability;
- expired observations become UNKNOWN;
- one preparation task serves concurrent waiters;
- LMCache Profile changes invalidate related observations.

## v0.1.15: Knowledge Injection and Compute Queue Model

- Compile CachePlan into ExecutionGraph.
- Include Control, KDN Lookup, KDN Serve, Network KV, Cache Load, Prefill, Decode, and Fusion nodes.
- Define dependency, Share Key, priority, deadline, cost, and fallback.
- Text tasks use a Compute Fast Path.
- Scheduler does not execute fine-grained nodes.

## v0.1.16: Parallel Network KV and Pure Compute

- Create independent concurrency domains for Control, KDN, Network, Cache Load, and Compute.
- Overlap network KV transfer with other-request Prefill/Decode.
- Remain work-conserving when requests wait for KV.
- Add network-compute Gantt and Overlap Ratio.
- Support cancellation, timeout, and fallback.

## v0.1.17: Queue Generality and Stability

- Admission control and backpressure.
- Fairness, aging, and starvation guards.
- Adaptive concurrency.
- Single-flight lifecycle.
- Test across models, Instances, KDNs, bandwidths, and injection mixes.
- Policy plugins control priority, quota, bypass, and concurrency but cannot break state-machine correctness.

## v0.1.18: KDN Knowledge-Aware Cache Policy

### Inputs

- knowledge access frequency and co-occurrence;
- LMCache Lookup/Event;
- Provider capacity, hits, health, and queueing;
- Proxy waiting and GPU idle;
- network cost and compute savings;
- build, refresh, and migration cost;
- Artifact compatibility and version;
- online and background load.

### Outputs

```text
BUILD
PUBLISH
PREFETCH
PIN
UNPIN
MOVE
CLEAR
REFRESH
REPLICATE_INTENT
```

### Requirements

- Every decision has a Reason Code.
- Prevent pollution and oscillation.
- Prioritize online SLOs.
- Support shadow, replay, and controlled enablement.
- Do not operate on Provider-private keys.
- Use physical operations exposed by LMCache.

## v0.1.19: Multi-Knowledge-Block Non-Prefix Fusion

- Resolve multiple knowledge blocks per request.
- Parallelize Artifact Resolve and Lookup.
- Plan Full/Partial/Overlap/Reorder uniformly.
- Use LMCache non-prefix reuse, CacheBlend, or an equivalent capability.
- Selectively recompute required tokens.
- Add multi-block preparation to ExecutionGraph.
- Fall back to text when unsupported, quality validation fails, or timeout occurs.
- Compare serial loading, parallel loading, pure text, and single-prefix reuse.

## v0.2.0: Integration, Stability, and Research Baseline

v0.2.0 is complete when:

- KDN is independently deployable and scalable;
- KDN is not bound to Redis or one LMCache mode;
- at least two Providers are validated;
- at least baseline and latest LMCache Profiles are validated;
- MP is the default Profile and Legacy has an explicit deprecation policy;
- the Knowledge Control Plane and Serving Hot Path scale independently;
- Proxy uses short-lived observations rather than an authoritative Block Index;
- network KV and pure compute overlap;
- queues support single-flight, backpressure, fairness, cancellation, and fallback;
- at least two knowledge blocks support non-prefix reuse;
- KDN includes at least one knowledge-value policy;
- critical failure and upgrade scenarios have reproducible tests;
- text, single-knowledge, and Legacy paths remain compatible.

## 9. LMCache Evolution Compatibility Test Framework

### 9.1 Contract Tests

Run the same KDN Serving Contract Tests against:

- Mock Profile;
- MP L2 Plugin Profile;
- Native Plugin Profile;
- Remote Storage Plugin Profile;
- Legacy Profile.

### 9.2 Compatibility Matrix

Record:

```text
CacheRoute version
KDN serving protocol
LMCache profile
LMCache version range
vLLM version range
provider profile
validated operations
known limitations
status
```

### 9.3 Upgrade Scenarios

- LMCache minor-version upgrade;
- Adapter API rename;
- Completion Model change;
- Key Format change;
- incompatible Layout/Serde;
- Provider restart;
- KDN rolling upgrade;
- old and new LMCache clients connecting concurrently;
- Profile deprecation;
- downgrade rollback.

### 9.4 Failure Principles

- Unknown capability is not supported by default.
- Incompatible Artifacts are not loaded.
- Provider operation failure does not corrupt the knowledge catalog.
- KDN control-plane failure does not interrupt authorized data tasks.
- Proxy can fall back to text when the Serving Plane fails.
- Upgrade failure can return to the previous validated Profile.

## 10. Queue Research Metrics

- TTFT P50/P95/P99;
- throughput and completion time;
- KDN Lookup Wait;
- KDN Serving Queue/Execution;
- Provider Lookup/Load;
- Network-Compute Overlap Ratio;
- GPU Idle Due to Cache Wait;
- Network Idle With Pending Work;
- Head-of-Line Blocking Time;
- single-flight saved tasks and bytes;
- Profile negotiation failure rate;
- incompatible rebuild and fallback rate;
- multi-Provider load distribution;
- result consistency across LMCache upgrades.

## 11. State Boundaries

### KDN Knowledge Control Plane

Authoritative for knowledge, Artifacts, policy, Desired State, Profile support, and historical value.

### KDN Serving Plane

Authoritative for KDN requests, tasks, and current serving results, but historical task results do not become permanent Provider physical facts.

### Provider / LMCache Runtime

Authoritative for physical object existence, bytes, layouts, storage location, and low-level operation results.

### Proxy

Maintains request-level plans, short-lived Instance/KDN observations, shared preparation tasks, and queues.

### Instance / vLLM

Authoritative for actual hit tokens, model execution, Prefill, and Decode outcomes.

## 12. Testing and Experiment Requirements

### Unit Tests

- object IDs and state transitions;
- LMCacheCompatibilityProfile;
- capability negotiation;
- protocol version;
- secret/private-key rejection;
- observation TTL;
- CachePlan/FusionPlan;
- ExecutionGraph;
- single-flight;
- trace provenance.

### Component Tests

- separate KDN Control and Serving startup;
- Mock Provider;
- two Provider implementations;
- two LMCache Profiles;
- KDN Connector;
- Provider restart;
- Profile upgrade/downgrade;
- multi-resource queue parallelism.

### End-to-End Tests

- vLLM + LMCache + Proxy + KDN;
- text, single-knowledge KV, and Hybrid;
- KDN remote Lookup/Load;
- network-compute parallelism;
- multi-Provider;
- multi-knowledge-block;
- KDN/Provider/LMCache failure;
- Profile incompatibility and text fallback.

### Experiment Reproduction

Store:

- CacheRoute, vLLM, LMCache, and Provider versions;
- the relevant Compatibility Matrix row;
- KDN protocol/Profile;
- workload;
- KDN and Provider topology;
- queue and policy parameters;
- ExecutionGraph;
- request-level results;
- aggregate metrics and anomalies.

## 13. Version Dependencies

```text
v0.1.10 contracts
       |
v0.1.11 knowledge control
       |
v0.1.12 independent serving MVP
       |
v0.1.13 multi-provider + LMCache compatibility
       |
v0.1.14 observed Proxy manager
       |
v0.1.15 execution graph
       |
v0.1.16 overlap pipeline
       |
v0.1.17 queue stability
       +----------------------+
       |                      |
v0.1.18 policy          v0.1.19 planning/tools
       |                      |
       +----------+-----------+
                  |
               v0.1.19
                  |
               v0.2.0
```

## 14. Long-Term KDN Evolution

After v0.2.0, KDN should evolve:

1. from a monolithic KDN into a Control Plane plus multiple Serving Nodes;
2. from one Provider into a heterogeneous Provider federation;
3. from static Profiles into automatic capability negotiation;
4. from one region into multi-region KDN;
5. from coarse Artifacts into multi-block, partial, and composed knowledge cache;
6. from rule policies into SLO- and uncertainty-aware policies;
7. in continuous alignment with new LMCache MP, Native, Transport, and Observability capabilities;
8. while preserving isolation among Knowledge API, KDN Serving Protocol, and Provider SPI.

Regardless of how LMCache evolves, CacheRoute's long-term core remains:

> **connect knowledge semantics, remote cache serving, injection decisions, and compute-queue orchestration into an observable, extensible, and reproducible experimental loop.**
