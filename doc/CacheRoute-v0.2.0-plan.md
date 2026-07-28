# CacheRoute v0.2.0 Evolution Plan

> Status: Planning draft  
> Current release baseline: v0.1.9  
> Current development baseline: `v1` (vLLM 0.25.1 + LMCache 0.5.2 + PyTorch 2.11.0)  
> Compatibility path: `legacy` remains runnable but feature-frozen  
> Target release: v0.2.0  
> Core foundation: vLLM + LMCache  
> Long-term positioning: build a KVCache Distribution Network (KDN) for large-model inference

## 0. Planning Decision

CacheRoute does not define KDN only as a knowledge-control service, nor as another single-node KVCache engine.

> **KDN = KVCache Distribution Network: network infrastructure for maintaining, locating, distributing, and governing KVCache resources.**

KDN follows a CDN-like infrastructure model, but its content is not static files or video. It distributes KVCache resources constrained by model, tokenizer, adapter, KV layout, parallelism, compatibility, and lifecycle.

Upward, KDN provides Scheduler, Proxy, Instance, and management tools with unified KVCache infrastructure capabilities:

- global naming and directory;
- compatibility evaluation;
- node, region, and topology management;
- CacheArtifact location;
- replica placement, replication, migration, warming, pinning, clearing, and invalidation;
- network-source selection, transfer planning, bandwidth control, and queue governance;
- multi-node, multi-region, and multi-tier KVCache distribution;
- operational state, reuse value, cost, and failure observations;
- v1/Legacy and LMCache-release compatibility.

Downward, KDN operates each node's KVCache Runtime through LMCache public interfaces, adapters, plugins, Coordinator, SDK, metrics, and events. KDN does not reimplement LMCache's node-local Token Database, chunk/hash/key model, KV layout, serde, L1/L2 StorageManager, locking, or device-memory management.

### 0.1 v1 Data Paths

The high-frequency local path inside one Instance remains:

```text
vLLM == LMCacheMPConnector == local LMCache MP == local L1 / L2
```

Cross-node or cross-region KVCache distribution is organized by the KDN Distribution Plane:

```text
source LMCache Runtime
        == KDN Transfer Session / transport
        == target LMCache Runtime
```

The KDN Control Plane does not execute policy for every chunk, but the KDN Distribution Plane may carry, proxy, or delegate the actual network transfer.

### 0.2 Runtime Profile Policy

- `v1`: the only development path for new functionality.
- `legacy`: preserves old startup, Redis scan/dump/restore/inject, requests, and experiment flows; feature-frozen.
- `auto`: migration discovery at startup only; it must resolve and freeze one explicit Profile.
- A v1 request never silently enters a Legacy write path.
- Legacy data enters v1 only through explicit migration, import, or rebuild.

### 0.3 Non-Negotiable Principles

- KDN is network-level KVCache infrastructure, not an alias for Redis.
- KDN may manage and transfer KVCache without duplicating LMCache's node-local data model or storage engine.
- Stable KDN identities use Knowledge, Artifact, Replica, Node, and Transfer, not raw Redis keys or LMCache-private Python objects.
- Physical KV formats are constrained by `LMCacheCompatibilityProfile` and `CacheDataProfile`.
- Cross-node transfer validates model, tokenizer, adapter, layout, dtype, parallelism, chunk/serde profile, and content integrity.
- Unknown capabilities are never assumed to be supported.
- Control Plane, Distribution Plane, and node-local Runtime must scale and fail independently.
- Every network-distribution task is observable, cancellable, retryable, rate-limited, and idempotent.
- Proxy does not copy the global physical chunk index. KDN owns the global directory; LMCache owns node-local physical indexes.

## 1. CDN Analogy and KDN Vocabulary

KDN borrows the infrastructure pattern of a CDN, but static-object semantics cannot be copied directly.

| CDN concept | KDN equivalent |
|---|---|
| Content Object | CacheArtifact |
| Origin | Artifact Producer, durable L2, or designated Origin Node |
| Edge POP | KDN Edge Node / LMCache Endpoint |
| Cache Replica | CacheReplica |
| Cache Fill | Distribution / Prefetch / Replication |
| Purge | Invalidate / Clear |
| Routing | Compatible Source Selection |
| TTL | Artifact lifecycle, Replica Lease, and Observation TTL |
| Bandwidth Control | Transfer Admission, Rate Limit, and Queue |
| Cache Hit | Token Coverage, Remote Availability, and Local Hit |
| Regional Shield | Regional KDN Node or shared L2 |

Important differences:

1. KVCache is reusable only across compatible runtimes.
2. An Artifact may cover token ranges rather than one complete object.
3. Transfer is followed by LMCache load, registration, or materialization.
4. Node-local hit and network availability are different states.
5. Purge and invalidation consider knowledge, model, and layout versions.
6. Network distance, bandwidth, GPU compute savings, and TTFT jointly determine distribution value.

## 2. Overall Architecture

### 2.1 Legend

```text
==  request, KVCache, or bulk-data transfer path
--  control, management, policy, or observation API
|   containment or component hierarchy
```

### 2.2 CacheRoute and the KDN Cluster

```text
+-------------------- Client / Workload --------------------+
| OpenAI-compatible inference request                       |
+============================+===============================+
                             |
                             v
+---------------------- CacheRoute Scheduler ----------------+
| request routing | admission | Proxy / Instance selection  |
| KDN region / node selection                                |
+=================+====================+----------------------+
                  |                    |
                  | request path       | KDN control query
                  v                    v
+------------- CacheRoute Proxy -------+     +---------------- KDN Control Plane ----------------+
| Knowledge resolve                    |     | Global Artifact Directory                         |
| CachePlan / DistributionPlan         |     | Node / Region / Topology Registry                 |
| ExecutionGraph / queue / fallback    |     | Compatibility / Placement / Lifecycle Policy      |
+=================+====================+     | Route / Replica / Transfer orchestration          |
                  |                          +----------------------+------------------------------+
                  | inference request                               |
                  v                                                  |
+------------- CacheRoute Instance ----------------------------------+----------------------------+
| vLLM | LMCacheMPConnector | local LMCache MP | KDN Node Agent / Gateway                           |
+===========================+==================+====================================+===============+
                            |                                                       |
                            | local KV path                                         | control/status
                            v                                                       |
                  +---------------- local LMCache Runtime ----------------+          |
                  | Token DB | L1 | L2 adapters | cache objects          |          |
                  +=======================+===============================+          |
                                          |                                          |
                                          | KDN distribution                         |
                                          v                                          v
+----------------------------------- KDN Distribution Plane --------------------------+
|                                                                                     |
| +-- KDN Edge Node A == Transfer Session / Transport == KDN Edge Node B               |
| |   |-- source selection                    |-- integrity / resume / rate limit       |
| |   |-- local LMCache Gateway               |-- retry / cancellation / accounting    |
| |   +-- local or durable replicas           +-- publish into target LMCache Runtime  |
| |                                                                                   |
| +-- optional regional/origin nodes, shared L2, object store, NIXL, Mooncake, RDMA    |
|                                                                                     |
+=====================================================================================+
```

### 2.3 Three Paths

```text
Inference Path
Client == Scheduler == Proxy == Instance == vLLM

Local KV Path
vLLM == LMCacheMPConnector == local LMCache MP == local L1 / L2

KDN Distribution Path
source LMCache == KDN Node/Transport == target LMCache
```

Control relations:

```text
Scheduler / Proxy / Instance
        -- Artifact / Route / Distribution API
        --> KDN Control Plane

KDN Control Plane
        -- placement / transfer / lifecycle task
        --> KDN Node Agent

KDN Node Agent
        -- LMCache Gateway
        --> local LMCache Runtime

KDN Node / LMCache Runtime
        -- observations / task result / hit value
        --> KDN Control Plane
```

## 3. Formal Definition of KDN

### 3.1 KDN Cluster

A KDN Cluster is KVCache network infrastructure composed of control nodes, edge nodes, regional nodes, and LMCache endpoints.

```text
KDN Cluster
|
+-- Control Plane
|   |-- Global Artifact Directory
|   |-- Node / Region / Topology Registry
|   |-- Placement and Replication Policy
|   |-- Route and Source Selection
|   |-- Lifecycle / Quota / Security
|   +-- Audit / Statistics / Cost Model
|
+-- Distribution Plane
|   |-- KDN Edge Node / Node Agent
|   |-- Transfer Session
|   |-- Pull / Push / Relay / Resume
|   |-- Rate Limit / Admission / Queue
|   |-- Integrity Verification
|   +-- Replica Publish / Remove
|
+-- LMCache Integration Plane
    |-- MPHTTPGateway
    |-- MPCoordinatorGateway
    |-- MPSDKGateway
    |-- MPMetricsEventGateway
    |-- Transport / Adapter Gateway
    +-- LegacyCacheAdapter
```

### 3.2 KDN Control Plane Owns

- global Artifact naming, version, and compatibility;
- node, region, network, and storage topology;
- the logical Replica directory and desired state;
- Origin, Source, Target, and relay-path selection;
- placement, replication, migration, warming, pin, clear, and rebuild policy;
- quota, tenancy, authorization, audit, and lifecycle;
- transfer-task idempotency, priority, deadline, cancellation, and retry policy;
- short-lived physical observations and RouteDecision generation;
- governance based on reuse value, bandwidth, TTFT, and compute savings.

### 3.3 KDN Distribution Plane Owns

- establishing TransferSession between compatible nodes;
- Pull, Push, Relay, and delegated transfer;
- selecting the concrete transport or backend;
- transferring bulk KVCache or resolvable transport references;
- resume, retry, verification, rate limit, backpressure, and cancellation;
- publishing completed data into the target LMCache Runtime;
- reporting actual bytes, token coverage, bandwidth, latency, and errors;
- switching Source or falling back to rebuild when a node or link fails.

### 3.4 LMCache Runtime Owns

- token chunking, hashes, chunk keys, and physical KV objects;
- KV layout, dtype, serde, and device-specific format;
- node-local L1/L2 residency and adapter cascade;
- Store, Retrieve, Prefetch, Pin, Unpin, and Clear;
- node-local locking, capacity, quota, and eviction execution;
- actual hit-token, remote-read, metrics, and events;
- registering or materializing an incoming Artifact for vLLM use.

### 3.5 Authority Boundary

| Information | Authority |
|---|---|
| KnowledgeObject and Artifact semantics/version | KDN Control Plane |
| Artifact compatibility and Data Profile | KDN Control Plane |
| Node, Region, and topology | KDN Control Plane |
| desired logical Replica state | KDN Control Plane |
| physical Replica existence | LMCache Runtime observation |
| global Replica Directory | KDN, maintained from node observations |
| node-local Chunk Index and KV bytes | LMCache Runtime |
| TransferSession and network result | KDN Distribution Plane |
| actual hit tokens at an Instance | Instance-side LMCache |
| request wait, compute release, and fallback | Proxy |
| global request and resource-pool selection | Scheduler |

KDN may authoritatively maintain the Replicas that should exist and a directory of confirmed Replicas, but it must not invent or indefinitely retain stale physical-existence claims. Every confirmation carries source, Generation, timestamp, and TTL.

## 4. KDN APIs and Distribution Protocol

### 4.1 Control API

```text
RegisterNode
HeartbeatNode
RegisterArtifact
UpdateArtifactVersion
ResolveArtifact
LocateReplicas
GetRouteDecision
CreatePlacementIntent
CreateReplicationIntent
CreateMigrationIntent
CreatePrefetchIntent
CreatePinIntent
CreateUnpinIntent
CreateClearIntent
CreateRebuildIntent
GetOperationStatus
CancelOperation
GetClusterTopology
GetCapacitySummary
GetTransferSummary
ReportRequestOutcome
```

### 4.2 Distribution API / Protocol

```text
OpenTransferSession
AuthorizeSource
FetchArtifact
FetchSegments
PushArtifact
PublishReplica
ResumeTransfer
VerifyTransfer
CompleteTransfer
AbortTransfer
RemoveReplica
```

The Control API does not carry bulk KVCache. The Distribution API may transfer data directly or return a transport reference supported by both sides.

### 4.3 API Mapping Diagram

```text
CacheRoute / KDN Control Request
            |
            v
KDN versioned Control API
            |
            +-- directory / policy / route ------> KDN Control Plane
            |
            +-- placement / replication ---------> DistributionPlan
            |
            +-- node operation ------------------> KDN Node Agent
                                                      |
                                                      v
                                              LMCache Gateway
                                                      |
                           +--------------------------+-------------------------+
                           |                          |                         |
                         MP HTTP                  Coordinator               SDK / Events
                           |                          |                         |
                           +--------------------------+-------------------------+
                                                      |
                                                      v
                                             local LMCache Runtime
```

Cross-node data path:

```text
DistributionPlan
      |
      v
OpenTransferSession
      |
      +-- direct stream ---------> KDN transport
      |
      +-- shared backend --------> object store / shared L2
      |
      +-- native transport ------> NIXL / Mooncake / RDMA / plugin
      |
      v
target LMCache publish / prefetch / load
```

### 4.4 Stable Protocol Must Not Expose

```text
Redis password
raw Redis key
LMCache private Python class
unversioned internal Chunk Key
device pointer
private serialized object without Data Profile
backend-specific credentials in domain objects
```

Backend credentials are supplied only through Secret References or node-local configuration.

## 5. Core Objects

### 5.1 KnowledgeObject

```text
knowledge_id
content_hash
content_version
text_location
semantic_metadata
tokenization_hints
created_at
updated_at
```

### 5.2 CacheArtifact

```text
artifact_id
knowledge_id
artifact_version
content_fingerprint
model_fingerprint
tokenizer_fingerprint
adapter_fingerprint
kv_layout_profile
kv_dtype
parallelism_profile
lmcache_data_profile
key_format_version
serde_profile
token_coverage
created_at
updated_at
```

CacheArtifact is the stable logical identity of a distributable KVCache resource. It is not a node-local Chunk Key.

### 5.3 KDNNode

```text
node_id
cluster_id
region
zone
endpoint
node_role
runtime_profile
lmcache_profile
transport_capabilities
storage_capabilities
network_summary
capacity_summary
health
generation
last_heartbeat_at
```

Recommended `node_role` values:

```text
control
edge
regional
origin
relay
```

### 5.4 CacheReplicaRecord

```text
replica_id
artifact_id
node_id
desired_state
observed_state
source_replica_id
data_profile
token_coverage
lease
generation
observation_source
observed_at
expires_at
integrity_status
```

KDN owns `desired_state`; node and LMCache Runtime observations provide `observed_state`.

### 5.5 DistributionPlan

```text
plan_id
artifact_id
source_candidates
selected_source
target_nodes
transport_profile
segment_plan
priority
deadline
bandwidth_budget
fallback
reason_code
state
```

### 5.6 TransferSession

```text
transfer_id
plan_id
artifact_id
source_node_id
target_node_id
transport_profile
idempotency_key
lease
bytes_expected
bytes_transferred
tokens_expected
tokens_transferred
checksum
resume_token
state
requested_at
started_at
finished_at
error
```

### 5.7 CacheOperationTask

```text
operation_id
operation_type
artifact_id
node_ids
distribution_plan_id
priority
deadline
idempotency_key
state
result
error
created_at
updated_at
```

### 5.8 RouteDecision

```text
route_decision_id
request_id
artifact_id
target_instance_id
compatible_replicas
selected_source
estimated_transfer_time
estimated_compute_saved
estimated_ttft
confidence
fallback
reason_code
```

### 5.9 CachePlan / ExecutionGraph

```text
CachePlan
|-- knowledge blocks
|-- matched artifacts
|-- RouteDecision
|-- DistributionPlan
|-- recompute ranges
|-- fallback

ExecutionGraph
|-- CONTROL
|-- KDN_LOOKUP
|-- KDN_ROUTE
|-- KDN_TRANSFER
|-- CACHE_PUBLISH
|-- CACHE_LOAD
|-- PREFILL
|-- DECODE
|-- FUSION
```

## 6. LMCache Integration and Compatibility

### 6.1 LMCacheCompatibilityProfile

```text
profile_id
lmcache_version_range
runtime_mode
connector_profile
data_profile
key_format_version
layout_profile
serde_profile
supported_operations
transport_capabilities
completion_model
locking_model
event_model
cancellation_model
status
validated_at
```

### 6.2 Gateway Structure

```text
KDN Node Agent / Control Service
            |
            v
+---------------- LMCache Integration Gateway ----------------+
| CapabilityFactory                                           |
| AdapterFactory                                              |
| |-- MPHTTPGateway                                           |
| |-- MPCoordinatorGateway                                    |
| |-- MPSDKGateway                                            |
| |-- MPMetricsEventGateway                                   |
| |-- TransportAdapterGateway                                 |
| |-- MockGateway                                             |
| +-- LegacyCacheAdapter                                      |
+-------------------------------------------------------------+
            |
            v
local LMCache public interfaces and loaded adapters
```

### 6.3 Startup Capability Discovery

Every v1 KDN Node must:

1. query LMCache version, Build ID, and runtime mode;
2. query Connector, Config, Tier, and loaded adapters;
3. probe HTTP routes, SDK, metrics, events, and transports;
4. build an immutable CapabilitySnapshot;
5. validate chunk size, hash, layout, dtype, serde, and Data Profile;
6. create a Node Generation;
7. register with the KDN Control Plane;
8. mark unknown capability as `unsupported` or `unknown`.

### 6.4 Transfer Compatibility Gate

KDN directly distributes an Artifact only when:

```text
model compatible
tokenizer compatible
adapter compatible
kv layout compatible
kv dtype compatible
parallelism compatible
lmcache data profile compatible
key / serde profile compatible
transport profile supported
integrity metadata available
```

Otherwise it must:

```text
reject reuse
select another replica
migrate
transcode through an explicit supported adapter
rebuild
fall back to text compute
```

Unknown or incompatible data is never reused silently.

## 7. Iteration Overview

| Version | Theme | Main delivery |
|---|---|---|
| v0.1.10 | Contract and observation baseline | RuntimeProfile, Artifact, Node, Replica, Operation, Queue, Trace, Legacy projection |
| v0.1.11 | KDN Control Plane and global directory | Artifact Directory, Node Registry, Topology, Desired/Observed State |
| v0.1.12 | KDN Distribution Plane MVP | Node Agent, TransferSession, one-source-to-one-target distribution, LMCache publish |
| v0.1.13 | Multi-node replication and source routing | Replica Placement, Source Selection, retry, recovery, second Transport/Profile |
| v0.1.14 | Proxy KVCache Manager | RouteDecision, short-lived Instance view, Single-flight |
| v0.1.15 | Distribution and compute queues | ExecutionGraph, Transfer Queue, Compute Fast Path |
| v0.1.16 | Network-compute overlap | Work-conserving Pipeline, bandwidth governance, overlap benchmark |
| v0.1.17 | Cluster stability and generality | Admission, backpressure, fairness, aging, failover |
| v0.1.18 | KDN resource-governance policy | Placement, Replication, Prefetch, Pin, Purge, value model |
| v0.1.19 | Multi-block distribution and fusion | parallel location, segmented transfer, selective recomputation, quality fallback |
| v0.2.0 | KVCache distribution-infrastructure baseline | multi-node KDN, stable protocols, cross-LMCache Profile, complete experiment loop |

## 8. Per-Version Plan

### v0.1.10: Contract and Observation Baseline

Freeze the stable vocabulary required for clustering:

- RuntimeProfile;
- LMCacheCompatibilityProfile;
- Instance Capability;
- CacheArtifact;
- KDNNode;
- CacheReplicaRecord;
- CacheOperationTask;
- QueueWork;
- Trace source and stage;
- read-only Legacy projection.

Acceptance:

- core objects contain no KV bytes, plaintext credentials, raw Redis keys, or LMCache-private classes;
- Desired State and Observed State are separate;
- Node, Replica, Operation, and Queue transitions are validated;
- v1 and Legacy Profiles never switch dynamically within a request;
- CPU-only tests do not require an external cluster.

### v0.1.11: KDN Control Plane and Global Directory

Main steps:

1. implement KnowledgeObject and CacheArtifact directories;
2. implement KDN Node/Region/Topology Registry;
3. build the global Artifact-to-Replica directory;
4. distinguish desired Replicas from confirmed Replicas;
5. add compatibility gates;
6. add Node Generation and Observation TTL;
7. provide LocateReplicas and GetRouteDecision;
8. let Scheduler consume only coarse resource summaries.

Acceptance:

- one Artifact may have Replicas across multiple regions and nodes;
- expired observations are not physical facts;
- incompatible nodes never enter Source Candidates;
- the directory does not copy node-local Chunk Indexes.

### v0.1.12: KDN Distribution Plane MVP

Main steps:

1. start an independent KDN Node Agent;
2. implement OpenTransferSession and one-source-to-one-target transfer;
3. implement at least one real Direct, Shared Backend, or Mock Transport path;
4. export or reference an Artifact through the LMCache Gateway;
5. Publish/Prefetch/Load it into the target LMCache;
6. implement verification, idempotency, timeout, cancellation, and basic retry;
7. report actual bytes, token coverage, and time;
8. fall back to rebuild or text compute on failure.

Acceptance:

- a compatible Artifact on one node can be distributed to another node;
- target LMCache reports availability or an actual hit after transfer;
- the Control API does not carry bulk payload;
- replacing the Transport does not change Artifact and Route APIs.

### v0.1.13: Multi-Node Replication, Source Routing, and Recovery

Main steps:

1. support multiple Source Candidates;
2. select sources by region, bandwidth, load, health, and compatibility;
3. support one Source to multiple Targets;
4. support Relay or shared L2;
5. add a second Transport or LMCache Profile;
6. support resume, Source Failover, and Transfer Recovery;
7. build Placement/Replication state machines;
8. build a cross-release Compatibility Matrix;
9. migrate, rebuild, or reject incompatible data.

Acceptance:

- a compatible Replica replaces a failed Source;
- multi-node replication is idempotent;
- KDN validates at least two Transport/Profile configurations;
- LMCache interface changes affect only Gateway Adapters.

### v0.1.14: Proxy KVCache Manager

- maintain a short-lived Instance Cache View;
- request RouteDecision from KDN;
- distinguish REMOTE_AVAILABLE, TRANSFERRING, PUBLISHED, LOCAL_AVAILABLE, STALE, and FAILED;
- implement Single-flight per Artifact/Target;
- compile DistributionPlan into CachePlan;
- invalidate on Instance, Node, or Profile Generation change.

### v0.1.15: Distribution and Compute Queues

- add KDN_ROUTE, KDN_TRANSFER, and CACHE_PUBLISH to ExecutionGraph;
- separate Control, Transfer, Cache Load, and Compute concurrency domains;
- define Share Key, priority, deadline, bandwidth budget, and fallback;
- preserve a Compute Fast Path for text requests;
- keep per-transfer scheduling out of Scheduler.

### v0.1.16: Network-Compute Overlap

- overlap KVCache transfer with Prefill/Decode for other requests;
- adjust concurrency from network and GPU state;
- use work-conserving scheduling;
- add Network-Compute Gantt, Overlap Ratio, and Saved Compute;
- handle timeout, cancellation, and fallback.

### v0.1.17: Cluster Stability and Generality

- Admission Control and Backpressure;
- multi-tenant quota and bandwidth governance;
- fairness, aging, and starvation guards;
- Node/Region Failover;
- protection against transfer storms and cache pollution;
- tests across models, Instances, KDN Nodes, and bandwidths.

### v0.1.18: KDN Resource-Governance Policy

Policy inputs:

- Artifact popularity and knowledge co-occurrence;
- regional Replica distribution;
- Source/Target bandwidth and queues;
- LMCache capacity, hit, and eviction;
- Proxy wait, TTFT, and GPU idle;
- compute savings, transfer cost, and rebuild cost;
- online and background load.

Policy outputs:

```text
PLACE
REPLICATE
MIGRATE
PREFETCH
PIN
UNPIN
PURGE
REFRESH
REBUILD
BYPASS
```

Every decision has a Reason Code and supports Shadow, Replay, and controlled enablement.

### v0.1.19: Multi-Knowledge-Block Distribution and Fusion

- resolve multiple Knowledge Blocks per request;
- parallelize Resolve, Locate, and Source Selection;
- establish TransferSessions for different Artifacts in parallel;
- support Full, Partial, Overlap, and Reorder;
- use LMCache non-prefix reuse, CacheBlend, or an equivalent capability;
- recompute only required tokens;
- fall back to text on quality failure or timeout.

### v0.2.0: Integrated KVCache Distribution Infrastructure

v0.2.0 is complete when:

- KDN is deployed as a Cluster with a Control Plane and multiple Nodes;
- Artifacts can be located, transferred, published, and cleared across nodes;
- at least two Nodes and two LMCache/Transport Profiles are validated;
- Source Selection, Replica Placement, and TransferSession are reproducible;
- Control Plane and Distribution Plane scale independently;
- node-local data semantics remain owned by LMCache;
- Proxy consumes KDN RouteDecision and short-lived observations;
- network transfer overlaps computation;
- queues support Single-flight, backpressure, fairness, cancellation, retry, and fallback;
- at least two knowledge blocks support parallel distribution and reuse;
- v1 is default and Legacy retains a minimal regression set;
- critical failure, upgrade, and cross-region scenarios have reproducible experiments.

## 9. Lifecycle and State

### 9.1 Artifact Lifecycle

```text
REGISTERED
    -> BUILDING
    -> AVAILABLE
    -> DISTRIBUTING
    -> PARTIALLY_REPLICATED
    -> REPLICATED
    -> STALE
    -> INVALIDATED
    -> PURGED
```

### 9.2 Replica State

```text
UNKNOWN
PLANNED
TRANSFERRING
VERIFYING
PUBLISHED
AVAILABLE
STALE
FAILED
REMOVING
REMOVED
```

### 9.3 Transfer State

```text
PENDING
AUTHORIZED
CONNECTING
TRANSFERRING
VERIFYING
PUBLISHING
SUCCEEDED
FAILED
CANCELLED
EXPIRED
```

Every transition records:

```text
source
generation
reason_code
observed_at
expires_at
trace_id
```

## 10. Observability and Research Metrics

### Request Metrics

- TTFT P50/P95/P99;
- throughput and completion time;
- actual hit tokens;
- remotely reused tokens;
- text fallback rate;
- compute time saved.

### Distribution Metrics

- Route Decision latency;
- Source Selection hit rate;
- Transfer Queue Wait;
- Transfer Setup Time;
- bytes/tokens transferred;
- effective bandwidth;
- resume and retry count;
- Source Failover count;
- integrity failures;
- Publish/Load Time;
- distribution success rate.

### Cluster Metrics

- Artifact/Replica count;
- Region/Node distribution;
- Replica freshness;
- capacity and quota;
- eviction, purge, and rebuild;
- hotspots and load skew;
- cross-region traffic;
- cache pollution;
- Placement Policy benefit.

### Parallelism Metrics

- Network-Compute Overlap Ratio;
- GPU Idle Due to Cache Wait;
- Network Idle With Pending Work;
- Head-of-Line Blocking;
- Single-flight saved tasks and bytes;
- work-conserving utilization.

## 11. Testing and Experiment Requirements

### Unit Tests

- IDs, fingerprints, and state transitions;
- Artifact compatibility;
- RouteDecision;
- Placement/Replication Policy;
- TransferSession idempotency;
- Resume, Retry, and Cancel;
- Observation TTL and Generation;
- Runtime Profile and Capability Snapshot;
- Secret and private-field rejection.

### Component Tests

- KDN Control Plane;
- KDN Node Agent;
- Mock LMCache Gateway;
- Mock Transport;
- MP HTTP/Coordinator Gateway;
- two Nodes and two Transport/Profile configurations;
- Node restart and Generation change;
- Source Failover;
- LMCache availability after Publish.

### End-to-End Tests

- vLLM + LMCache + Proxy + KDN Control + two KDN Nodes;
- single-node local hit;
- cross-node distribution;
- multi-Target replication;
- Source failure recovery;
- bandwidth limit and queue backpressure;
- network-compute overlap;
- multi-knowledge-block;
- Profile incompatibility and text fallback;
- minimal Legacy regression.

### Experiment Reproduction

Each experiment stores:

```text
CacheRoute version
vLLM / LMCache version
KDN protocol version
Node / Region topology
LMCacheCompatibilityProfile
Transport profile
Artifact / Replica layout
workload
bandwidth / latency
queue and policy parameters
RouteDecision
DistributionPlan
TransferSession
ExecutionGraph
request-level result
aggregate metrics
failure events
```

## 12. Non-Goals

v0.2.0 does not require:

- reimplementing LMCache Token Database, allocator, serde, or Paged KV;
- fixing one network transport forever;
- using raw Redis keys as global KDN identity;
- scheduling per-chunk transfers in Scheduler;
- synchronously moving all KV data through the Control Plane;
- silently converting incompatible KVCache;
- implementing global production-grade multi-region consistency in one release;
- replacing vLLM model execution and engine scheduling.

## 13. Long-Term Evolution

After v0.2.0, KDN should evolve:

1. from one cluster into a multi-region KVCache Distribution Network;
2. from a central directory into hierarchical directories and regional autonomy;
3. from simple Source Selection into latency-, cost-, and SLO-aware routing;
4. from one-shot replication into continuous popularity-driven Replica Placement;
5. from one Transport into unified selection across NIXL, Mooncake, RDMA, object storage, and shared L2;
6. from single tenancy into quota, isolation, and fairness governance;
7. from Artifact-level distribution into token-segment and composed multi-block distribution;
8. in continuous alignment with LMCache MP, Coordinator, Adapter, Transport, and Observability capabilities;
9. while preserving a clear boundary between KDN network infrastructure and LMCache node-local Runtime.

CacheRoute's long-term core is:

> **Elevate KVCache from a single-runtime resource into infrastructure that can be named, located, distributed, replicated, governed, and observed across a network.**
