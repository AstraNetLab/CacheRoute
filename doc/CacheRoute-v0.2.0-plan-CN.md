# CacheRoute v0.2.0 演进规划

> 状态：规划草案（已根据 v0.1.10 实施进展与 LMCache 对齐原则更新）  
> 当前发布基线：v0.1.9  
> 当前开发阶段：v0.1.10 进行中  
> 目标版本：v0.2.0  
> 核心底座：vLLM + LMCache  
> 核心研究方向：KDN 知识控制面、LMCache 对齐的数据访问面、知识型缓存策略、基于 LMCache 观测的 Proxy KVCache Management、知识注入与计算队列并行、多知识块非前缀融合复用

## 0. 当前实施状态与本次设计校正

v0.1.10 已经开始实施，因此后续规划必须在保留已完成工作的基础上校正架构边界，而不是推倒重来。

| 项目 | 当前状态 | 规划处理 |
|---|---|---|
| #138 / PR #143 | 已完成并合并 | 保留 Instance Capability Fingerprint 与兼容性判断契约 |
| PR #145 | 已完成并合并 | 保留能力文档、测试说明和包版本基线同步结果 |
| #139 / PR #147 | 正在实施 | 保留不可变状态模型，但明确 Artifact/Replica 只是 CacheRoute 对 LMCache 数据的逻辑视图 |
| #140 | 待实施 | 调整为 LMCache 管理接口适配协议，而不是自建第二套缓存存储协议 |
| #141 | 待实施 | 将 LMCache Lookup、Controller、MP API、KV Event 和运行时回执作为一级 Trace 来源 |
| #142 | 待实施 | 增加 LMCache 对齐验证，并修复历史脚本阻断 CPU-only pytest 收集的问题 |

本次规划确立以下不可违反的原则：

> **LMCache 负责物理 KVCache 存储、块索引、分层、传输、序列化和运行时操作；CacheRoute 负责知识语义、策略、编排、排队与可复现实验。**

CacheRoute 可以维护逻辑 Artifact、Replica 引用、期望状态、策略状态和短期观测，但不能：

- 再实现一套与 LMCache 并行的物理 KVCache Store；
- 复制 LMCache 的 Token/Chunk 索引；
- 将 KDN 文件目录、Redis Key 或私有序列化格式作为长期稳定契约；
- 在 Proxy 内维护第二套权威 Instance KVCache 目录；
- 直接绕过 LMCache 操作底层 KV 数据，除非处于明确标记的 Legacy 兼容路径。

## 1. 整体目标

CacheRoute v0.2.0 的目标不是重新实现 KVCache 存储系统，也不是优先引入复杂的全局调度算法，而是在 vLLM + LMCache 之上建立面向知识复用的语义控制、策略编排和多资源队列框架。

目标闭环如下：

```text
知识注册与版本管理
  -> 将知识映射为模型/Tokenizer/Adapter 相关的 CacheArtifact 意图
  -> 通过 LMCache Lookup / Status / Event 查询物理缓存事实
  -> KDN 生成知识级策略和缓存操作意图
  -> Proxy 构建 CachePlan / FusionPlan / ExecutionGraph
  -> LMCache 负责查找、加载、预取、移动、Pin、清理与后端传输
  -> 知识准备队列与纯计算队列并行推进
  -> vLLM 执行 Prefill / Decode / 选择性重计算
  -> 回报命中、排队、传输、加载、计算和质量结果
  -> KDN 更新价值模型和后续策略
```

v0.2.0 重点建设五条相互依赖的主线。

### 1.1 KDN 知识控制面

KDN 控制面是知识语义、逻辑制品和策略的权威目录，而不是物理 KVCache Store。它负责：

- 区分 KnowledgeObject、CacheArtifact 和逻辑 CacheReplica；
- 将知识版本与 Instance Capability Fingerprint 映射到 LMCache 可查询的 Token、Hash 或对象引用；
- 维护兼容性、期望生命周期、策略状态、Pin 意图、预算和历史价值统计；
- 发现 LMCache 能力并接收 Lookup、Worker、Health、Event 和任务结果；
- 生成构建、保存、预取、移动、Pin、清理、刷新和回退等高层意图；
- 提供稳定、轻量、可版本化的查询和任务接口；
- 不在控制消息中携带大块 KV 数据、后端凭据、Redis 私有 Key 或 LMCache 私有块索引。

KDN 对“为什么该缓存存在、它对应什么知识、应该采取什么策略”负责；LMCache 对“物理缓存是否存在、位于哪里、操作是否完成”负责。

### 1.2 LMCache 对齐的数据访问面

KDN 数据面应重新定义为 LMCache 上层的数据访问与编排适配层，不再建设独立存储引擎。

主要职责：

- 调用 LMCache 已支持的 Lookup、Retrieve/Prefetch、Move/Copy、Pin/Unpin、Clear/Delete、Health、对象枚举和任务状态接口；
- 使用 LMCache 的 CPU、磁盘、Redis/Valkey、Mooncake、InfiniStore、S3、NIXL、GDS 和 Storage Plugin 等后端；
- 通过统一 Adapter 屏蔽 LMCache in-process/Controller 与 MP HTTP/Coordinator 模式差异；
- 统一返回实际命中 Token、字节数、位置、层级、排队时间、操作耗时、Worker 健康和结构化错误；
- 对不支持的操作返回明确 `unsupported`，而不是在 CacheRoute 中错误模拟；
- 将当前直接 Redis/文件注入封装成 `LegacyCompatibilityAdapter`；
- 保证 LMCache 操作失败不会破坏 KDN 知识目录，KDN 临时故障也不应直接破坏已执行中的 LMCache 任务。

CacheRoute 的 DataPlaneTask 是对 LMCache 操作的逻辑编排记录，执行者通常是 LMCache，而不是 CacheRoute 自建 Data Worker。

新增底层存储能力时，应优先扩展 LMCache Storage Plugin 或 Remote Connector；只有在确认 LMCache 不具备且无法合理扩展时，才讨论 CacheRoute 特有实现。

### 1.3 知识注入与计算队列并行

这是 CacheRoute 最重要的系统特色。

Proxy 不应把“所有知识准备完成”作为请求进入计算前的统一串行屏障，而应显式建模并并行推进：

- KDN 知识元数据解析；
- LMCache Cache Lookup；
- 远端 KVCache Retrieve/Prefetch；
- LMCache 本地加载和确认；
- 纯文本或残余 Token Prefill；
- Decode；
- 多知识块局部准备和融合依赖。

队列机制应保证：

- 网络 KV 准备与其他请求的纯计算并行；
- 不依赖远端 KV 的文本任务走 Compute Fast Path；
- 慢 KV 任务不阻塞立即可计算任务；
- 同一 Artifact、同一目标 Instance 的请求共享 Single-flight；
- 不同 LMCache Endpoint、链路、Instance 和资源类型独立并发；
- 状态机、依赖和资源上限由统一机制保证，策略只能改变优先级、配额、绕行和并发；
- 机制适用于不同模型、后端、带宽、知识块数量和文本/KV 混合比例。

### 1.4 KDN 知识型缓存策略

KDN 策略位于 LMCache 之上，重点研究：

- 哪些知识值得构建或保存 KVCache；
- 哪些 LMCache 管理的缓存对象值得 Pin、保留、移动、预取或清理；
- 热点知识应预热到哪个层级或哪个 Instance 附近；
- 模型、Tokenizer、Adapter、KV Layout 或知识版本变化后何时刷新；
- 如何利用 Proxy 队列反馈、LMCache Lookup/Event、网络成本、计算节省和多块共现；
- 如何避免污染、抖动和后台操作干扰在线请求；
- 如何使策略研究不依赖某一个具体 LMCache 后端。

CacheRoute 策略只产生“期望动作和优先级”，实际块级淘汰、存储分配、序列化和传输仍由 LMCache 负责。

### 1.5 多知识块非前缀匹配与融合复用

v0.2.0 需要支持：

- 一个请求携带多个独立 Knowledge Block；
- 在 Prompt 任意位置识别可复用知识，而不仅是连续前缀；
- 对完全命中、部分命中、重叠和顺序变化进行统一规划；
- 使用 LMCache 非前缀复用、CacheBlend 或等价能力；
- 对必要 Token 进行选择性重计算；
- 将多块 Lookup、Prefetch 和 Load 接入统一 ExecutionGraph；
- 在运行时不支持、观测过期、质量校验失败或执行异常时稳定回退文本计算。

## 2. 总体边界和工程原则

### 2.1 角色边界

```text
Scheduler
- 选择目标 Proxy / KDN 资源池
- 保留全局知识感知和资源感知候选能力
- 不承担细粒度缓存生命周期、物理存储和队列执行

KDN Control Plane
- 维护知识身份、Artifact 兼容性、期望状态、策略和编排历史
- 将知识需求映射为 LMCache 可查询引用
- 不成为物理 KV Store，不复制 LMCache Chunk/Location Index

KDN LMCache Adapter / Data Access Plane
- 将 CacheRoute 意图转换为 LMCache Controller、CacheEngine、MP HTTP、Coordinator 或 Plugin 操作
- 统一能力、观测、任务结果和错误
- LMCache 已支持的后端不在 CacheRoute 中重复实现

Proxy
- 构建 CachePlan、FusionPlan、ExecutionGraph
- 基于 LMCache Lookup/Status/Event 维护短期 Instance Cache View
- 协调知识准备和计算队列
- 不建立第二套权威缓存目录

Instance
- 连接 Proxy、vLLM 和 LMCache
- 上报 Capability、LMCache 事件和执行结果
- 提供稳定的缓存观测与控制入口

LMCache
- 负责物理缓存对象、Chunk Index、存储层级、序列化、淘汰机制、加载、传输和 vLLM Connector
- 是缓存驻留和运行时操作的主要事实来源

vLLM
- 负责模型执行、Paged KV 管理和引擎内部调度
```

### 2.2 LMCache 对齐原则

1. CacheRoute 不实现与 LMCache 竞争的物理 KVCache Store。
2. KnowledgeObject 和 CacheArtifact 是 CacheRoute 语义对象；CacheReplica 是 LMCache 位置/对象的逻辑引用。
3. 物理缓存事实来自 LMCache Lookup、Controller、MP API、KV Event 或运行时确认。
4. KDN 的期望状态和策略状态必须与 LMCache 观测状态分离。
5. 所有 LMCache 操作经过 Capability-aware Adapter。
6. 不把 Redis Key、密码、连接串、私有序列化格式和内部 Chunk Layout 当作稳定接口。
7. 优先使用 LMCache 公共 Lookup、Health、Object/Status、Prefetch、Move、Pin、Clear 和 CheckFinish 接口。
8. Legacy Redis/文件路径只用于兼容和回归。
9. 新存储后端优先通过 LMCache Plugin/Connector 扩展。
10. 不确定或过期观测必须表示为 `UNKNOWN/STALE`，不能猜测为 `READY`。

### 2.3 队列与执行原则

1. **依赖正确性优先**：必需依赖未满足时不得提前计算。
2. **工作守恒**：资源可用且存在可执行任务时不应空闲。
3. **资源分离**：CONTROL、LMCache Lookup、NET_KV、CACHE_LOAD、PREFILL、DECODE 分别维护预算。
4. **避免队头阻塞**：慢远端操作不得阻塞无关文本或本地命中任务。
5. **Single-flight**：重复准备合并。
6. **事件驱动释放**：优先使用 LMCache 事件、任务完成和回执唤醒依赖。
7. **可取消、可超时、可回退**。
8. **策略与机制分离**。
9. **预测与实测分离**。
10. **兼容快速路径**：纯文本、单前缀 KV 和当前 IWS 都是统一执行图的特例。

### 2.4 工程原则

- 每个版本独立运行、独立验证；避免一次性大重构。
- 已合并的 v0.1.10 Capability 契约保持兼容。
- 新字段默认可选，旧请求、旧 `kv_ready` 和 Legacy 路径继续可用。
- 所有状态变化和外部观测可序列化、可追踪。
- 不在 `demo_*.py` 中承载业务逻辑。
- 使用 LMCache 公共接口，不复制私有实现。
- 运行时失败优先保证正确性并回退文本。
- 所有研究策略可关闭、可替换、可复现。

### 2.5 v0.2.0 暂不优先实现

- 分层 Pareto 全局调度；
- 强化学习或 Bandit 在线策略；
- 完整 Prefill/Decode 解耦；
- 自研 RDMA 传输引擎；
- 替代 LMCache 的 KV Store；
- 跨地域、多租户生产级控制面；
- 依赖 LMCache 私有内部实现的深度侵入式修改。

## 3. 现有基础与主要缺口

### 3.1 KDN 现有基础

当前具备：

- SQLite 文本知识索引和基于内容 Hash 的 `kid`；
- 文本、Embedding、长度和粗粒度 KV 元数据；
- `KV_database/<kid>`、Manifest 和 KV dump；
- 文本注册、查询、删除、快照和 KV 构建；
- 直接写入目标 Redis 的 Legacy 注入路径；
- KDN 注册、心跳、网络队列模拟和基础传输统计。

主要限制：

- 目录、文件管理、注入和策略耦合；
- 一个 `kid` 只能表达一套粗粒度 KV 状态；
- `kv_ready` 无法表达兼容性、观测来源、过期和物理位置；
- 文件、SQLite 和 LMCache/Redis 事实可能不一致；
- 当前路径绑定 Redis Key 和序列化格式；
- 尚未使用 LMCache Controller/MP 管理接口作为事实来源。

### 3.2 Proxy 与队列基础

当前具备：

- Instance Pool 和 `round_robin`、`least_load`；
- `inflight`、队列深度和预测 backlog；
- prepare/ready 双队列和 Instance 时间线；
- KDN 文本查询和 `kv_ready/text_only/miss` 分类；
- KDN 到 Instance 的传输预测；
- `ordered/text_bypass` Ready 释放策略；
- IWS 文本/KV 注入决策基础；
- v0.1.10 Capability Fingerprint 与兼容性注册已经完成。

主要缺口：

- Proxy 仍缺少基于 LMCache Lookup/Event 的统一 Instance Cache View；
- prepare 阶段包含多类资源，但主要仍是一条粗队列；
- LMCache Lookup、网络传输、Load、Prefill、Decode 的依赖未统一；
- 文本绕行还不是通用工作守恒机制；
- 重复查询、Single-flight、取消和重试需要系统化；
- 多知识块缺少 FusionPlan 和 ExecutionGraph。

### 3.3 vLLM + LMCache 基础

后续应直接利用 LMCache 已有能力：

- vLLM KV Connector；
- Token/Hash Lookup 与命中长度/位置查询；
- 异步 Retrieve、Prefetch、Load、Save 和事件；
- CPU、磁盘、Redis/Valkey、Mooncake、InfiniStore、S3、NIXL、GDS 和插件后端；
- Controller 的 Lookup、Move、Pin、Clear、Health 和 CheckFinish；
- MP HTTP/Coordinator 的 Status、Object、Prefetch、Adapter、Metrics 和多服务协调；
- 非前缀复用和 CacheBlend；
- KV Event 与 Worker/Runtime 观测。

需要显式处理的风险：

- in-process/Controller 与 MP API 可能不同；
- 并非所有模式都暴露精确 GPU Residency；
- LMCache 公共 API 持续演进；
- CacheRoute Adapter 必须做能力协商，并记录观测来源、时间和置信度。

## 4. v0.2.0 目标架构

```text
                              Scheduler
                                  |
                        knowledge-aware route
                                  |
                                Proxy
  +-------------------+-----------+-----------------------------+
  |                   |                                         |
Admission         Plan Builder                         Queue Coordinator
- validate        - Knowledge Layout                  - Dependency Graph
- fallback        - KDN semantic query                - Resource Budgets
- trace           - LMCache observed query            - Event-driven release
  |                   |                                         |
  |                   +---------------------+-------------------+
  |                                         |
  |                        Knowledge Preparation Plane
  |                  +----------+----------+----------+
  |                  |          |          |          |
  |               metadata   LMCache    cache load  fusion
  |                resolve   lookup /      wait      prepare
  |                          prefetch
  +----------------------------- Compute Plane
                        +-----------+-----------+
                        |                       |
                 pure/residual Prefill       Decode
                        |                       |
                        +-----------+-----------+
                                    |
                            Instance / vLLM
                                    |
                                 LMCache
              +---------------------+-----------------------+
              |                     |                       |
          CPU / Disk          Remote Backends           P2P/Transport
                            Redis/Valkey/S3/...       NIXL/Mooncake/...

                         KDN Control Plane
       +----------------------+----------------------+----------------+
       |                      |                      |                |
Knowledge Catalog      Artifact Intent Catalog    Policy Engine   Task/Trace
       +----------------------+-----------+----------+----------------+
                                          |
                           LMCache Integration Adapter
            lookup / status / prefetch / move / pin / clear / events
                                          |
                                     LMCache APIs
```

该架构不包含 CacheRoute 自有物理存储层。KDN 可以作为远端知识服务部署，但 KV 数据必须位于 LMCache 管理的存储和传输单元中。

## 5. 核心对象和执行模型

### 5.1 KnowledgeObject

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

CacheArtifact 表示某个知识版本在特定兼容环境下“可复用 KV 物化”的逻辑意图和语义身份。

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
desired_state
policy_state
created_at
updated_at
```

Artifact 不保存 KV 数据，不复制 LMCache Chunk Index。

### 5.3 CacheReplica

CacheReplica 是 Artifact 与 LMCache 管理位置之间的逻辑观测/引用。

```text
replica_id
artifact_id
provider                 # 通常为 lmcache
lmcache_mode             # controller / mp / in_process / unknown
lmcache_instance_id
worker_id
backend_type
storage_tier
location_ref             # 不透明、无秘密信息的引用
observed_state
health
observation_source       # lookup / event / status / legacy / inferred
observed_at
expires_at
confidence
```

`location_ref` 不得包含密码、连接串、私有 Redis Key 或序列化数据。

### 5.4 LMCacheEndpoint

```text
endpoint_id
api_mode
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

DataPlaneTask 是对 LMCache 操作的 CacheRoute 编排记录。

```text
task_id
idempotency_key
operation                 # LOOKUP/PREFETCH/MOVE/PIN/UNPIN/CLEAR/VERIFY/STATUS
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

### 5.6 CachePlan / FusionPlan

```text
request_id
target_instance_id
knowledge_blocks
matched_artifacts
lmcache_observations
missing_blocks
prepare_tasks
fusion_mode
recompute_ranges
fallback_mode
plan_state
trace_context
```

### 5.7 ExecutionGraph

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

推荐资源类型：

```text
CONTROL         KDN 语义查询和计划解析
CACHE_LOOKUP    LMCache Lookup/Status
NET_KV          LMCache 远端 Retrieve/Prefetch/Move
CACHE_LOAD      LMCache 本地加载和确认
PREFILL         纯文本或残余 Token 计算
DECODE          Decode 占用与完成跟踪
FUSION          多块融合和选择性重计算准备
```

## 6. 版本迭代总览

| 版本 | 主题 | 主要交付 |
|---|---|---|
| v0.1.10 | 契约与观测基线 | Capability、不可变逻辑状态、LMCache 对齐协议词汇、Queue Trace |
| v0.1.11 | KDN 语义目录 | KnowledgeObject、Artifact Intent、逻辑 Replica 引用 |
| v0.1.12 | LMCache 集成面 | 能力发现、Lookup/Status/Event、管理 Adapter、Legacy Adapter |
| v0.1.13 | 期望/观测生命周期 | LMCache Reconcile、Freshness/Confidence、任务恢复 |
| v0.1.14 | Proxy KVCache Manager | 基于 LMCache 观测的 Instance View、CachePlan、Single-flight |
| v0.1.15 | 注入与计算队列模型 | ExecutionGraph、资源队列、依赖释放、Compute Fast Path |
| v0.1.16 | 网络与计算并行流水线 | 工作守恒并行、链路/Instance 时间线、Overlap Benchmark |
| v0.1.17 | 队列普适性和稳定性 | 准入、背压、公平、Aging、自适应并发、故障回退 |
| v0.1.18 | 知识型缓存策略 | 基于 LMCache 的 Pin/Move/Prefetch/Clear 策略、价值模型、Trace Replay |
| v0.1.19 | 多块非前缀融合 | 匹配、并行 LMCache 准备、选择性重计算、质量回退 |
| v0.2.0 | 集成研究基线 | 完整闭环、故障测试、稳定接口、可复现实验 |

## 7. 分版本规划

## v0.1.10：契约与观测基线（进行中）

### 当前状态

- #138 / PR #143：已完成；
- PR #145：已完成；
- #139 / PR #147：正在实施；
- #140、#141、#142：待实施，并需按本规划调整。

### 主要目标

1. 保留已经合并的 Instance Capability Fingerprint。
2. 定义不可变、可序列化、策略无关的 Artifact/Replica/DataPlaneTask/QueueWork 状态。
3. 明确这些对象是逻辑控制对象，不是物理存储实现。
4. 定义 LMCache 对齐的协议词汇、版本和结构化错误。
5. 统一 Trace 中预测、实测、来源、阶段和回退字段。
6. 保持 Legacy 请求、`kv_ready` 和 Redis 注入兼容。
7. 建立 CPU-only 回归门禁。

### 验收标准

- Capability 不兼容能够在复用前识别；
- 状态模型不可变、转换可验证；
- Replica 能表示 LMCache 逻辑位置且不携带底层秘密；
- 协议不设计第二套物理 Store；
- Trace 标识 LMCache 观测来源；
- 旧路径保持可运行；
- pytest 收集不要求外部 vLLM 服务。

## v0.1.11：KDN 语义目录与逻辑缓存引用

### 主要步骤

1. 保留 Legacy 表，新增 KnowledgeObject 和 CacheArtifact Intent。
2. 一个 KnowledgeObject 对应多个兼容 Artifact。
3. CacheReplica 仅表示 LMCache 观测位置、来源、时间和置信度。
4. Artifact/Replica ID 不使用原始 Redis Key。
5. `KV_database/<kid>` 和 `kv_ready` 映射为 Legacy、Compatibility Unknown 视图。
6. 支持按知识、Capability 和 Artifact Variant 查询。
7. 提供 LMCache 观测写入接口。
8. Scheduler 只获取粗粒度可用性。

### 验收标准

- 同一知识支持多模型 Artifact；
- Replica 不保存 KV 数据和凭据；
- 期望状态与观测状态可区分；
- 不新增 CacheRoute Store、Chunk Index 和物理淘汰器。

## v0.1.12：LMCache 对齐的远端数据面集成

### 主要步骤

1. 定义 `LMCacheManagementAdapter`。
2. 按 LMCache 模式支持：
   - Lookup 和命中 Token/位置；
   - Health、Worker、Status、Object、Adapter、Metrics；
   - Retrieve/Prefetch 和完成状态；
   - Move/Copy；
   - Pin/Unpin；
   - Clear/Delete；
   - KV Event。
3. 分别实现 Controller/In-process 与 MP HTTP/Coordinator Adapter。
4. 不支持的能力返回 `unsupported`。
5. Legacy Redis/文件注入封装为兼容 Adapter。
6. 统一 Token、Byte、Location、Duration、Provider Task ID 和错误。
7. 提供 CPU-only Mock Adapter 和故障注入。

### 验收标准

- KDN/Proxy 可以通过 LMCache 公共接口查询缓存；
- 不依赖 LMCache 私有 Redis Key 和序列化格式；
- Lookup/Status 和至少一种异步准备操作完成适配；
- 不创建独立物理 KV Store。

## v0.1.13：期望/观测生命周期、一致性和恢复

### 主要步骤

1. 分离 `desired_state`、`observed_state`、`health`、`source`、`observed_at`、`expires_at`。
2. 延续 v0.1.10 不可变状态契约。
3. 通过 LMCache Lookup/Status/Event Reconcile。
4. Artifact 发布过程：构建意图 -> 兼容校验 -> LMCache 保存观测 -> 逻辑可用。
5. 通过 Provider Task ID 和幂等键恢复任务。
6. Endpoint/Instance Generation 变化时使观测失效。
7. Legacy 文件 Reconcile 保留在独立兼容模块。
8. 暴露不一致、过期和失败统计。

### 验收标准

- KDN `READY` 不再等于目标 Instance 已驻留；
- 重启后可从 LMCache 重建观测或安全回到 UNKNOWN；
- 过期观测不会导致错误复用；
- Legacy 不成为长期事实来源。

## v0.1.14：基于 LMCache 观测的 Proxy KVCache Manager

### 主要步骤

1. Proxy KVCache Manager 定位为短期观测和编排组件。
2. 数据来源包括：
   - LMCache Lookup；
   - Controller/MP Status 与 Worker；
   - KV Event；
   - Load/Save/Prefetch 回执；
   - CacheRoute 提交任务结果。
3. 每条观测记录来源、时间、Freshness 和 Confidence。
4. 本地状态只是投影：UNKNOWN、AVAILABLE_REMOTE、PREFETCHING、LOADING、AVAILABLE_LOCAL、FAILED、EXPIRED。
5. KDN 语义 + LMCache 观测生成 CachePlan/FusionPlan。
6. 实现 Single-flight、Query Coalescing 和短期 Negative Cache。
7. Instance/LMCache Generation 变化或事件冲突时失效。
8. Debug API 展示来源、年龄、置信度和 Provider Task。

### 验收标准

- Proxy 能区分逻辑存在、远端存在、加载中和本地可用；
- 所有驻留判断有 LMCache 来源和时间；
- 过期状态安全回到 UNKNOWN；
- 不实现第二套物理缓存索引或淘汰器。

## v0.1.15：知识注入与计算队列模型

### 主要步骤

1. CachePlan 编译为 ExecutionGraph。
2. 建立逻辑资源队列：CONTROL、CACHE_LOOKUP、NET_KV、CACHE_LOAD、PREFILL、DECODE、FUSION。
3. QueueCoordinator 管理依赖、引用、取消和事件唤醒。
4. 文本和本地命中走 Compute Fast Path。
5. 外部保留 prepare/ready 语义，内部由 ExecutionGraph 决定 Ready。
6. 每类资源有独立预算和时间线。
7. 共享节点完成后批量唤醒依赖请求。
8. 记录排队、执行、依赖等待和阻塞原因。

### 验收标准

- 文本任务不被无关远端 KV 阻塞；
- 依赖未满足不提交计算；
- 共享任务只执行一次；
- 取消正确释放引用；
- ExecutionGraph 可观察和复现。

## v0.1.16：网络 KV 与纯计算并行流水线

### 主要步骤

1. 工作守恒 QueueCoordinator。
2. 独立维护 LMCache Endpoint/链路、Instance Load、Prefill Slot 和 Decode 摘要。
3. 网络准备与其他请求 Prefill/Decode 并行。
4. 同请求多知识块可跨 Endpoint/Worker 并行准备。
5. Transfer Coalescing 与 Single-flight。
6. 受带宽和内存预算限制的 Look-ahead。
7. 事件驱动唤醒。
8. 测量 Overlap Ratio、GPU Cache-wait Idle、Network Idle、Pipeline Makespan、TTFT 和吞吐。
9. 对比串行、text_bypass 和完整并行。

### 验收标准

- KV 操作期间其他可计算任务持续执行；
- 多 Endpoint/Instance 不被全局锁串行化；
- 有并行机会时 Makespan 优于串行基线；
- 不破坏正确性和顺序约束。

## v0.1.17：队列普适性、稳定性和策略接口

### 主要步骤

1. 分层准入和背压：全局、Instance、Endpoint、链路、实验组。
2. Priority、Aging、Deadline Hint、Starvation Protection。
3. 大 KV 任务分片或让行。
4. Text/KV/Hybrid/Fusion 统一策略接口。
5. 静态和自适应并发。
6. KDN、LMCache Endpoint、网络、Load、Instance 故障回退和熔断。
7. 重试预算和重试风暴保护。
8. 暴露 Priority/Bypass/Concurrency/Admission Policy。
9. 建立模型、后端、带宽、RTT、负载比例和长尾实验矩阵。

### 验收标准

- 文本与 KV 任务都不会永久饥饿；
- 过载有明确拒绝、降级或背压；
- 故障不产生永久挂起和无限重试；
- 同一机制覆盖单知识、Hybrid 和多知识。

## v0.1.18：LMCache 之上的知识型缓存策略

### 主要步骤

1. 建立命中 Token、Prefill 节省、传输/Load、队列等待和失败的价值统计。
2. 从 LMCache 获取 Adapter、容量摘要、Quota 和支持操作。
3. 将策略动作翻译为 LMCache Pin/Unpin、Prefetch、Move/Copy、Clear/Delete 或 Quota 操作。
4. 物理淘汰使用 LMCache 现有机制，CacheRoute 不实现竞争性的块级淘汰器。
5. 实现至少一种可解释的知识价值策略。
6. 后台操作使用独立预算。
7. 不支持操作和过期容量信息作为策略约束。
8. 提供 Dry-run 和 Trace Replay。
9. 区分策略决策与 LMCache 实际结果。

### 验收标准

- 策略只发出 Adapter 声明支持的 LMCache 操作；
- 能比较无策略、LMCache Baseline 和知识型策略；
- 决策和物理结果分别可追踪；
- 不引入 CacheRoute 物理 Store。

## v0.1.19：多知识块非前缀融合

### 主要步骤

1. 构建有序 Knowledge Block 和 Prompt Layout。
2. 查询每块兼容 Artifact 和 LMCache 观测。
3. 分类完全、部分、非前缀、重叠和未命中。
4. Coverage Map 防止重复覆盖。
5. 生成 FusionPlan。
6. FusionPlan 编译为 ExecutionGraph，多块可并行 Lookup/Prefetch/Load。
7. 适配 LMCache 非前缀复用、CacheBlend 或公开等价接口。
8. 选择性重计算和质量保护。
9. 按单前缀 KV、部分 KV+文本、全文本顺序回退。
10. 建立块数量、顺序、命中率、后端和重算比例实验。

### 验收标准

- 至少两个知识块支持非前缀融合；
- 多块准备能并行且不会形成任务风暴；
- 命中、重算、传输和融合开销可观察；
- 质量或运行时异常正确回退。

## v0.2.0：集成、稳定与研究基线发布

### 主要步骤

1. 冻结 KnowledgeObject、Artifact Intent、逻辑 Replica Observation、LMCacheEndpoint、DataPlaneTask、CachePlan、FusionPlan、ExecutionGraph 和 Trace Schema。
2. 发布 LMCache 模式/操作 Capability Matrix。
3. 完成 `kv_ready`、dump 目录和直接 Redis 注入迁移说明。
4. 完成端到端场景：
   - 单知识文本/KV；
   - LMCache Lookup 驱动的本地/远端命中规划；
   - 网络准备与纯计算并行；
   - Hybrid；
   - 多块部分命中与非前缀融合；
   - Unsupported/STALE 回退；
   - KDN、LMCache Endpoint 和 Instance 重启；
   - 知识型策略调用 LMCache 操作。
5. 建立 KDN 不可用、LMCache 管理接口不可用、观测过期、任务中断、传输超时和 Generation 变化故障测试。
6. 统一 Benchmark：TTFT、吞吐、命中/重算 Token、Queue Breakdown、网络字节、Overlap、GPU Idle、Provider Operation Duration、Freshness、回退率和质量。
7. 对比串行、text_bypass、工作守恒、静态/自适应并发、LMCache Baseline 和知识型策略。
8. UI/Debug API 分离展示逻辑期望状态和 LMCache 观测状态。

### 发布标准

- LMCache 是唯一目标物理 KVCache 存储/传输平面；
- KDN 维护知识语义、Artifact Intent、策略和编排历史；
- Proxy KVCache Manager 基于 LMCache 公共查询/事件或明确标记的推断；
- 至少一种 LMCache 管理模式端到端可用；
- 不支持操作有结构化回退；
- 网络准备与独立计算安全并行；
- 队列具有 Single-flight、准入、背压、公平、取消、重试和回退；
- 至少两个知识块完成非前缀融合；
- 知识型策略相对 LMCache Baseline 有可复现实验；
- Legacy 路径兼容但与目标架构明确隔离。

## 8. 知识注入与计算队列研究框架

### 8.1 核心研究命题

> 当知识准备包含 LMCache Lookup、网络、存储和 Load 延迟，而模型计算包含 GPU 排队和执行延迟时，如何通过依赖感知、多资源队列编排，使缓存准备和纯计算最大化重叠，同时保证正确性、公平性和回退能力。

### 8.2 系统不变量

- 依赖未满足的计算不能提前执行；
- 无关任务不能被慢依赖阻塞；
- 共享准备只执行一次；
- 一个资源阻塞不能冻结其他资源；
- 取消、失败和超时沿图传播；
- 回退后不得重复注入；
- 预算、引用和任务状态最终一致；
- 相同输入、KDN Snapshot、LMCache Observation 和策略参数产生可复现计划。

### 8.3 策略接口

```text
AdmissionPolicy
PriorityPolicy
BypassPolicy
ConcurrencyPolicy
RetryPolicy
FallbackPolicy
ReleasePolicy
```

策略不能绕过状态机正确性，也不能伪造 LMCache 驻留状态。

### 8.4 评价指标

- TTFT、尾延迟、吞吐和完成时间；
- Network-Compute Overlap Ratio；
- GPU Idle Due to Cache Wait；
- Network Idle With Pending Work；
- LMCache Lookup/Prefetch/Load 时间；
- Queue Wait Breakdown；
- Pipeline/Serialized Makespan；
- Head-of-line Blocking；
- Text/KV/Hybrid 公平性；
- Single-flight 节省任务和字节；
- 观测 Freshness 和错误驻留率；
- 回退、取消、重试和泄漏率。

### 8.5 重点实验

1. 改变文本/KV/Hybrid 比例。
2. 改变带宽、RTT 和 LMCache 后端。
3. 改变知识块大小、命中率和观测新鲜度。
4. 单/多 KDN、Endpoint、Instance。
5. 均匀、突发、热点和长尾 Artifact。
6. 串行、text_bypass、静态并行、自适应并行。
7. 后台策略关闭/开启的在线干扰。
8. 多块顺序、共享和并行加载比例。

## 9. LMCache 集成与 KDN 接口框架

### 9.1 KDN 语义与策略接口

- Knowledge Catalog Query；
- Artifact Intent / Compatibility Query；
- Desired/Policy State Update；
- CachePlan Input Query；
- Maintenance Decision / Dry-run；
- Task Create/Cancel/Inspect；
- Event/Observation Ingest；
- Reconcile/Repair；
- Trace/Experiment Export。

### 9.2 LMCache Adapter 能力类别

- Capability/Configuration Discovery；
- Lookup 与命中 Token/位置；
- Worker/Instance/Endpoint Health；
- Object/Backend/Tier Status；
- Retrieve/Prefetch 与完成状态；
- Move/Copy；
- Pin/Unpin；
- Clear/Delete；
- KV Event；
- Runtime Metrics 和结构化错误。

### 9.3 Adapter 规则

- 使用 LMCache 公共 Controller、CacheEngine、MP HTTP/Coordinator 和 Plugin 接口；
- 能力协商，不假设模式完全一致；
- 明确返回 `unsupported/unknown/stale`；
- Provider 引用不透明且不含秘密；
- 不复制 LMCache Token Database、Chunk Index、Serde 和 Eviction；
- 新后端优先扩展 LMCache；
- Legacy 直接 Redis/文件行为隔离。

## 10. KDN 策略研究框架

### 10.1 输入

- Artifact Token、大小和构建成本；
- 近期/长期访问频率；
- 命中 Token 和 Prefill 节省；
- LMCache Lookup、网络、Load 和重算成本；
- 后端、层级、Instance 分布和观测置信度；
- 容量摘要、Quota、在线任务和预算；
- Pin、实验和租户约束；
- 多知识块共现；
- 预测值及其置信度。

### 10.2 输出

```text
MATERIALIZE / SKIP
KEEP_INTENT / RELEASE_INTENT
PIN / UNPIN
PREFETCH / CANCEL_PREFETCH
MOVE / COPY
CLEAR / DELETE
REFRESH / REBUILD
FALLBACK_TEXT
```

所有输出都必须经过 LMCache Adapter Capability 检查。

### 10.3 指标

- 请求 TTFT、尾延迟和吞吐；
- 命中 Token 和节省 GPU 时间；
- LMCache 容量利用率和缓存抖动；
- 网络传输与在线队列干扰；
- 预取准确率和污染率；
- Unsupported/Fallback 比例；
- 多块融合收益；
- 故障恢复和策略稳定性。

## 11. 状态边界

### KDN：知识语义和期望状态权威

维护 KnowledgeObject、Artifact 兼容性、Desired State、策略约束、Pin 意图和编排历史。

### LMCache：物理缓存事实权威

维护缓存对象/Chunk 存在、位置、层级、物理 Pin、Load/Save/Move/Clear、Worker Health 和后端错误。

### DataPlaneTask：CacheRoute 编排记录

记录请求的 LMCache 操作、Provider Task/Event ID、超时、重试和归一化结果，不替代 LMCache 执行状态。

### Proxy：短期请求和 Instance 观测

维护 CachePlan/FusionPlan/ExecutionGraph、共享任务和 TTL View。每条观测必须记录来源、时间、Freshness 和 Confidence。

### Instance/vLLM：模型执行事实

上报实际提交、Prefill/Decode、命中/重算 Token（若可用）和请求完成。

KDN Artifact 逻辑可用不等于物理驻留；Proxy View 过期不等于删除 LMCache 对象；策略成功不等于物理操作成功，必须等待 LMCache 确认。

## 12. 测试与实验要求

### 12.1 单元测试

- 不可变状态模型和非法转换；
- LMCache Adapter Capability Negotiation；
- Unsupported/Unknown/Stale；
- Desired/Observed Reconcile；
- Source/Freshness/Confidence/Expiry；
- ExecutionGraph 依赖、取消和回退；
- Single-flight 和 Query Coalescing；
- CachePlan/FusionPlan 确定性；
- Legacy 只读映射。

### 12.2 组件测试

- KDN + Mock LMCache Adapter；
- Controller/MP Adapter Fixture；
- Lookup/Status/Event 驱动的 Proxy View；
- KDN 或 LMCache Endpoint 重启；
- QueueCoordinator 多资源并行；
- Policy Dry-run 与 LMCache 结果区分；
- 不依赖私有 Redis Key 和序列化格式。

### 12.3 端到端测试

- vLLM + LMCache + CacheRoute 完整启动；
- 文本、前缀 KV、Hybrid、部分 KV、多块融合；
- LMCache Lookup 驱动规划；
- 网络准备与纯计算并行；
- 支持操作与 Unsupported 回退；
- 过期观测、Endpoint 故障和重启；
- Legacy 回归。

### 12.4 v0.1.10 回归门禁

- #138 Capability 测试继续通过；
- #139 模型不可变且存储中立；
- #140 Mock 反映 LMCache 操作语义；
- #141 Trace 标识 LMCache 来源；
- `test/test_kv_injector_reuse.py` 不在 pytest 收集阶段访问外部服务；
- CPU-only 测试不要求 GPU 或真实 LMCache Server。

### 12.5 实验复现

每个实验保存：

- 配置和代码版本；
- vLLM/LMCache 版本和模式；
- LMCache Storage/Transport Adapter；
- Workload Trace 和初始 KDN Catalog；
- 队列和策略参数；
- 请求级 ExecutionGraph；
- 原始 LMCache Observation/Event；
- 归一化 CacheRoute 记录；
- 汇总指标、回退原因和异常。

## 13. 版本依赖和并行开发

```text
v0.1.10
   |
v0.1.11  KDN Semantic Catalog
   |
v0.1.12  LMCache Integration Adapter
   |
v0.1.13  Desired/Observed Reconcile
   |
v0.1.14  Proxy LMCache-observed View
   |
v0.1.15  ExecutionGraph
   |
v0.1.16  Network/Compute Pipeline
   |
v0.1.17  Queue Stability
   +-------------------------+
   |                         |
v0.1.18 Policy          v0.1.19 Planning/Tooling
   |                         |
   +------------+------------+
                |
             v0.1.19
                |
             v0.2.0
```

并行建议：

- v0.1.10 同步冻结 Capability、State 和 Trace 词汇；
- v0.1.11 同步设计 LMCache Observation Schema；
- v0.1.12 同步开发 Mock、Controller 和 MP Adapter；
- v0.1.14 同步准备 ExecutionGraph 测试模型；
- v0.1.15–v0.1.17 持续建设串行/并行 Benchmark；
- v0.1.18 策略任务必须复用队列低优先级预算；
- v0.1.19 必须复用 ExecutionGraph，不建立第二套融合队列；
- 所有版本都不得重新引入 CacheRoute 物理 KV Store。

## 14. v0.2.0 之后

达到 v0.2.0 后，再基于可信知识语义、LMCache 物理事实和稳定队列反馈推进：

1. `kv_aware` Proxy Instance 路由；
2. KDN、Proxy、Instance 联合候选；
3. 分层 Pareto 筛选；
4. SLO 和不确定性感知调度；
5. LMCache MP/P2P 和高性能数据面；
6. Prefill/Decode 或 Encoder/Prefill/Decode 解耦；
7. 多租户配额、公平性和生产级高可用；
8. LMCache 新公共 API 的持续适配和 Legacy Adapter 淘汰。

这些能力必须建立在“CacheRoute 管知识和策略、LMCache 管物理缓存”的稳定边界上。