# CacheRoute v0.2.0 演进规划

> 状态：规划草案  
> 当前发布基线：v0.1.9  
> 当前开发基线：`v1`（vLLM 0.25.1 + LMCache 0.5.2 + PyTorch 2.11.0）  
> 兼容路径：`legacy` 保持可用但功能冻结  
> 目标版本：v0.2.0  
> 核心底座：vLLM + LMCache  
> 长期定位：构建面向大模型推理的 KVCache Distribution Network（KDN）

## 0. 规划结论

CacheRoute 后续不把 KDN 仅定义为一个知识控制服务，也不把它定义为另一套单机 KVCache 引擎。

> **KDN = KVCache Distribution Network：维护、定位、分发和治理 KVCache 资源的网络基础设施。**

KDN 的目标类似 CDN，但服务对象不是静态文件或视频，而是具有模型、Tokenizer、Adapter、KV Layout、并行配置和生命周期约束的 KVCache 资源。

KDN 向上为 Scheduler、Proxy、Instance 和管理工具提供统一的 KVCache 基础设施能力：

- 全局命名和目录；
- 兼容性判断；
- 节点、区域和拓扑管理；
- CacheArtifact 定位；
- Replica 放置、复制、迁移、预热、Pin、清理和失效；
- 网络源选择、传输计划、带宽和队列治理；
- 多节点、多区域和多层级 KVCache 分发；
- 运行状态、命中价值、成本和故障观测；
- v1/Legacy 和 LMCache 版本兼容。

KDN 向下通过 LMCache 公开接口、Adapter、Plugin、Coordinator、SDK、Metrics 和 Events 操作各节点的 KVCache Runtime。KDN 不重新实现 LMCache 的节点内 Token Database、Chunk/Hash/Key、KV Layout、Serde、L1/L2 StorageManager、锁或设备内存管理。

### 0.1 v1 数据路径

单个 Instance 内部的高频本地读写仍保持：

```text
vLLM == LMCacheMPConnector == local LMCache MP == local L1 / L2
```

跨节点或跨区域的 KVCache 分发由 KDN Distribution Plane 组织：

```text
source LMCache Runtime
        == KDN Transfer Session / transport
        == target LMCache Runtime
```

KDN Control Plane 不逐 Chunk 执行策略计算，但 KDN Distribution Plane 可以承载、代理或委托实际网络传输。

### 0.2 Runtime Profile 政策

- `v1`：所有新功能的唯一开发路线。
- `legacy`：保留旧启动、Redis scan/dump/restore/inject、旧请求和实验流程；功能冻结。
- `auto`：仅用于启动期迁移发现，必须解析并冻结为一个明确 Profile。
- v1 请求不得静默进入 Legacy 写路径。
- Legacy 数据进入 v1 必须经过显式迁移、导入或重建。

### 0.3 不可违反的设计原则

- KDN 是网络级 KVCache 基础设施，不是 Redis 的别名。
- KDN 可以管理和传输 KVCache，但不复制 LMCache 的节点内数据模型和存储引擎。
- KDN 的稳定身份使用 Knowledge、Artifact、Replica、Node 和 Transfer，不使用原始 Redis Key 或 LMCache 私有 Python 对象。
- 物理 KV 数据格式由 `LMCacheCompatibilityProfile` 和 `CacheDataProfile` 约束。
- 跨节点传输必须校验模型、Tokenizer、Adapter、Layout、DType、并行配置、Chunk/Serde Profile 和内容完整性。
- 未知能力不得默认视为支持。
- Control Plane、Distribution Plane 和节点内 Runtime 必须可以独立扩展和独立故障。
- 所有网络分发任务必须可观测、可取消、可重试、可限速并具有幂等语义。
- Proxy 不复制全局物理 Chunk Index；全局目录由 KDN 维护，节点内物理索引由 LMCache 维护。

## 1. CDN 类比与 KDN 术语

KDN 借鉴 CDN 的基础设施模式，但不能直接照搬静态对象缓存语义。

| CDN 概念 | KDN 对应概念 |
|---|---|
| Content Object | CacheArtifact |
| Origin | Artifact Producer、Durable L2 或指定 Origin Node |
| Edge POP | KDN Edge Node / LMCache Endpoint |
| Cache Replica | CacheReplica |
| Cache Fill | Distribution / Prefetch / Replication |
| Purge | Invalidate / Clear |
| Routing | Compatible Source Selection |
| TTL | Artifact 生命周期、Replica Lease 和 Observation TTL |
| Bandwidth Control | Transfer Admission、Rate Limit 和 Queue |
| Cache Hit | Token Coverage、Remote Availability 和 Local Hit |
| Regional Shield | Regional KDN Node 或共享 L2 |

关键差异：

1. KVCache 只能在兼容 Runtime 之间复用；
2. Artifact 可能只覆盖 Token 区间，而不是完整对象；
3. 传输后还需要 LMCache Load、注册或物化；
4. 节点内命中与网络可用是两个不同状态；
5. 清理和失效必须同时考虑知识版本、模型版本和布局变化；
6. 网络距离、带宽、GPU 计算节省和 TTFT 共同决定分发价值。

## 2. 总体架构

### 2.1 图例

```text
==  请求、KVCache 或大块数据传输路径
--  控制、管理、策略或观测 API
|   组件内部包含或层级归属
```

### 2.2 CacheRoute 与 KDN 集群

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

### 2.3 三条路径

```text
Inference Path
Client == Scheduler == Proxy == Instance == vLLM

Local KV Path
vLLM == LMCacheMPConnector == local LMCache MP == local L1 / L2

KDN Distribution Path
source LMCache == KDN Node/Transport == target LMCache
```

控制关系：

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

## 3. KDN 的正式定义

### 3.1 KDN Cluster

KDN Cluster 是多个控制节点、边缘节点、区域节点和 LMCache Endpoint 组成的 KVCache 网络基础设施。

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

### 3.2 KDN Control Plane 负责

- Artifact 全局命名、版本和兼容性；
- 节点、区域、网络和存储拓扑；
- 逻辑 Replica 目录和期望状态；
- 选择 Origin、Source、Target 和中继路径；
- 放置、复制、迁移、预热、Pin、清理和重建策略；
- 配额、租户、授权、审计和生命周期；
- 传输任务的幂等、优先级、Deadline、取消和重试策略；
- 维护短期物理观测并生成 RouteDecision；
- 根据命中价值、带宽、TTFT 和计算节省做治理决策。

### 3.3 KDN Distribution Plane 负责

- 在兼容节点之间建立 TransferSession；
- 支持 Pull、Push、Relay 和委托式传输；
- 选择实际传输协议或后端；
- 传输大块 KVCache 或可解析的 transport reference；
- 断点续传、重试、校验、限速、背压和取消；
- 将完成的数据发布到目标 LMCache Runtime；
- 上报实际字节、Token 覆盖、带宽、延迟和错误；
- 在节点或链路故障时切换 Source 或回退重建。

### 3.4 LMCache Runtime 负责

- Token 分块、Hash、Chunk Key 和物理 KV Object；
- KV Layout、DType、Serde 和设备相关格式；
- 节点内 L1/L2 驻留和 Adapter 级联；
- Store、Retrieve、Prefetch、Pin、Unpin、Clear；
- 节点内锁、容量、Quota 和淘汰执行；
- 实际 hit-token、remote-read、Metrics 和 Events；
- 将传入 Artifact 注册或物化为可供 vLLM 使用的本地缓存。

### 3.5 权威边界

| 信息 | 权威来源 |
|---|---|
| KnowledgeObject、Artifact 语义和版本 | KDN Control Plane |
| Artifact 兼容性和 Data Profile | KDN Control Plane |
| Node、Region 和拓扑 | KDN Control Plane |
| 逻辑 Replica 期望状态 | KDN Control Plane |
| 物理 Replica 是否存在 | LMCache Runtime 观测 |
| 全局 Replica Directory | KDN 基于节点观测维护 |
| 节点内 Chunk Index 和 KV 字节 | LMCache Runtime |
| TransferSession 和网络结果 | KDN Distribution Plane |
| Instance 实际命中 Token | Instance 侧 LMCache |
| 请求等待、计算释放和回退 | Proxy |
| 全局请求与资源池选择 | Scheduler |

KDN 可以权威维护“应该存在的 Replica”和“已确认存在的 Replica 目录”，但不得伪造或永久缓存过期的物理存在性。每个确认状态都必须包含来源、Generation、时间和 TTL。

## 4. KDN API 与分发协议

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

Control API 不携带大块 KVCache。Distribution API 可以直接传输数据，也可以返回由双方支持的 transport reference。

### 4.3 API 映射图

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

跨节点数据路径：

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

### 4.4 稳定协议不得暴露

```text
Redis password
raw Redis key
LMCache private Python class
unversioned internal Chunk Key
device pointer
private serialized object without Data Profile
backend-specific credentials in domain objects
```

后端凭据只能通过 Secret Reference 或节点本地配置传递。

## 5. 核心对象

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

CacheArtifact 是可分发 KVCache 资源的稳定逻辑身份，不直接等于某个节点内 Chunk Key。

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

推荐 `node_role`：

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

`desired_state` 由 KDN 权威维护，`observed_state` 来自节点和 LMCache Runtime。

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

## 6. LMCache 集成与兼容

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

### 6.2 Gateway 结构

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

### 6.3 启动期能力发现

每个 v1 KDN Node 启动时必须：

1. 查询 LMCache 版本、Build ID 和运行模式；
2. 查询 Connector、Config、Tier 和已加载 Adapter；
3. 探测 HTTP Route、SDK、Metric、Event 和 Transport；
4. 构建不可变 CapabilitySnapshot；
5. 验证 Chunk Size、Hash、Layout、DType、Serde 和 Data Profile；
6. 生成 Node Generation；
7. 注册到 KDN Control Plane；
8. 未知能力标记为 `unsupported` 或 `unknown`。

### 6.4 传输兼容门禁

KDN 只能在以下条件满足时直接分发 Artifact：

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

不满足时执行以下之一：

```text
reject reuse
select another replica
migrate
transcode through an explicit supported adapter
rebuild
fall back to text compute
```

不得静默复用未知或不兼容数据。

## 7. 版本迭代总览

| 版本 | 主题 | 主要交付 |
|---|---|---|
| v0.1.10 | 契约与观测基线 | RuntimeProfile、Artifact、Node、Replica、Operation、Queue、Trace、Legacy 投影 |
| v0.1.11 | KDN Control Plane 与全局目录 | Artifact Directory、Node Registry、Topology、Desired/Observed State |
| v0.1.12 | KDN Distribution Plane MVP | Node Agent、TransferSession、单源到单目标分发、LMCache 发布 |
| v0.1.13 | 多节点复制与源路由 | Replica Placement、Source Selection、重试、恢复、第二 Transport/Profile |
| v0.1.14 | Proxy KVCache Manager | RouteDecision、短期 Instance View、Single-flight |
| v0.1.15 | 分发与计算队列 | ExecutionGraph、Transfer Queue、Compute Fast Path |
| v0.1.16 | 网络与计算并行 | Work-conserving Pipeline、带宽治理、Overlap Benchmark |
| v0.1.17 | 集群稳定与普适性 | Admission、Backpressure、Fairness、Aging、Failover |
| v0.1.18 | KDN 资源治理策略 | Placement、Replication、Prefetch、Pin、Purge、价值模型 |
| v0.1.19 | 多知识块分发与融合 | 并行定位、分段传输、选择性重计算、质量回退 |
| v0.2.0 | KVCache 分发基础设施基线 | 多节点 KDN、稳定协议、跨 LMCache Profile、完整实验闭环 |

## 8. 分版本规划

### v0.1.10：契约与观测基线

目标是冻结后续集群化需要的稳定词汇：

- RuntimeProfile；
- LMCacheCompatibilityProfile；
- Instance Capability；
- CacheArtifact；
- KDNNode；
- CacheReplicaRecord；
- CacheOperationTask；
- QueueWork；
- Trace Source 和阶段；
- Legacy 只读投影。

验收：

- 核心对象不包含 KV 字节、明文凭据、原始 Redis Key 或 LMCache 私有类；
- Desired State 和 Observed State 明确分离；
- 节点、Replica、Operation 和 Queue 状态转换可验证；
- v1 和 Legacy Profile 不会在请求中动态切换；
- CPU-only 测试不依赖外部集群。

### v0.1.11：KDN Control Plane 与全局目录

主要步骤：

1. 实现 KnowledgeObject 和 CacheArtifact 目录；
2. 实现 KDN Node/Region/Topology Registry；
3. 建立 Artifact 到 Replica 的全局目录；
4. 区分期望 Replica 和已确认 Replica；
5. 建立兼容性门禁；
6. 建立 Node Generation 和 Observation TTL；
7. 提供 LocateReplicas 和 GetRouteDecision；
8. Scheduler 只读取粗粒度资源摘要。

验收：

- 同一 Artifact 可以有多个区域和节点 Replica；
- 过期观测不会被视为物理事实；
- 不兼容节点不会进入 Source Candidate；
- 目录不复制节点内 Chunk Index。

### v0.1.12：KDN Distribution Plane MVP

主要步骤：

1. 启动独立 KDN Node Agent；
2. 实现 OpenTransferSession 和单源到单目标传输；
3. 实现 Direct、Shared Backend 或 Mock Transport 中至少一种真实路径；
4. 通过 LMCache Gateway 从 Source 导出或引用 Artifact；
5. 在 Target LMCache 中 Publish/Prefetch/Load；
6. 实现校验、幂等、超时、取消和基础重试；
7. 上报实际字节、Token 覆盖和耗时；
8. 失败可回退重建或文本计算。

验收：

- 一个节点上的兼容 Artifact 可以分发到另一个节点；
- 传输后目标 LMCache 能报告可用或实际命中；
- Control API 不承载大块 Payload；
- 替换 Transport 不修改 Artifact 和 Route API。

### v0.1.13：多节点复制、源路由与恢复

主要步骤：

1. 支持多个 Source Candidate；
2. 根据区域、带宽、负载、健康和兼容性选源；
3. 支持一个 Source 到多个 Target；
4. 支持 Relay 或共享 L2；
5. 增加第二种 Transport 或 LMCache Profile；
6. 支持断点续传、Source Failover 和 Transfer Recovery；
7. 建立 Placement/Replication 状态机；
8. 建立跨版本 Compatibility Matrix；
9. 不兼容时迁移、重建或拒绝。

验收：

- Source 失败时可切换兼容 Replica；
- 多节点复制具有幂等性；
- KDN 至少验证两种 Transport/Profile 配置；
- LMCache 接口变化只修改 Gateway Adapter。

### v0.1.14：Proxy KVCache Manager

- 维护短期 Instance Cache View；
- 调用 KDN 获取 RouteDecision；
- 区分 REMOTE_AVAILABLE、TRANSFERRING、PUBLISHED、LOCAL_AVAILABLE、STALE 和 FAILED；
- 同 Artifact/Target 实现 Single-flight；
- 将 DistributionPlan 编译进 CachePlan；
- Instance、Node 或 Profile Generation 变化时失效。

### v0.1.15：分发与计算队列

- ExecutionGraph 增加 KDN_ROUTE、KDN_TRANSFER 和 CACHE_PUBLISH；
- 分离 Control、Transfer、Cache Load 和 Compute 并发域；
- 定义 Share Key、优先级、Deadline、带宽预算和回退；
- 文本任务保留 Compute Fast Path；
- Scheduler 不参与逐 Transfer 调度。

### v0.1.16：网络与计算并行

- KVCache 传输与其他请求 Prefill/Decode 重叠；
- 根据网络和 GPU 状态动态调整并发；
- 支持 Work-conserving 调度；
- 增加 Network-Compute Gantt、Overlap Ratio 和 Saved Compute；
- 处理超时、取消和回退。

### v0.1.17：集群稳定与普适性

- Admission Control 和 Backpressure；
- 多租户配额和带宽治理；
- Fairness、Aging 和 Starvation Guard；
- Node/Region Failover；
- Transfer Storm 和 Cache Pollution 防护；
- 多模型、多 Instance、多 KDN Node、多带宽测试。

### v0.1.18：KDN 资源治理策略

策略输入：

- Artifact 热度和知识共现；
- Replica 区域分布；
- Source/Target 带宽和队列；
- LMCache 容量、命中和淘汰；
- Proxy 等待、TTFT 和 GPU Idle；
- 计算节省、传输成本和重建成本；
- Online 与 Background 负载。

策略输出：

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

每个决策必须有 Reason Code，并支持 Shadow、Replay 和受控启用。

### v0.1.19：多知识块分发与融合

- 一个请求解析多个 Knowledge Block；
- 并行 Resolve、Locate 和 Source Selection；
- 对不同 Artifact 并行建立 TransferSession；
- 支持 Full、Partial、Overlap 和 Reorder；
- 使用 LMCache Non-prefix、CacheBlend 或等价能力；
- 只重计算必要 Token；
- 质量失败或超时回退文本。

### v0.2.0：集成 KVCache 分发基础设施

v0.2.0 完成时应满足：

- KDN 以 Cluster 形式部署，至少包含 Control Plane 和多个 Node；
- Artifact 可以跨节点定位、传输、发布和清理；
- 至少验证两个 Node、两个 LMCache/Transport Profile；
- Source Selection、Replica Placement 和 TransferSession 可重复验证；
- Control Plane 与 Distribution Plane 独立扩展；
- 节点内数据语义继续由 LMCache 管理；
- Proxy 使用 KDN RouteDecision 和短期观测；
- 网络传输与计算可并行；
- 队列具备 Single-flight、背压、公平、取消、重试和回退；
- 支持至少两个知识块的并行分发和复用；
- v1 为默认，Legacy 保留最小兼容回归；
- 关键故障、升级和跨区域场景有可重复实验。

## 9. 生命周期与状态

### 9.1 Artifact 生命周期

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

### 9.2 Replica 状态

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

### 9.3 Transfer 状态

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

状态转换必须记录：

```text
source
generation
reason_code
observed_at
expires_at
trace_id
```

## 10. 观测与研究指标

### 请求指标

- TTFT P50/P95/P99；
- 吞吐和完成时间；
- 实际 hit-token；
- 远端复用 Token；
- 文本回退率；
- 计算节省时间。

### 分发指标

- Route Decision 延迟；
- Source Selection 命中率；
- Transfer Queue Wait；
- Transfer Setup Time；
- Bytes/Tokens Transferred；
- Effective Bandwidth；
- Resume 和 Retry 次数；
- Source Failover 次数；
- Integrity Failure；
- Publish/Load Time；
- Distribution Success Rate。

### 集群指标

- Artifact/Replica 数量；
- Region/Node 分布；
- Replica Freshness；
- Capacity 和 Quota；
- Eviction/Purge/Rebuild；
- Hotspot 和负载偏斜；
- Cross-region Traffic；
- Cache Pollution；
- Placement Policy 收益。

### 并行指标

- Network-Compute Overlap Ratio；
- GPU Idle Due to Cache Wait；
- Network Idle With Pending Work；
- Head-of-line Blocking；
- Single-flight 节省任务和字节；
- Work-conserving 利用率。

## 11. 测试与实验要求

### 单元测试

- ID、Fingerprint 和状态转换；
- Artifact 兼容性；
- RouteDecision；
- Placement/Replication Policy；
- TransferSession 幂等；
- Resume、Retry、Cancel；
- Observation TTL 和 Generation；
- Runtime Profile 与 Capability Snapshot；
- Secret 和私有字段拒绝。

### 组件测试

- KDN Control Plane；
- KDN Node Agent；
- Mock LMCache Gateway；
- Mock Transport；
- MP HTTP/Coordinator Gateway；
- 两个 Node 和两个 Transport/Profile；
- Node 重启和 Generation 变化；
- Source Failover；
- Publish 后的 LMCache 可用性。

### 端到端测试

- vLLM + LMCache + Proxy + KDN Control + 两个 KDN Node；
- 单节点本地命中；
- 跨节点分发；
- 多 Target 复制；
- Source 故障恢复；
- 带宽受限和队列背压；
- 网络与计算并行；
- 多知识块；
- Profile 不兼容和文本回退；
- Legacy 最小回归。

### 实验复现

每次实验保存：

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

## 12. 非目标

v0.2.0 不要求：

- 重新实现 LMCache Token Database、Allocator、Serde 或 Paged KV；
- 固化某一种网络传输协议；
- 把原始 Redis Key 作为 KDN 全局身份；
- 在 Scheduler 中执行逐 Chunk 传输调度；
- 在 Control Plane 中同步搬运所有 KV 数据；
- 对不兼容 KVCache 做隐式转换；
- 一次性实现全球多区域生产级一致性；
- 替代 vLLM 的模型执行和引擎调度。

## 13. 长期演进

达到 v0.2.0 后，KDN 的长期方向是：

1. 从单集群演进为多区域 KVCache Distribution Network；
2. 从中心目录演进为分层目录和区域自治；
3. 从简单 Source Selection 演进为延迟、成本和 SLO 感知路由；
4. 从单次复制演进为持续热度驱动的 Replica Placement；
5. 从固定 Transport 演进为 NIXL、Mooncake、RDMA、对象存储和共享 L2 的统一选择；
6. 从单租户演进为配额、隔离和公平治理；
7. 从 Artifact 级分发演进为 Token Segment 和多知识块组合分发；
8. 与 LMCache 的 MP、Coordinator、Adapter、Transport 和 Observability 能力持续对齐；
9. 保持 KDN 网络基础设施与 LMCache 节点内 Runtime 的清晰边界。

CacheRoute 的长期核心是：

> **把 KVCache 从单机运行时资源提升为可在网络中命名、定位、分发、复制、治理和观测的基础设施资源。**
