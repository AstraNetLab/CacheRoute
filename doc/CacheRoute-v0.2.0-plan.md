# CacheRoute v0.2.0 Evolution Plan

> Status: Planning draft  
> Current release baseline: v0.1.9  
> Implementation approach: restart from the v0.1.10 Issue sequence without inheriting closed-PR implementations  
> Target release: v0.2.0  
> Core foundation: vLLM + LMCache  
> Core positioning: an independent knowledge-aware KDN remote-cache server, an LMCache evolution-compatibility layer, Proxy multi-resource execution orchestration, knowledge-aware cache policy, and multi-block reuse

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

This API exchanges knowledge, policy, logical references, observation summaries, and task states. It does not transfer large KV payloads.

#### LMCache-Facing Remote Cache Serving API

Used by Instance-side LMCache or an LMCache plugin:

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

The API must:

- remain backend-neutral;
- support synchronous and asynchronous completion models;
- support batching;
- define lock, lease, cancellation, and idempotency semantics;
- return coverage, source, timing, and structured errors;
- not require LMCache to understand KnowledgeObject or CacheRoute policy.

### 1.4 KDN Is Not Redis

The first runnable KDN may use Redis, but the following must not enter stable contracts:

- Redis URLs;
- Redis passwords;
- Redis internal keys;
- Redis pipeline details;
- Redis as the Replica identity;
- Redis-specific TTL or transaction semantics.

Providers are represented through a neutral description:

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

Mooncake, NIXL, S3, filesystems, object stores, native connectors, or other LMCache-supported/extensible providers can later replace Redis without changing the KDN Knowledge API.

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
    +-- namespace / Artifact mapping
    +-- request and maintenance accounting
    |
    v
KDN Provider Compatibility Layer
    |
    +-- LMCache-aligned adapter/provider
    +-- supported storage or transport backend
```

Instance-side LMCache treats KDN as a queryable remote-cache service. KDN maps higher-level knowledge identities to physical cache references understood by the active Provider.

The data hot path must be separated from the knowledge-policy path:

- normal Lookup/Load uses a fast Serving Path;
- policy changes, maintenance, rebuild, and placement use an asynchronous Control Path;
- the Serving Path can consume versioned snapshots and policy decisions produced by the control plane.

### 2.2 Authority Boundaries

| Information | Authority |
|---|---|
| KnowledgeObject content, version, and semantics | KDN |
| KnowledgeObject-to-CacheArtifact mapping | KDN |
| Artifact compatibility and invalidation reason | KDN |
| desired Pin, prefetch, retention, and placement intent | KDN policy |
| LMCache client capabilities and interface profile | LMCache Compatibility Layer |
| physical KV data, layout, serde, and chunk index | LMCache/Provider |
| physical object existence and operation completion | Provider runtime observation |
| actual local hit tokens | Instance-side LMCache |
| request wait, bypass, and compute release | Proxy |
| global Proxy/KDN resource-pool choice | Scheduler |

KDN may cache physical observations, but every observation records:

```text
observation_source
observed_at
expires_at
provider_generation
lmcache_profile_id
confidence
```

### 2.3 Provider Alignment Priority

KDN Providers should not invent a KV-data abstraction unrelated to LMCache. The priority is:

1. use an LMCache MP L2 Adapter or public equivalent;
2. use `native_plugin` or a public native connector for high-performance native providers;
3. use the recommended Remote Storage Plugin for external distributed storage;
4. retain in-process Remote Connector, Controller, or old-configuration adapters only for compatibility;
5. contribute required provider capabilities through LMCache extension points first;
6. discuss CacheRoute-specific data mechanisms only after a demonstrated gap cannot reasonably be addressed through LMCache.

## 3. Compatibility With LMCache Evolution

LMCache is evolving from in-process operation toward an independent MP server, multi-tier L1/L2 storage, asynchronous Store/Lookup/Load, and plugin-based adapters. CacheRoute must not treat a Python class, module path, or HTTP endpoint from one release as a permanent architecture boundary.

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
Current LMCache     high performance   old deployments
```

The compatibility layer isolates:

- LMCache version;
- runtime mode;
- request/response types;
- adapter class paths;
- ZMQ, HTTP, and in-process differences;
- asynchronous completion;
- lock and Unlock semantics;
- key/hash and layout formats;
- event and observation formats;
- deprecated configuration and APIs.

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

A KDN-to-LMCache connection exchanges:

- KDN Serving Protocol version;
- LMCache Compatibility Profile;
- supported operations;
- maximum batch size;
- key/layout/serde profiles;
- synchronous or asynchronous completion model;
- lock/unlock/lease semantics;
- event and metrics support;
- Provider generation;
- recommended fallback behavior.

Unknown capability is never interpreted as supported.

### 3.4 Prefer Public Interfaces

- LMCache public interfaces are referenced only inside the compatibility layer.
- KDN domain models, Proxy queues, and Scheduler do not import LMCache private classes.
- Private or experimental interfaces live in isolated, version-gated adapters.
- LMCache interface changes replace an adapter rather than KnowledgeObject, CachePlan, or ExecutionGraph.
- Deprecated `remote_url`, old in-process mode, or one module path is not stored as a stable KDN field.

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

During an LMCache upgrade:

1. compare Compatibility Profiles;
2. reuse data when directly readable;
3. create a migration task when migration is supported;
4. rebuild the Artifact when incompatible;
5. forbid silent reuse and fall back to text when unknown;
6. keep observations and a rollback window for the previous Profile.

### 3.6 Support Policy

Each CacheRoute release declares:

- minimum supported LMCache version or capability Profile;
- default validated version;
- latest experimentally validated version;
- deprecated Profiles;
- known incompatible combinations;
- a Compatibility Matrix;
- upgrade and rollback guidance.

Testing covers at least:

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
- Do not process physical cache keys, chunks, or transfer tasks

Proxy
- Resolve knowledge
- Build CachePlan / FusionPlan / ExecutionGraph
- Maintain short-lived Instance Cache Observations
- Coordinate KDN Serving, network, Cache Load, Prefill, and Decode
- Do not build an authoritative block index

KDN Knowledge Control Plane
- Authoritative for knowledge, Artifacts, policy, and desired state
- Maintain KDN Endpoint, Provider, and LMCache Profile registries
- Generate maintenance and serving intent

KDN Remote Cache Serving Plane
- Receive LMCache remote-cache requests
- Execute fast Lookup/Store/Load operations
- Return structured hit and task results
- Do not run complex global policy in the hot path

KDN Provider Compatibility Layer
- Adapt current LMCache extension contracts and concrete Providers
- Isolate version, configuration, and completion-model differences

LMCache
- Instance-side cache client, L1/L2 management, and vLLM Connector
- Define public extension interfaces and data-layout capabilities
- Provide actual hit and load observations

vLLM
- Model execution, Paged KV, and internal scheduling
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

Primary data flow:

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

An Artifact is a logical materialization identity for knowledge and a compatible runtime. It does not store KV bytes.

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

A Replica is a short-lived observation/reference, not a CacheRoute-owned physical-replica implementation.

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

Use the model in Section 3.2.

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

| Version | Theme | Primary delivery |
|---|---|---|
| v0.1.10 | Contract and observability baseline | Capability, core states, dual KDN vocabulary, LMCache Profiles, Trace |
| v0.1.11 | KDN Knowledge Control Plane | KnowledgeObject, Artifact Catalog, desired/observed state |
| v0.1.12 | Independent KDN Serving Plane MVP | LMCache-facing server, Provider SPI, Redis/Mock validation |
| v0.1.13 | Multi-Provider and LMCache evolution compatibility | MP/Profile adapters, compatibility matrix, second provider, recovery |
| v0.1.14 | Proxy KVCache Manager | LMCache/KDN-observed Instance View and Single-flight |
| v0.1.15 | Injection and compute queue model | ExecutionGraph, resource queues, Compute Fast Path |
| v0.1.16 | Network-compute parallelism | work-conserving pipeline and overlap benchmark |
| v0.1.17 | Queue stability and generality | admission, backpressure, fairness, aging, adaptive concurrency |
| v0.1.18 | KDN knowledge-aware policy | Pin/Prefetch/Placement/Clear intent, value model, replay |
| v0.1.19 | Multi-block non-prefix fusion | parallel retrieval, selective recompute, quality fallback |
| v0.2.0 | Integrated research baseline | stable interfaces, cross-version compatibility, complete experimental loop |

## 8. Per-Version Plan

## v0.1.10: Contract and Observability Baseline

### Goal

Freeze stable vocabulary without implementing the complete KDN Server:

- Instance Capability;
- CacheArtifact and CacheReplicaObservation;
- KDNServingEndpoint;
- KDNServingTask;
- LMCacheCompatibilityProfile;
- QueueWork;
- Trace sources and stages;
- Legacy compatibility mapping.

### Acceptance

- the completed #138 capability contract remains compatible;
- core objects contain no KV bytes, private Redis keys, credentials, or LMCache private classes;
- KDN Knowledge API and LMCache-facing Serving API are distinguishable;
- LMCache Profiles represent MP, Plugin, Legacy, and unknown capabilities;
- Trace distinguishes KDN, Provider, LMCache, Proxy, and vLLM sources;
- CPU-only tests require no external vLLM, Redis, or LMCache cluster.

## v0.1.11: KDN Knowledge Control Plane

### Main Steps

1. Implement KnowledgeObject and version management.
2. Support multiple CacheArtifacts per KnowledgeObject.
3. Determine Artifact compatibility through Capability and LMCache Data Profiles.
4. Separate desired state from Provider observations.
5. Build KDN Endpoint and Provider registries.
6. Map knowledge into KDN Serving namespaces/location references.
7. Expose only coarse knowledge availability to Scheduler.
8. Map Legacy `kv_ready` into `compatibility=unknown`.

### Acceptance

- one knowledge item supports multiple models, adapters, and LMCache Profiles;
- the control plane does not access or duplicate physical KV data;
- expired Provider observations are not treated as authoritative;
- Redis does not appear in the stable knowledge domain model.

## v0.1.12: Independent KDN Remote Cache Serving Plane MVP

### Main Steps

1. Run KDN as an independent server.
2. Implement Serving Handshake and Capability Negotiation.
3. Implement a minimum Lookup, Store, Load/Retrieve, and TaskStatus set.
4. Define a Provider SPI aligned with public LMCache L2/remote-storage semantics.
5. Implement a Mock Provider.
6. Implement the first real Provider; Redis is acceptable only as a Provider.
7. Implement an Instance-side LMCache KDN Connector/Adapter.
8. Keep the data hot path independent from complex policy queries.
9. Record actual bytes, coverage, queueing, and operation time.

### Acceptance

- LMCache can use KDN as a remote-cache service;
- KDN Server remains independent of a concrete Provider;
- Mock and Redis can be exchanged without changing the Serving Protocol;
- Redis keys and credentials never enter CacheRoute APIs;
- serving failures support text fallback.

## v0.1.13: Multi-Provider and LMCache Evolution Compatibility

### Main Steps

1. Prefer an LMCache MP L2 Plugin Profile.
2. Support at least one compatibility Profile such as Remote Storage Plugin or Legacy.
3. Add a second real Provider to prove KDN is not Redis-bound.
4. Build a Compatibility Matrix and Profile Conformance Suite.
5. Allow different LMCache Profiles to register concurrently.
6. Implement Profile upgrade, downgrade, and deprecation states.
7. Implement Provider generation, reconnect, and task recovery.
8. Migrate or rebuild incompatible key/layout/serde data.
9. Establish periodic validation against the latest LMCache Profile.

### Acceptance

- KDN runs with at least two Provider configurations;
- MP is the default evolution direction;
- old Profiles are explicitly accepted or rejected;
- LMCache interface changes require only Compatibility Adapter changes;
- incompatible upgrades never silently reuse old Artifacts.

## v0.1.14: Proxy KVCache Manager

### Main Steps

1. Build an Instance Cache Observation View.
2. Use KDN Lookup, LMCache events, Load results, and actual hits as sources.
3. Store time, source, Profile, Generation, and TTL for every observation.
4. Support UNKNOWN, REMOTE_AVAILABLE, PREPARING, LOCAL_AVAILABLE, STALE, and FAILED.
5. Implement Single-flight per Artifact/Instance.
6. Invalidate on Instance, KDN, or Provider generation change.
7. Do not copy the Provider chunk index into Proxy.

### Acceptance

- Proxy distinguishes KDN availability, Provider hit, loading, and local availability;
- expired observations return to UNKNOWN;
- shared preparation executes once;
- LMCache Profile changes invalidate related observations.

## v0.1.15: Knowledge Injection and Compute Queue Model

- Compile CachePlan into ExecutionGraph.
- Maintain CONTROL, KDN_LOOKUP, KDN_SERVE, NET_KV, CACHE_LOAD, PREFILL, DECODE, and FUSION queues.
- Use a Compute Fast Path for text and local hits.
- Unify dependency, reference, cancellation, and event-wakeup handling.
- Record wait and execution reasons for every node.

## v0.1.16: Parallel Network KV and Pure Compute

- Overlap KDN Lookup/Load with other requests' Prefill/Decode.
- Maintain timelines per KDN Endpoint, Provider, link, and Instance.
- Prepare multiple blocks across Providers/Endpoints concurrently.
- Measure Overlap Ratio, GPU Cache-wait Idle, Network Idle, and Pipeline Makespan.
- Compare serialized, text_bypass, and fully parallel baselines.

## v0.1.17: Queue Generality and Stability

- hierarchical admission and backpressure;
- priority, aging, deadline hints, and starvation prevention;
- segmentation/yield for large operations;
- adaptive KDN/network/load concurrency;
- KDN, Provider, LMCache, and Instance fault fallback;
- policy plugins that cannot bypass state correctness;
- no Pareto or learning-based global scheduling in this phase.

## v0.1.18: KDN Knowledge-Aware Cache Policy

KDN policy emits:

```text
BUILD
PREFETCH
PIN
UNPIN
PLACE
MOVE_INTENT
CLEAR
REFRESH
REBUILD
```

Physical execution is delegated to the active Provider/LMCache Profile.

Research topics:

- knowledge value;
- capacity and cost across Providers;
- Pin, prefetch, and clear;
- hotspot placement;
- maintenance budgets;
- background interference with online requests;
- Trace Replay.

## v0.1.19: Multi-Knowledge-Block Non-Prefix Fusion

- ordered Knowledge Blocks and Prompt Layout;
- multi-Artifact and KDN-candidate queries;
- full, partial, non-prefix, overlap, and miss classification;
- Coverage Map;
- FusionPlan compilation into ExecutionGraph;
- parallel multi-block KDN Lookup/Load;
- LMCache non-prefix reuse or CacheBlend;
- selective recomputation and quality guards;
- reliable text fallback.

## v0.2.0: Integration, Stability, and Research Baseline

### Release Criteria

- KDN is an independent server with two stable external interfaces;
- KDN is not bound to Redis or one LMCache mode;
- at least two Providers are validated;
- at least baseline and latest LMCache Profiles are validated;
- MP is the default Profile and Legacy has an explicit deprecation policy;
- Knowledge Control Plane and Serving hot path scale independently;
- Proxy uses short-lived observations rather than an authoritative block index;
- network KV and pure compute overlap;
- queues provide Single-flight, backpressure, fairness, cancellation, and fallback;
- at least two knowledge blocks support non-prefix reuse;
- KDN provides at least one knowledge-value policy;
- important fault and upgrade scenarios have reproducible tests;
- text, single-knowledge, and Legacy paths remain compatible.

## 9. LMCache Evolution Compatibility Test Framework

### 9.1 Contract Tests

Run one KDN Serving Contract Suite against:

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

- LMCache minor upgrade;
- adapter API rename;
- completion-model change;
- key-format change;
- incompatible layout/serde;
- Provider restart;
- rolling KDN upgrade;
- concurrent old and new LMCache clients;
- Profile deprecation;
- downgrade rollback.

### 9.4 Failure Principles

- Unknown capability is not assumed supported.
- Incompatible Artifacts are not loaded.
- Provider operation failure does not corrupt the knowledge catalog.
- KDN control failure does not interrupt already authorized serving tasks.
- Serving failure permits Proxy text fallback.
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
- Head-of-line Blocking Time;
- Single-flight saved tasks and bytes;
- Profile negotiation failure rate;
- incompatible rebuild and fallback rate;
- multi-Provider load distribution;
- result consistency before and after an LMCache upgrade.

## 11. State Boundaries

### KDN Knowledge Control Plane

Authoritative for knowledge, Artifacts, policy, desired state, supported Profiles, and historical value.

### KDN Serving Plane

Authoritative for KDN requests, tasks, and current serving results, but historical task results do not permanently prove Provider physical state.

### Provider / LMCache Runtime

Authoritative for physical-object existence, bytes, layout, storage location, and low-level operation results.

### Proxy

Owns request plans, short-lived Instance/KDN observations, shared preparation tasks, and queues.

### Instance / vLLM

Authoritative for actual hit tokens, model execution, Prefill, and Decode results.

## 12. Testing and Experiment Requirements

### Unit Tests

- object identities and state transitions;
- LMCacheCompatibilityProfile;
- capability negotiation;
- protocol versions;
- secret/private-key rejection;
- observation TTL;
- CachePlan/FusionPlan;
- ExecutionGraph;
- Single-flight;
- Trace provenance.

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
