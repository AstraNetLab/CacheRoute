# CacheRoute v0.2.0 演进规划

> 状态：规划草案  
> 当前发布基线：v0.1.9  
> 当前开发基线：`v1`（vLLM 0.25.1 + LMCache 0.5.2 + PyTorch 2.11.0）  
> 兼容路径：`legacy` 保持可用但功能冻结  
> 目标版本：v0.2.0  
> 核心底座：vLLM + LMCache  
> 核心定位：KDN 知识控制平面、CacheRoute 缓存服务门面、LMCache 编排网关、Proxy 多资源执行编排、知识型缓存策略与多知识块复用

## 0. 本轮规划结论

本规划确立以下长期边界：

> **KDN Server = Knowledge Control Plane + CacheRoute Cache Service Facade + LMCache Orchestration Gateway。**

v1 的高频 KV 数据路径保持为：

```text
vLLM == LMCacheMPConnector == LMCache MP == L1 / L2 adapters
```

KDN 是独立部署、独立扩展并可被 Scheduler 管理的 CacheRoute 服务，但它不再作为 v1 默认的物理 KV 数据服务器，也不重复实现 LMCache 已有的 Token Database、Chunk/Hash/Key、L1/L2 StorageManager、Adapter 级联、Store/Prefetch Controller、Serde、锁、容量和淘汰。

KDN 的差异化价值位于：

1. KnowledgeObject、CacheArtifact 和知识版本语义；
2. 模型、Tokenizer、Adapter、KV Layout 和 LMCache Profile 兼容性；
3. Lookup、Prefetch、Pin、Clear、Rebuild 等知识级操作意图；
4. 多 LMCache Endpoint 的选择、幂等任务、审计、授权和回退；
5. LMCache 观测的归一化、TTL、置信度和请求价值反馈；
6. Proxy CachePlan、ExecutionGraph、队列以及网络—计算并行。

### 0.1 Runtime Profile 政策

- `v1`：所有新功能的唯一开发路线；使用 LMCache MP 和公开控制/观测接口。
- `legacy`：保留旧启动、Redis scan/dump/restore/inject、旧请求和实验流程；功能冻结。
- `auto`：仅用于启动期迁移发现；必须解析并冻结为一个明确 Profile。
- v1 请求不得静默进入 Legacy 写路径。
- Legacy 数据进入 v1 必须显式迁移或重建。

### 0.2 当前 Issue 状态

| 项目 | 规划处理 |
|---|---|
| #148 / PR #149 / PR #151 | 已完成 v1 环境、MP 启动与文档基线 |
| #138 / PR #143 | 已完成 Instance Capability Fingerprint |
| #139 | 定义 v1 Runtime、Artifact、LMCache Observation、Operation Task 和 Queue 状态 |
| #140 | 定义 KDN Cache Service Facade 与 LMCache Gateway 契约 |
| #141 | 增加 Gateway、Tier、Adapter、Queue 和 vLLM 统一观测 |
| #142 | 增加 v1/Legacy 双 Profile 与 Gateway 回归验证 |
| 已关闭 PR | 不作为 #139–#142 的实现迁移基础 |

### 0.3 不可违反的设计原则

- CacheRoute 不复制 LMCache 的 Token DB、Chunk Index、Allocator、Serde、锁或物理传输实现。
- KDN API 只交换知识语义、逻辑引用、操作意图、观测摘要和任务状态，不传输大块 KVCache。
- LMCache 版本和接口差异只允许出现在 Gateway Adapter、Factory 和 Capability Snapshot 中。
- Scheduler、Proxy、KnowledgeObject、CacheArtifact 和 ExecutionGraph 不导入 LMCache 私有类。
- Redis 只属于 Legacy 兼容边界或 LMCache 已加载的一个后端 Adapter，不是 KDN 身份。
- 未知能力不得默认视为支持；缺失能力返回 `unsupported`、`incompatible` 或明确回退。
- 物理状态以 LMCache Runtime 为权威；KDN 和 Proxy 只保存带来源、时间和 TTL 的观测。

## 1. CacheRoute、KDN、vLLM 与 LMCache 总体结构

### 1.1 图例

```text
==  高频请求或 KV 数据热路径
--  控制、管理、策略或观测 API
|   组件内部包含或层级归属
```

### 1.2 全局组件、数据路径和控制路径

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

该图表达两个不可混淆的事实：

1. `vLLM == LMCacheMPConnector == LMCache MP` 是 v1 的 KV 数据热路径；
2. KDN 通过 `--` 控制与观测接口管理 LMCache，不进入逐 Chunk 的高频数据传输路径。

## 2. KDN Server 的正式定位

### 2.1 三层结构

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

三层分别回答：

- **Knowledge Control Plane**：缓存为什么存在、对应什么知识、应采用什么策略；
- **Cache Service Facade**：CacheRoute 需要什么稳定的领域操作；
- **LMCache Orchestration Gateway**：当前 LMCache 版本和接口如何执行或观测该操作。

### 2.2 KDN 负责

- KnowledgeObject 内容、版本和语义；
- KnowledgeObject 到 CacheArtifact、Token Reference 的映射；
- Artifact 兼容性和失效原因；
- Desired State、Prefetch、Pin、Clear、Rebuild 意图；
- 多 Endpoint 粗粒度选择；
- CacheOperationTask 幂等、审计、授权、取消和回退；
- LMCache 观测的归一化、TTL 和置信度；
- 命中价值、计算节省和维护反馈。

### 2.3 LMCache 负责

- Token 分块、Hash、Chunk Key 和物理 KV Object；
- L1/L2 驻留和 Adapter 级联；
- Store、Retrieve、Prefetch、Pin、Unpin 和 Clear；
- Serde、Lock/Unlock、容量、Quota 和淘汰；
- 物理操作完成状态；
- 实际 hit-token、remote-read、Metrics 和 Events。

### 2.4 KDN 不是 Redis，也不是第二套 LMCache

以下内容不得进入稳定 KDN 领域模型：

```text
Redis URL / password / raw key
LMCache private Python class
LMCache internal Chunk Key
physical KV payload
private serialized object
physical chunk-index copy
```

Legacy Redis 操作必须收拢到 `LegacyCacheAdapter`。v1 新代码不在现有 Redis Injector 上继续叠加 Token Lookup、Tier、Adapter、Prefetch 或 Pin 逻辑。

## 3. KDN API 与 LMCache Gateway

### 3.1 API 分层与映射结构图

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

### 3.2 接口映射规则

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

稳定参数只使用：Knowledge ID、Artifact ID、Token 序列或 Token Reference、Instance Capability、LMCache Endpoint ID 和逻辑 Operation ID。

### 3.5 Gateway 内部结构图

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

### 3.6 启动期能力发现

v1 Gateway 启动时应：

1. 查询 LMCache 版本、Build ID 和运行模式；
2. 查询 Config、Connector 和已加载 Adapter；
3. 探测所需 HTTP Route、SDK 方法、Metric 和 Event；
4. 构建不可变 `CapabilitySnapshot`；
5. 校验 Chunk Size、Hash、Layout、Serde、Tier 和 Completion Model；
6. 生成 `EndpointGeneration`；
7. 将 Profile 写入 Instance Capability 和 Trace。

未知能力不得视为支持。LMCache 接口更名或小版本变化只替换 Gateway Adapter，不修改 KDN 领域对象。

## 4. v1、Legacy 与 Auto 边界

### 4.1 运行 Profile 分流结构图

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

- 所有新功能只进入 v1；
- 通过 Gateway 使用 LMCache 公开控制与观测接口；
- 不直接扫描、复制或推断 Redis Key；
- 缺少能力时返回结构化失败或明确文本回退；
- 实际复用由 hit-token 或 remote-read 观测确认。

### 4.3 Legacy

- 保留 Redis scan/dump/restore/inject、旧启动和旧请求；
- 功能冻结，只接受可用性、安全、严重缺陷和兼容修复；
- Legacy Key 和目录不能成为 v1 Artifact 身份；
- Legacy 物理操作只允许出现在 `LegacyCacheAdapter`。

### 4.4 Auto

```text
auto --> v1
```

或：

```text
auto --> legacy
```

解析后 Profile 在进程生命周期内不可变，不得根据请求或 Key 是否存在动态切换。

## 5. 权威边界和总体角色

| 信息 | 权威来源 |
|---|---|
| KnowledgeObject 内容、版本和语义 | KDN Knowledge Control Plane |
| KnowledgeObject 到 CacheArtifact 的关系 | KDN Knowledge Control Plane |
| Artifact 兼容性和失效原因 | KDN Knowledge Control Plane |
| Prefetch、Pin、Clear、Rebuild Desired State | KDN Policy |
| LMCache Endpoint、接口和能力 Profile | Gateway Capability Snapshot |
| Token/Chunk/Hash/Key、物理 KV、Layout、Serde | LMCache Runtime |
| L1/L2、Adapter、容量、Quota 和淘汰 | LMCache Runtime |
| 物理操作是否完成 | LMCache Runtime Observation |
| Instance 本地实际命中 Token | Instance-side LMCache |
| 请求等待、绕行和计算释放 | Proxy |
| Proxy、Instance、KDN Endpoint 粗粒度选择 | Scheduler |

所有物理观测必须携带：

```text
observation_source
observed_at
expires_at
endpoint_generation
lmcache_profile_id
adapter_or_tier
confidence
```

## 6. 核心对象

### 6.1 RuntimeProfile

```text
profile_id
resolved_mode
source
resolved_at
immutable
```

持久运行状态只允许 `v1`、`legacy` 或 `mock/test`；`auto` 只是启动输入。

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

推荐的 `integration_family`：

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

Profile 状态：

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

Artifact 是知识在兼容环境下的逻辑物化身份，不保存 KV 字节。

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

它是带 TTL 的短期物理观测，不是 CacheRoute 自有 Replica 或 Chunk Index。

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

资源类型：

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

## 7. 版本迭代总览

| 版本 | 主题 | 主要交付 |
|---|---|---|
| v0.1.10 | v1/Legacy 契约与观测基线 | RuntimeProfile、Gateway Profile、核心状态、Trace、Legacy 投影 |
| v0.1.11 | Knowledge Control + LMCache Observation | Knowledge/Artifact、Token Mapping、Endpoint/Adapter/Tier 观测 |
| v0.1.12 | LMCache-backed KDN Cache Service MVP | MP HTTP/Coordinator Gateway、Lookup/Prefetch/Pin/Clear |
| v0.1.13 | 多层级、多 Adapter 与版本兼容 | Adapter Cascade、容量/淘汰观测、兼容矩阵、恢复/重建 |
| v0.1.14 | Proxy KVCache Manager | 基于 KDN/LMCache 观测的短期 Instance View、Single-flight |
| v0.1.15 | 注入与计算队列模型 | ExecutionGraph、资源队列、Compute Fast Path |
| v0.1.16 | 网络与计算并行 | 工作守恒流水线、Overlap Benchmark |
| v0.1.17 | 队列稳定与普适性 | 准入、背压、公平、Aging、自适应并发 |
| v0.1.18 | KDN 知识型策略 | Prefetch/Pin/Clear/Rebuild 意图、价值模型、Replay |
| v0.1.19 | 多知识块非前缀融合 | Token/Artifact 并行查询、选择性重计算、质量回退 |
| v0.2.0 | 集成研究基线 | v1 默认、Legacy 保留、跨 LMCache 版本兼容、完整实验闭环 |

## 8. 分版本规划

## v0.1.10：v1/Legacy 契约与观测基线

### 目标

冻结后续工作所需的稳定词汇：

- RuntimeProfile；
- LMCacheCompatibilityProfile；
- LMCacheEndpoint 与 CapabilitySnapshot；
- CacheArtifact 和 CacheReplicaObservation；
- CacheOperationTask；
- QueueWork、Trace Source 和阶段；
- Legacy `kv_ready` 与 Redis 只读兼容映射。

### 验收

- #138 Capability 保持兼容；
- `auto` 启动时解析并冻结；
- v1 操作不能静默调用 Legacy 写 Adapter；
- 核心对象不包含 KV 字节、Redis 私有 Key、凭据或 LMCache 私有类；
- Token Lookup、Prefetch、Pin、Clear 等表达为 LMCache-backed 操作；
- CPU-only 测试使用 Mock Gateway，不要求外部服务。

## v0.1.11：Knowledge Control 与 LMCache Observation

### 主要步骤

1. 实现 KnowledgeObject 和版本管理。
2. 一个 KnowledgeObject 对应多个 CacheArtifact。
3. 建立 KnowledgeObject 到 Token Reference、Artifact 的映射。
4. Artifact 使用 Capability 和 LMCache Data Profile 判断兼容性。
5. 实现 Desired State 与 LMCache Observation 分离。
6. 建立 LMCacheEndpoint、Adapter 和 Tier Registry。
7. 所有物理观测记录来源、Profile、Generation、时间和 TTL。
8. Scheduler 只读取粗粒度知识和 Endpoint 可用性。
9. Legacy `kv_ready` 映射为只读、`compatibility=unknown` 的观测。

### 验收

- 同一知识支持多模型、多 Adapter 和多 LMCache Profile；
- KDN 不访问或复制物理 KV 数据；
- 过期观测不会继续视为权威；
- Redis 不出现在 v1 稳定领域模型。

## v0.1.12：LMCache-backed KDN Cache Service MVP

### 主要步骤

1. 实现版本化 KDN Knowledge API 与 Cache Service API。
2. 实现 `MPHTTPGateway`。
3. 实现 `MPCoordinatorGateway` 的最小能力。
4. 实现 LookupTokens、GetCacheObservation、Prefetch、Pin、Unpin、Clear 和 OperationStatus。
5. 建立 CapabilityFactory 和 AdapterFactory。
6. 实现 Mock Gateway 用于 CPU-only CI。
7. 使用 LMCache hit-token 或 remote-read 验证实际复用。
8. 缺少能力时返回 `unsupported` 或明确回退。
9. 不在 KDN 中实现物理 KV Store 或逐 Chunk 数据路径。

### 验收

- vLLM 与 LMCache MP 保持直接数据路径；
- KDN 可将领域操作稳定映射到 LMCache 公开接口；
- Gateway 替换不修改 KnowledgeObject、CacheArtifact 或 CachePlan；
- 失败可以结构化回退文本计算；
- Legacy 行为不受影响。

## v0.1.13：多层级、多 Adapter 与 LMCache 版本兼容

### 主要步骤

1. 支持多个 L2 Adapter 和 Tier 的能力发现与观测。
2. 复用 LMCache Adapter Cascade、容量、Quota 和淘汰能力。
3. 建立 Compatibility Matrix 和 Gateway Conformance Suite。
4. 支持 baseline、latest、Legacy、unknown-future Profile。
5. 实现 Endpoint Generation、重连和观测失效。
6. 实现 Profile 升级、降级和弃用状态。
7. 对 Key/Layout/Serde 不兼容执行迁移或重建。
8. 只有证明 LMCache 存在能力缺口时才增加 L2 Plugin。
9. 增加 LMCache 小版本周期性验证流程。

### 验收

- 至少表示两种 Adapter/Tier 配置；
- LMCache 接口变化只修改 Gateway Adapter；
- 不兼容升级不会静默复用旧 Artifact；
- KDN 不实现自己的 Adapter Cascade、容量或淘汰线程。

## v0.1.14：Proxy KVCache Manager

### 主要步骤

1. 建立 Instance Cache Observation View。
2. 数据来源包括 KDN 观测、LMCache Event、Gateway 结果和实际命中。
3. 状态包括 UNKNOWN、REMOTE_AVAILABLE、PREPARING、LOCAL_AVAILABLE、STALE、FAILED。
4. 同 Artifact/Instance 实现 Single-flight。
5. Endpoint、Instance 或 Profile Generation 变化时失效。
6. Proxy 不复制 LMCache Chunk Index。

### 验收

- Proxy 区分远端可用、准备中、本地可用和过期；
- 同一准备任务只执行一次；
- 实际命中由 LMCache 原生观测确认。

## v0.1.15：知识注入与计算队列模型

- CachePlan 编译为 ExecutionGraph；
- 节点包括 Control、KDN Lookup、LMCache Gateway、Network KV、Cache Load、Prefill、Decode 和 Fusion；
- 定义依赖、Share Key、优先级、Deadline、成本和回退；
- 文本任务走 Compute Fast Path；
- Scheduler 不参与细粒度节点执行。

## v0.1.16：网络 KV 与纯计算并行

- 为 Control、Gateway、Network、Cache Load、Compute 建立独立并发域；
- 网络 KV 与其他请求 Prefill/Decode 重叠；
- Work-conserving，不因等待 KV 让可计算请求空闲；
- 增加网络—计算 Gantt 和 Overlap Ratio；
- 支持取消、超时和回退。

## v0.1.17：队列普适性和稳定性

- 准入控制和背压；
- 公平、Aging 和 Starvation Guard；
- Adaptive Concurrency；
- Single-flight 生命周期；
- 多模型、多 Instance、多 KDN、多带宽和不同混合比例测试；
- 策略插件不能破坏状态机。

## v0.1.18：KDN 知识型缓存策略

### 输入

- 知识访问频率和共现；
- LMCache Token Lookup、Metrics 和 Events；
- Endpoint、Adapter、Tier 容量和健康；
- Proxy 等待和 GPU Idle；
- 网络成本和计算节省；
- 构建、刷新和迁移成本；
- Artifact 兼容性和版本；
- Online 与 Background 负载。

### 输出

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

### 要求

- 每个决策有 Reason Code；
- 防止 Pollution 和 Oscillation；
- Online SLO 优先；
- 支持 Shadow、Replay 和可控启用；
- 不直接操作 LMCache 或 Provider 私有 Key；
- 将知识策略意图编译为 LMCache 公开操作。

## v0.1.19：多知识块非前缀融合

- 一个请求解析多个知识块；
- Artifact Resolve 与 Token/Cache Lookup 并行；
- Full/Partial/Overlap/Reorder 统一规划；
- 使用 LMCache Non-prefix、CacheBlend 或等价公开能力；
- 选择性重计算必要 Token；
- 多块 Preparation 接入 ExecutionGraph；
- 不支持、质量失败或超时时回退文本；
- 比较串行加载、并行加载、纯文本和单前缀复用。

## v0.2.0：集成、稳定与研究基线

v0.2.0 完成时应满足：

- v1 是默认开发和实验路径；
- Legacy 保持可运行并有明确弃用策略；
- KDN 作为 Knowledge Control + Cache Service Facade + LMCache Gateway 独立部署；
- vLLM 与 LMCache MP 数据热路径不经过 KDN 业务服务；
- 至少验证 baseline 和 latest 两个 LMCache Profile；
- 至少表示两个 Adapter/Tier 配置；
- Proxy 使用短期观测而非权威 Block Index；
- 网络 KV 与纯计算可并行；
- 队列具备 Single-flight、背压、公平、取消和回退；
- 支持至少两个知识块非前缀复用；
- KDN 有至少一种知识价值策略；
- 关键故障和升级场景有可重复测试；
- 文本、单知识和 Legacy 路径兼容。

## 9. LMCache 演进兼容测试框架

### 9.1 Contract Tests

同一套领域与 Gateway Contract Tests 应运行于：

- Mock MP HTTP Profile；
- Mock Coordinator Profile；
- Mock SDK Profile；
- Mock Metrics/Event Profile；
- 当前 v1 validated Profile；
- Legacy Profile；
- unknown-future Profile。

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

- LMCache 小版本升级；
- HTTP Route、SDK 或 Metric 更名；
- Completion Model 变化；
- Key Format、Layout 或 Serde 变化；
- Endpoint 重启和 Generation 变化；
- Adapter 增删或顺序变化；
- 新旧 Profile 并存；
- Profile 弃用和回滚；
- Legacy 到 v1 显式迁移或重建。

### 9.4 失败原则

- 未知能力不默认支持；
- 不兼容 Artifact 不加载；
- Gateway 失败不破坏知识目录；
- KDN 控制面失败不改变已运行的 LMCache 数据路径；
- v1 不静默执行 Legacy 写操作；
- 失败时 Proxy 可回退文本；
- 升级失败可回到上一个 validated Profile。

## 10. 队列和缓存研究指标

- TTFT P50/P95/P99；
- 吞吐和完成时间；
- Knowledge Resolve Wait；
- LMCache Gateway Request/Operation Time；
- Token Lookup Coverage；
- Hit Tokens 和 Remote Reads；
- Prefetch/Pin/Clear 成功率；
- Endpoint/Adapter/Tier 容量和健康；
- Network-Compute Overlap Ratio；
- GPU Idle Due to Cache Wait；
- Head-of-line Blocking Time；
- Single-flight 节省任务和字节；
- Profile 协商失败率；
- 不兼容重建和回退率；
- LMCache 升级前后结果一致性。

## 11. 状态边界

### KDN Knowledge Control Plane

权威维护知识、Artifact、策略、Desired State、Profile 支持和历史价值。

### KDN Cache Service Facade

权威维护 CacheRoute 逻辑 Operation、幂等关系、任务状态、审计和结构化结果，但不拥有物理 KV。

### LMCache Gateway

维护当前 Endpoint Capability Snapshot、版本 Adapter 和短期调用观测；不成为第二套物理事实来源。

### LMCache Runtime

权威维护 Token/Chunk/Key、物理 KV、L1/L2、Adapter、Serde、锁、容量、淘汰和底层操作结果。

### Proxy

维护请求级计划、短期 Instance/LMCache 观测、共享准备任务和队列。

### Instance / vLLM

权威维护实际命中 Token、模型执行、Prefill 和 Decode 结果。

## 12. 测试与实验要求

### 单元测试

- RuntimeProfile 解析和冻结；
- Object ID 和状态转换；
- LMCacheCompatibilityProfile；
- CapabilitySnapshot；
- Secret/Private Key 拒绝；
- Observation TTL 和 Endpoint Generation；
- CacheOperationTask 幂等；
- CachePlan/FusionPlan；
- ExecutionGraph；
- Trace 来源。

### CPU-only 组件测试

- Mock HTTP/Coordinator/SDK/Metrics Gateway；
- Knowledge 与 Cache Service Contract；
- supported/unsupported/incompatible/fallback；
- Legacy 只读投影；
- v1 不调用 Legacy 写路径；
- 两种 Adapter/Tier 表示；
- Generic pytest collection 不访问外部服务。

### GPU 端到端测试

- vLLM + LMCache MP + CacheRoute；
- Token Lookup、Warm Prefetch 和 Operation Status；
- 冷请求无缓存读取；
- 热请求有 hit-token 或 remote-read；
- 冷热确定性输出一致；
- Endpoint 重启和 Generation 失效；
- 文本、单知识 KV、Hybrid 和 Legacy 回归。

### 实验复现

保存：

- CacheRoute、vLLM、LMCache 版本；
- Runtime 和 Compatibility Profile；
- Gateway Adapter 与 Capability Snapshot；
- 工作负载和 Endpoint/Adapter/Tier 拓扑；
- 队列和策略参数；
- ExecutionGraph；
- 请求级 Trace 和结果；
- 汇总指标和异常。

## 13. 版本依赖

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

## 14. KDN 的长期演进趋势

达到 v0.2.0 后，KDN 的演进方向应是：

1. 从单体服务演进为 Knowledge Control、Cache Service 和多个 Gateway Worker；
2. 从单 LMCache Endpoint 演进为多 Endpoint 和多区域编排；
3. 从静态 Profile 演进为自动 Capability Negotiation 和 Conformance；
4. 从粗粒度 Artifact 演进为多块、部分和组合知识缓存；
5. 从规则策略演进为 SLO 和不确定性感知策略；
6. 与 LMCache 新的 MP、Coordinator、SDK、Adapter、Metrics 和 Event 能力持续对齐；
7. 只有明确证明 LMCache 扩展机制无法满足需求时，才新增 CacheRoute 特有的数据扩展；
8. 始终保持 Knowledge API、Cache Service Domain、Gateway Adapter 和 LMCache Runtime 四层隔离。

无论 LMCache 底层如何演进，CacheRoute 的长期核心始终是：

> **把知识语义、LMCache 原生缓存能力、缓存策略和计算队列编排连接为一个可观测、可扩展、可复现实验的闭环。**
