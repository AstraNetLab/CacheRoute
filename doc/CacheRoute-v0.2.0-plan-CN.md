# CacheRoute v0.2.0 演进规划

> 状态：规划草案  
> 当前发布基线：v0.1.9  
> 当前实施方式：从 v0.1.10 Issue 路线重新推进，不继承已关闭 PR 的实现  
> 目标版本：v0.2.0  
> 核心底座：vLLM + LMCache  
> 核心定位：KDN 独立知识型远端缓存服务器、LMCache 演进兼容层、Proxy 多资源执行编排、知识型缓存策略与多知识块复用

## 0. 本轮规划结论

本规划确立以下长期边界：

> **KDN Server = Knowledge Control Plane + LMCache-Compatible Remote Cache Serving Plane。**

KDN 是可独立部署、可独立扩展和可被 Scheduler 管理的服务器实体。它不是 Redis 的别名，也不是 CacheRoute 自行实现的一套通用 KVCache Store。

KDN 同时承担两类职责：

1. 面向 CacheRoute 的知识语义、Artifact、策略、维护和观测管理；
2. 面向 LMCache 的远端 KVCache 检索、保存、加载和异步任务服务。

物理 KVCache 的分块、序列化、传输、存储后端和底层淘汰机制应尽可能复用或对齐 LMCache 的公开能力。KDN 的差异化价值位于知识语义和策略层，而不是重新实现 Redis、Mooncake、S3、NIXL 或文件系统缓存引擎。

### 0.1 当前 Issue 状态

| 项目 | 规划处理 |
|---|---|
| #138 / PR #143 | 已完成，保留 Instance Capability Fingerprint |
| #139 | 重新按 Issue 实施，定义存储中立的核心状态和逻辑对象 |
| #140 | 调整为 KDN 双接口协议与 LMCache Compatibility Profile |
| #141 | 增加 KDN Serving、LMCache Profile 和 Provider 来源观测 |
| #142 | 增加跨 LMCache 版本/接口 Profile 的契约与回归验证 |
| 已关闭 PR | 不作为新实现迁移基础，不在本规划讨论 |

### 0.2 不可违反的设计原则

- KDN 必须是独立服务器，但不能把某一种底层存储实现固化为 KDN 身份。
- Redis 只可以作为早期验证后端或 Legacy 兼容路径。
- KDN 对 LMCache 暴露稳定的远端缓存服务语义，而不是暴露 Redis Key、目录或私有序列化。
- KDN 内部 Provider 层应与 LMCache 公开扩展接口对齐。
- CacheRoute 不复制 LMCache 的 Chunk Index、内存分配器、Serde 或块级传输实现。
- LMCache 版本变化不能直接传播到 KDN Knowledge API、Proxy CachePlan 和 Scheduler。
- 所有版本和能力差异必须通过 Compatibility Profile 与 Capability Negotiation 表达。
- 当某项 LMCache 能力缺失或语义不兼容时，必须返回 `unsupported`、`incompatible` 或执行明确回退，不能静默模拟。

## 1. KDN Server 的正式定位

### 1.1 定义

KDN Server 是面向知识复用的远端缓存服务。它接收 Instance 侧 LMCache 发起的 Lookup、Store、Load/Retrieve 等调用，并为 CacheRoute 提供知识目录和策略控制。

KDN 不仅是一个数据后端。普通远端缓存后端只关心 Key 和 Value，而 KDN 还理解：

- 缓存对应哪个 KnowledgeObject；
- 知识内容和版本；
- 模型、Tokenizer、Adapter 和 KV Layout 兼容性；
- CacheArtifact 的构建和失效关系；
- 多知识块共现；
- 缓存价值、Pin、预取和保留意图；
- 请求的网络代价、计算节省和队列影响；
- 质量保护和文本回退。

### 1.2 三层结构

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
|   - async task status
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

三层分别解决：

- **Knowledge Control Plane**：为什么缓存存在、对应什么知识、应该采取什么策略；
- **Remote Cache Serving Plane**：向 LMCache 提供什么远端缓存服务；
- **Provider Compatibility Layer**：当前 LMCache 版本和具体后端如何完成操作。

### 1.3 两个外部接口

#### CacheRoute-facing Knowledge Management API

由 Scheduler、Proxy、管理工具和 KDN 策略模块调用：

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

该接口只交换知识、策略、逻辑引用、观测摘要和任务状态，不传输大块 KVCache。

#### LMCache-facing Remote Cache Serving API

由 Instance 侧 LMCache 或其插件调用：

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

该接口必须：

- 与具体 Backend 无关；
- 支持同步和异步完成模型；
- 支持批量操作；
- 明确锁、Lease、取消和幂等语义；
- 返回命中范围、来源、耗时和结构化错误；
- 不要求 LMCache 理解 KnowledgeObject 和上层策略。

### 1.4 KDN 不是 Redis

KDN 的首个可运行版本可以使用 Redis，但以下内容不得进入稳定协议：

- Redis URL；
- Redis 密码；
- Redis 内部 Key；
- Redis Pipeline 细节；
- Redis 作为 Replica 身份；
- Redis 特有的 TTL 或事务语义。

应通过统一 Provider 描述表示：

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

后续可替换为 Mooncake、NIXL、S3、文件系统、对象存储、原生连接器或其他 LMCache 支持/扩展的后端，而不修改 KDN Knowledge API。

## 2. KDN 与 LMCache 的关系

### 2.1 数据路径关系

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

Instance 侧 LMCache 将 KDN 视为可检索的远端缓存服务。KDN 将上层知识标识映射为 Provider 可执行的物理缓存引用。

KDN 不要求所有 LMCache 请求都经过复杂策略计算。数据热路径必须与知识策略路径解耦：

- 常规 Lookup/Load 走快速 Serving Path；
- 策略变化、维护、重建和放置通过异步 Control Path；
- Serving Path 可以使用控制平面下发的版本化快照和策略结果。

### 2.2 权威边界

| 信息 | 权威来源 |
|---|---|
| KnowledgeObject 内容、版本和语义 | KDN |
| KnowledgeObject 到 CacheArtifact 的关系 | KDN |
| Artifact 兼容性和失效原因 | KDN |
| 期望 Pin、预取、保留和放置意图 | KDN Policy |
| LMCache 客户端能力和接口 Profile | LMCache Compatibility Layer |
| 物理 KV 数据、布局、Serde 和块索引 | LMCache/Provider |
| 物理对象是否存在和操作是否完成 | Provider 运行时观测 |
| Instance 本地实际命中 Token | Instance 侧 LMCache |
| 请求等待、绕行和计算释放 | Proxy |
| 全局 Proxy/KDN 资源池选择 | Scheduler |

KDN 可以缓存物理观测，但必须记录：

```text
observation_source
observed_at
expires_at
provider_generation
lmcache_profile_id
confidence
```

### 2.3 Provider 对齐原则

KDN Provider 不应自行发明与 LMCache 无关的 KV 数据抽象。优先顺序为：

1. 使用 LMCache MP L2 Adapter 或其公开等价接口；
2. 对高性能原生后端使用 `native_plugin` 或公开原生连接器契约；
3. 对外部分布式存储使用当前推荐的 Remote Storage Plugin；
4. 仅为兼容旧部署保留进程内 Remote Connector、Controller 或旧配置适配；
5. LMCache 缺少所需能力时，优先向 LMCache 扩展机制贡献 Provider；
6. 只有明确证明无法通过 LMCache 扩展实现时，才讨论 CacheRoute 特有的数据机制。

## 3. LMCache 演进兼容性

LMCache 正从进程内模式向独立 MP Server、多级 L1/L2、异步 Store/Lookup/Load 和插件化 Adapter 演进。CacheRoute 不能把某一个时间点的 Python 类、模块路径或 HTTP Endpoint 当成长期架构。

### 3.1 兼容层目标

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

兼容层必须隔离：

- LMCache 版本号；
- 运行模式；
- Request/Response 类型；
- Adapter 类路径；
- ZMQ/HTTP/进程内调用差异；
- 异步完成机制；
- 锁和 Unlock 语义；
- Key/Hash 和 Layout 差异；
- 事件与观测格式；
- 已弃用配置和接口。

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

推荐的 `integration_family`：

```text
mp_l2_plugin
mp_native_plugin
remote_storage_plugin
controller_api
in_process_legacy
mock
```

Profile 状态：

```text
experimental
validated
default
deprecated
unsupported
```

### 3.3 握手和能力协商

KDN 与 LMCache Connector 建立连接时必须交换：

- KDN Serving Protocol Version；
- LMCache Compatibility Profile；
- 支持操作；
- 最大 Batch；
- Key/Layout/Serde Profile；
- 同步或异步完成方式；
- Lock/Unlock/Lease 语义；
- Event/Metric 支持；
- Provider Generation；
- 推荐的降级方式。

任何不确定能力不得默认视为支持。

### 3.4 公共接口优先

- 只在稳定适配层中引用 LMCache 公共接口；
- 不在 KDN Domain Model、Proxy Queue 或 Scheduler 中导入 LMCache 私有类；
- 私有或实验接口必须位于独立 Adapter，带明确版本门禁；
- LMCache 接口更名时只替换 Adapter，不修改 KnowledgeObject、CachePlan 或 ExecutionGraph；
- 配置中不直接把已弃用的 `remote_url`、旧进程内模式或某个模块路径作为 KDN 稳定字段。

### 3.5 数据兼容与升级

Artifact 身份必须包含或关联：

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

升级 LMCache 时：

1. 先比较 Compatibility Profile；
2. 可直接读取时复用；
3. 只支持迁移时创建迁移任务；
4. 不兼容时重新构建 Artifact；
5. 未知时禁止静默复用并回退文本；
6. 保留旧 Profile 的观测和回滚窗口。

### 3.6 支持策略

每个 CacheRoute 版本应声明：

- 最低支持 LMCache 版本或能力 Profile；
- 默认验证版本；
- 最新实验验证版本；
- 已弃用 Profile；
- 已知不兼容组合；
- Compatibility Matrix；
- 升级和回退说明。

测试至少覆盖：

```text
baseline validated LMCache profile
latest validated LMCache profile
one deprecated/legacy profile
mock future profile with unknown capabilities
```

## 4. 总体角色边界

```text
Scheduler
- 选择 Proxy / KDN 资源池
- 使用知识和资源粗粒度摘要
- 不处理物理缓存 Key、块和传输任务

Proxy
- Resolve Knowledge
- 构建 CachePlan / FusionPlan / ExecutionGraph
- 维护短期 Instance Cache Observation
- 协调 KDN Serving、网络、Cache Load、Prefill 和 Decode
- 不建立权威 Block Index

KDN Knowledge Control Plane
- 知识、Artifact、策略和 Desired State 权威
- 维护 KDN Endpoint、Provider 和 LMCache Profile
- 生成维护和服务意图

KDN Remote Cache Serving Plane
- 接收 LMCache 远端缓存请求
- 执行快速 Lookup/Store/Load
- 返回结构化命中和任务结果
- 不在热路径运行复杂全局策略

KDN Provider Compatibility Layer
- 适配当前 LMCache 扩展契约和具体 Provider
- 隔离版本、配置和完成模型差异

LMCache
- Instance 侧缓存客户端、L1/L2 管理和 vLLM Connector
- 定义公开扩展接口和数据布局能力
- 提供实际命中和加载观测

vLLM
- 模型执行、Paged KV 和引擎内部调度
```

## 5. v0.2.0 目标架构

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

关键数据流：

```text
Instance LMCache
    -> KDN Lookup
    -> KDN Provider Lookup
    -> KDN 返回 coverage / task reference
    -> LMCache Load/Retrieve
    -> Instance 确认实际命中
    -> Proxy 释放依赖计算
```

## 6. 核心对象

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

Artifact 是知识和兼容环境下的逻辑物化身份，不保存 KV 字节。

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

Replica 是短期观测/引用，不是 CacheRoute 自有物理副本实现。

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

采用第 3.2 节定义。

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

资源类型：

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

## 7. 版本迭代总览

| 版本 | 主题 | 主要交付 |
|---|---|---|
| v0.1.10 | 契约与观测基线 | Capability、核心状态、KDN 双接口词汇、LMCache Profile、Trace |
| v0.1.11 | KDN Knowledge Control Plane | KnowledgeObject、Artifact Catalog、Desired/Observed State |
| v0.1.12 | 独立 KDN Serving Plane MVP | LMCache-facing Server、Provider SPI、Redis/Mock 验证 |
| v0.1.13 | 多 Provider 与 LMCache 演进兼容 | MP/Profile 适配、兼容矩阵、第二后端、恢复 |
| v0.1.14 | Proxy KVCache Manager | LMCache/KDN 观测驱动的 Instance View、Single-flight |
| v0.1.15 | 注入与计算队列模型 | ExecutionGraph、资源队列、Compute Fast Path |
| v0.1.16 | 网络与计算并行 | 工作守恒流水线、Overlap Benchmark |
| v0.1.17 | 队列稳定与普适性 | 准入、背压、公平、Aging、自适应并发 |
| v0.1.18 | KDN 知识型策略 | Pin/Prefetch/Placement/Clear 意图、价值模型、Replay |
| v0.1.19 | 多知识块非前缀融合 | 并行检索、选择性重计算、质量回退 |
| v0.2.0 | 集成研究基线 | 稳定接口、跨版本兼容、完整实验闭环 |

## 8. 分版本规划

## v0.1.10：契约与观测基线

### 目标

在不实现完整 KDN Server 的前提下冻结后续所需的稳定词汇：

- Instance Capability；
- CacheArtifact 和 CacheReplicaObservation；
- KDNServingEndpoint；
- KDNServingTask；
- LMCacheCompatibilityProfile；
- QueueWork；
- Trace Source 和阶段；
- Legacy 兼容映射。

### 验收

- #138 已完成的 Capability 保持兼容；
- 核心对象不包含 KV 字节、Redis 私有 Key、连接凭据和 LMCache 私有类；
- KDN Knowledge API 与 LMCache-facing Serving API 可区分；
- LMCache Profile 可以表达 MP、Plugin、Legacy 和未知能力；
- Trace 区分 KDN、Provider、LMCache、Proxy 和 vLLM 来源；
- CPU-only 测试不要求外部 vLLM、Redis 或 LMCache 集群。

## v0.1.11：KDN Knowledge Control Plane

### 主要步骤

1. 实现 KnowledgeObject 和版本管理。
2. 一个 KnowledgeObject 对应多个 CacheArtifact。
3. Artifact 使用 Capability 和 LMCache Data Profile 判断兼容性。
4. 实现 Desired State 与 Provider Observation 分离。
5. 建立 KDN Endpoint 和 Provider Registry。
6. 支持知识到 KDN Serving Namespace/Location Reference 的映射。
7. Scheduler 只读取粗粒度知识可用性。
8. Legacy `kv_ready` 映射为 `compatibility=unknown`。

### 验收

- 同一知识支持多模型、多 Adapter 和多 LMCache Profile；
- 控制面不访问或复制物理 KV 数据；
- Provider 观测过期后不会继续视为权威；
- Redis 不出现在稳定 Knowledge Domain Model 中。

## v0.1.12：独立 KDN Remote Cache Serving Plane MVP

### 主要步骤

1. 启动独立 KDN Server。
2. 实现 Serving Handshake 和 Capability Negotiation。
3. 实现 Lookup、Store、Load/Retrieve 和 TaskStatus 最小集合。
4. 定义 Provider SPI，与 LMCache 公开 L2/Remote Storage 语义对齐。
5. 实现 Mock Provider。
6. 实现第一个真实 Provider；可以使用 Redis，但仅作为 Provider。
7. 实现 Instance-side LMCache KDN Connector/Adapter。
8. 数据热路径不依赖复杂策略查询。
9. 记录实际字节、命中范围、队列和操作时间。

### 验收

- LMCache 可把 KDN 当作远端缓存服务；
- KDN Server 与具体 Provider 解耦；
- 替换 Mock/Redis 不修改 Serving Protocol；
- Redis Key 和凭据不进入 CacheRoute API；
- 失败可回退文本计算。

## v0.1.13：多 Provider 与 LMCache 演进兼容

### 主要步骤

1. 优先支持 LMCache MP L2 Plugin Profile。
2. 支持至少一个兼容 Profile，例如 Remote Storage Plugin 或 Legacy。
3. 增加第二种真实 Provider，证明不绑定 Redis。
4. 建立 Compatibility Matrix 和 Profile Conformance Suite。
5. 支持不同 LMCache Profile 同时注册。
6. 实现 Profile 升级、降级和弃用状态。
7. 实现 Provider generation、重连和任务恢复。
8. 对 Key/Layout/Serde 不兼容执行迁移或重建。
9. 增加最新验证 LMCache Profile 的周期性检查流程。

### 验收

- KDN 至少通过两种 Provider 配置运行；
- MP Profile 是默认演进方向；
- 旧 Profile 可以明确兼容或拒绝；
- LMCache 接口变化只需修改 Compatibility Adapter；
- 不兼容升级不会静默复用旧 Artifact。

## v0.1.14：Proxy KVCache Manager

### 主要步骤

1. 建立 Instance Cache Observation View。
2. 数据来源包括 KDN Lookup、LMCache 事件、Load 结果和实际命中。
3. 所有观测包含时间、来源、Profile、Generation 和 TTL。
4. 状态包括 UNKNOWN、REMOTE_AVAILABLE、PREPARING、LOCAL_AVAILABLE、STALE、FAILED。
5. 同 Artifact/Instance 实现 Single-flight。
6. Instance、KDN 或 Provider generation 变化时失效。
7. Proxy 不复制 Provider Chunk Index。

### 验收

- Proxy 能区分 KDN 可用、Provider 命中、正在加载和 Instance 本地可用；
- 过期观测返回 UNKNOWN；
- 同一准备任务只执行一次；
- LMCache Profile 变化会使相关观测失效。

## v0.1.15：知识注入与计算队列模型

- CachePlan 编译为 ExecutionGraph；
- 独立 CONTROL、KDN_LOOKUP、KDN_SERVE、NET_KV、CACHE_LOAD、PREFILL、DECODE 和 FUSION 队列；
- 纯文本和本地命中使用 Compute Fast Path；
- 依赖、引用、取消和事件唤醒统一管理；
- 记录每个节点的等待和执行原因。

## v0.1.16：网络 KV 与纯计算并行

- KDN Lookup/Load 与其他请求 Prefill/Decode 并行；
- 每 KDN Endpoint、Provider、链路和 Instance 建立独立时间线；
- 多知识块可在不同 Provider/Endpoint 并行；
- 测量 Overlap Ratio、GPU Cache-wait Idle、Network Idle 和 Pipeline Makespan；
- 对比串行、text_bypass 和完整并行。

## v0.1.17：队列普适性和稳定性

- 分层准入和背压；
- 优先级、Aging、Deadline Hint 和防饥饿；
- 大任务分片/让行；
- 自适应 KDN/Network/Load 并发；
- KDN、Provider、LMCache 和 Instance 故障回退；
- 策略插件不绕过状态机；
- 不引入 Pareto 或学习型全局调度。

## v0.1.18：KDN 知识型缓存策略

KDN 策略输出：

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

物理执行由当前 Provider/LMCache Profile 完成。

研究：

- 知识价值；
- 多 Provider 容量和成本；
- Pin、预取和清理；
- 热点放置；
- 维护预算；
- 后台任务对在线请求的干扰；
- Trace Replay。

## v0.1.19：多知识块非前缀融合

- 有序 Knowledge Block 和 Prompt Layout；
- 多 Artifact 和 KDN Candidate 查询；
- 完全、部分、非前缀、重叠和 Miss 分类；
- Coverage Map；
- FusionPlan 编译到 ExecutionGraph；
- 多块并行 KDN Lookup/Load；
- LMCache 非前缀复用或 CacheBlend；
- 选择性重计算和质量保护；
- 文本稳定回退。

## v0.2.0：集成、稳定与研究基线

### 发布标准

- KDN 是独立服务器，并提供稳定双接口；
- KDN 不绑定 Redis 或单一 LMCache 模式；
- 至少验证两个 Provider；
- 至少验证 baseline 和 latest 两个 LMCache Profile；
- MP 是默认 Profile，Legacy 有明确弃用策略；
- Knowledge Control Plane 与 Serving Hot Path 可独立扩展；
- Proxy 使用短期观测而非权威 Block Index；
- 网络 KV 与纯计算可并行；
- 队列具备 Single-flight、背压、公平、取消和回退；
- 支持至少两个知识块非前缀复用；
- KDN 有至少一种知识价值策略；
- 关键故障和升级场景有可重复测试；
- 文本、单知识和 Legacy 路径兼容。

## 9. LMCache 演进兼容测试框架

### 9.1 Contract Tests

同一套 KDN Serving Contract Tests 应运行于：

- Mock Profile；
- MP L2 Plugin Profile；
- Native Plugin Profile；
- Remote Storage Plugin Profile；
- Legacy Profile。

### 9.2 Compatibility Matrix

记录：

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

- LMCache 小版本升级；
- Adapter API 更名；
- Completion Model 变化；
- Key Format 变化；
- Layout/Serde 不兼容；
- Provider 重启；
- KDN 滚动升级；
- 新旧 LMCache 客户端同时连接；
- Profile 弃用；
- 降级回滚。

### 9.4 失败原则

- 未知能力不默认支持；
- 不兼容 Artifact 不加载；
- Provider 操作失败不破坏知识目录；
- KDN 控制面失败不应中断已授权数据任务；
- Serving Plane 失败时 Proxy 可回退文本；
- 升级失败可回到上一个 validated Profile。

## 10. 队列研究指标

- TTFT P50/P95/P99；
- 吞吐和完成时间；
- KDN Lookup Wait；
- KDN Serving Queue/Execution；
- Provider Lookup/Load；
- Network-Compute Overlap Ratio；
- GPU Idle Due to Cache Wait；
- Network Idle With Pending Work；
- Head-of-line Blocking Time；
- Single-flight 节省任务和字节；
- Profile 协商失败率；
- 不兼容重建和回退率；
- 多 Provider 负载分布；
- LMCache 升级前后结果一致性。

## 11. 状态边界

### KDN Knowledge Control Plane

权威维护知识、Artifact、策略、Desired State、Profile 支持和历史价值。

### KDN Serving Plane

权威维护 KDN 请求、Task 和当前服务结果，但不把历史任务结果永久当作 Provider 物理事实。

### Provider / LMCache Runtime

权威维护物理对象存在性、字节、布局、存储位置和底层操作结果。

### Proxy

维护请求级计划、短期 Instance/KDN 观测、共享准备任务和队列。

### Instance / vLLM

权威维护实际命中 Token、模型执行、Prefill 和 Decode 结果。

## 12. 测试与实验要求

### 单元测试

- Object ID 和状态转换；
- LMCacheCompatibilityProfile；
- Capability Negotiation；
- Protocol Version；
- Secret/Private Key 拒绝；
- Observation TTL；
- CachePlan/FusionPlan；
- ExecutionGraph；
- Single-flight；
- Trace 来源。

### 组件测试

- KDN Control 和 Serving 分离启动；
- Mock Provider；
- 两种 Provider；
- 两种 LMCache Profile；
- KDN Connector；
- Provider 重启；
- Profile 升级/降级；
- Queue 多资源并行。

### 端到端测试

- vLLM + LMCache + Proxy + KDN；
- 文本、单知识 KV、Hybrid；
- KDN 远端 Lookup/Load；
- 网络和计算并行；
- 多 Provider；
- 多知识块；
- KDN/Provider/LMCache 故障；
- Profile 不兼容和文本回退。

### 实验复现

保存：

- CacheRoute、vLLM、LMCache 和 Provider 版本；
- Compatibility Matrix 行；
- KDN Protocol/Profile；
- 工作负载；
- KDN 和 Provider 拓扑；
- 队列和策略参数；
- ExecutionGraph；
- 请求级结果；
- 汇总指标和异常。

## 13. 版本依赖

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

## 14. KDN 的长期演进趋势

达到 v0.2.0 后，KDN 的演进方向应是：

1. 从单体 KDN 演进为 Control Plane + 多 Serving Node；
2. 从单 Provider 演进为异构 Provider Federation；
3. 从静态 Profile 演进为自动 Capability Negotiation；
4. 从单区域演进为多区域 KDN；
5. 从粗粒度 Artifact 演进为多块、部分和组合知识缓存；
6. 从规则策略演进为 SLO 和不确定性感知策略；
7. 与 LMCache 新的 MP、Native、Transport 和 Observability 能力持续对齐；
8. 保持 Knowledge API、KDN Serving Protocol 和 Provider SPI 三层稳定隔离。

无论 LMCache 底层如何演进，CacheRoute 的长期核心始终是：

> **把知识语义、远端缓存服务、注入决策和计算队列编排连接为一个可观测、可扩展、可复现实验的闭环。**
