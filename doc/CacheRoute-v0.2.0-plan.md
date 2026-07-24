# CacheRoute v0.2.0 演进规划

> 状态：规划草案  
> 当前基线：v0.1.9  
> 目标版本：v0.2.0  
> 核心底座：vLLM + LMCache  
> 核心研究方向：KDN 控制/数据平面、知识型 KVCache 维护、Proxy KVCache Management、知识注入与计算队列并行、多知识块非前缀融合复用

## 1. 整体目标

CacheRoute v0.2.0 的目标不是重新实现一个 KVCache 存储系统，也不是优先引入复杂的全局调度算法，而是在 vLLM + LMCache 之上建立一套面向知识复用的控制、执行和维护框架。

v0.2.0 应形成以下完整闭环：

```text
知识注册
  -> KVCache 制品构建
  -> KDN 控制平面登记、校验和维护
  -> KDN 数据平面发布、传输和迁移
  -> Proxy 构建请求级 CachePlan / ExecutionGraph
  -> 知识准备队列与纯计算队列并行推进
  -> LMCache / vLLM 加载、复用、融合或选择性重计算
  -> 上报命中、排队、传输、加载、计算和质量结果
  -> KDN 根据反馈执行保留、淘汰、复制、迁移和预取
```

v0.2.0 重点建设五条相互依赖的主线。

### 1.1 KDN 控制平面

KDN 控制平面从当前“文本知识库 + KV dump 文件 + `kv_ready` 标记”的组合状态，演进为知识对象和 KVCache 制品的权威目录，负责：

- 区分 KnowledgeObject、CacheArtifact 和 CacheReplica；
- 维护制品兼容性、生命周期、位置、层级、容量和维护状态；
- 接收数据平面能力注册、健康状态和任务结果；
- 生成构建、发布、复制、迁移、预取和淘汰任务；
- 提供稳定、轻量、可版本化的查询与任务接口；
- 不承载大块 KV 数据传输，不在控制请求中携带 Redis 内部 Key、密码或大规模二进制内容。

### 1.2 KDN 数据平面

KDN 数据平面负责执行实际 KVCache 数据操作，允许独立扩展、替换和故障隔离：

- 执行 Artifact 发布、读取、传输、复制、迁移、校验和删除；
- 对接 LMCache、Legacy Redis、CPU、NVMe、P2P、NIXL、Mooncake 或其他运行时后端；
- 暴露统一 DataPlaneEndpoint 和异步 TransferTask；
- 返回实际字节数、排队时间、传输时间、来源/目标层级和错误类别；
- 支持多个 Data Worker 横向扩展，并由控制平面维护能力与负载摘要；
- 数据面失败不应破坏 KDN 目录服务，控制面失败也不应立即中断已经提交的数据任务。

### 1.3 知识注入与计算队列并行

这是 CacheRoute v0.2.0 的核心特色，也是区别于普通 KVCache 路由器的主要系统贡献。

Proxy 不应把“知识准备完成”简单视为所有请求进入计算前的统一串行屏障，而应显式建模并并行推进：

- KDN 元数据解析；
- 网络 KVCache 传输；
- LMCache 本地加载；
- 纯文本或残余 Token 的 Prefill 计算；
- Decode 执行；
- 多知识块的局部准备与融合依赖。

队列机制需要达到：

- 网络传输与其他请求的纯计算并行；
- 不依赖 KV 的文本任务能够走计算快速路径；
- KV 等待任务不阻塞可立即计算的任务；
- 同一 Artifact 的并发请求共享准备任务；
- 不同链路、不同 Instance 和不同资源类型可独立并发；
- 调度策略可插拔，但正确性、依赖关系和资源上限由统一队列底座保证；
- 在不同模型、带宽、存储后端、知识块数量和注入比例下仍具有普适性。

### 1.4 KDN KVCache 维护策略

KDN 在底座稳定后重点研究：

- 哪些知识值得构建和准入 KVCache；
- 容量受限时保留或淘汰哪些制品；
- 热点制品应复制到哪个 KDN、资源池、存储层级或 Instance 附近；
- 何时预取、迁移、刷新或重建；
- 如何利用 Proxy 队列反馈、网络成本、计算节省和多知识块共同出现关系；
- 如何避免缓存污染、维护抖动和后台任务干扰在线请求。

### 1.5 多知识块非前缀匹配与融合复用

v0.2.0 需要支持：

- 一个请求携带多个独立知识块；
- 在 Prompt 任意位置识别可复用知识，而不是只匹配连续前缀；
- 对完全命中、部分命中、重叠命中和顺序变化进行统一规划；
- 通过 LMCache 非前缀复用、CacheBlend 或等价能力执行融合；
- 对必要 Token 进行选择性重计算，避免直接拼接 KV 引入质量错误；
- 将多块加载任务接入知识准备队列并尽可能并行；
- 在运行时不支持、质量校验失败或执行异常时稳定回退到文本重算。

## 2. 总体要求与边界

### 2.1 角色边界

```text
Scheduler
- 选择目标 Proxy / KDN 资源池
- 保留知识感知和资源感知的全局候选能力
- 暂不承担细粒度 KV 生命周期、数据传输和队列执行

KDN Control Plane
- 维护知识、Artifact、Replica、策略和任务权威状态
- 生成并追踪数据面任务
- 只交换元数据、任务票据、能力摘要和结果

KDN Data Plane
- 执行实际 KV 数据发布、传输、复制、迁移、校验和删除
- 通过 Adapter 对接 LMCache 或其他后端
- 不负责全局维护策略和请求路由

Proxy
- 维护请求级和 Instance 级 KVCache 工作视图
- 构建 CachePlan、FusionPlan 和 ExecutionGraph
- 协调知识准备队列与计算队列
- 不成为全局 KVCache 元数据的权威数据库

Instance
- 作为 Proxy 与 vLLM / LMCache 之间的执行适配层
- 上报能力、缓存事件和执行结果
- 不承担全局缓存放置决策

LMCache
- 负责 KVCache 的实际存储、加载、传输、序列化和与 vLLM 的连接
- CacheRoute 不重复实现 LMCache 已提供的底层能力

vLLM
- 负责模型执行、Paged KV 管理和引擎内部调度
- Proxy 只控制请求何时满足依赖并提交，不侵入 vLLM 内部 Scheduler
```

### 2.2 KDN 控制与数据平面原则

1. 控制面 API 不直接承载 KVCache 大数据。
2. 控制面返回 Artifact、Replica、Endpoint、Lease 和 Task ID。
3. 数据面通过短期有效的任务票据或 Lease 执行操作。
4. Data Worker 可独立注册、下线和横向扩展。
5. 控制面只保存任务状态和结果摘要，不轮询或复制传输细节。
6. 数据面必须幂等；重复提交相同任务不会造成重复副本或破坏现有数据。
7. 控制面与数据面分别暴露健康状态、容量、队列和错误统计。
8. Legacy Redis 路径被封装为一种 DataPlane Adapter，而不是 KDN 唯一数据接口。

### 2.3 队列与执行原则

1. **依赖正确性优先**：请求只有在其必需依赖满足后才能进入对应计算阶段。
2. **工作守恒**：只要存在可执行任务且资源可用，队列协调器不应让该资源空闲。
3. **资源分离**：网络、Cache Load、Prefill 和 Decode 分别维护并发预算和时间线。
4. **避免队头阻塞**：慢 KV 任务不得阻塞不依赖它的文本或本地命中任务。
5. **Single-flight**：同 Artifact、同目标的重复准备合并为一个共享任务。
6. **事件驱动释放**：任务状态变化主动唤醒依赖者，避免高频轮询。
7. **可取消与可回退**：请求取消或超时时释放引用，并按策略切换到文本或部分复用。
8. **策略与机制分离**：队列底座保证状态机、依赖和资源安全；策略只决定优先级、配额和绕行规则。
9. **测量优先**：预测值和实际值分开记录，所有并行收益可被实验复现。
10. **兼容快速路径**：纯文本、单知识前缀 KV 和现有 IWS 路径均作为统一执行图的简单特例。

### 2.4 工程原则

- 每个版本可独立运行和验证，不以一次性重构替代连续迭代。
- 保留当前文本注入和 Redis 注入实验路径，直到替代路径通过端到端验证。
- 新字段默认可选，旧请求和旧 KDN 数据能够继续工作。
- 所有状态变化必须可观察，不能只在日志中隐式发生。
- 维护和队列策略必须可插拔、可关闭、可复现实验，不能散落在 API Handler 中。
- 运行时失败必须有明确降级路径，优先保证请求正确性。
- `demo_*.py` 只负责启动和参数解析，业务逻辑保留在正式模块中。

### 2.5 v0.2.0 范围内暂不优先实现

- 分层 Pareto 调度；
- 强化学习或 Bandit 在线决策；
- 完整 Prefill / Decode 解耦；
- 自研 RDMA 传输引擎；
- 强制全量迁移到 LMCache MP；
- 跨地域、多租户生产级控制面；
- 替代 LMCache 的 KV 存储实现。

复杂全局调度应在缓存对象、数据面任务、队列事件和维护反馈稳定之后再实现。

## 3. 现有工作基础

### 3.1 KDN 基础

当前 KDN 已具备：

- SQLite 文本知识索引和基于内容哈希的 `kid`；
- 文本、Embedding、长度和 KV 状态元数据；
- `KV_database/<kid>`、Manifest 和 KV dump；
- 文本注册、查询、删除、快照和 KV 构建接口；
- 将 dump 内容写入目标 Redis 的 Legacy 注入路径；
- KDN 注册、心跳、网络队列模拟和基础传输统计。

主要限制：

- 控制 API、目录状态、文件管理和数据传输集中在同一服务；
- 一个 `kid` 只能表达一套粗粒度 KV 状态；
- `kv_ready` 无法表达构建中、传输中、失败、过期和删除中；
- KV dump、SQLite 和远端后端可能不一致；
- KDN 直接依赖 LMCache Redis Key 和序列化格式；
- 数据任务缺乏独立 Worker、能力注册、Lease、恢复和故障隔离；
- 没有副本、层级、容量、访问统计和维护策略。

### 3.2 Proxy 与队列基础

当前 Proxy 已具备：

- 本地 Instance 池和 `round_robin`、`least_load` 策略接口；
- Proxy 维护的 `inflight`、队列深度和预测 backlog；
- prepare / ready 双队列和每 Instance 预留时间线；
- KDN 文本查询与 `kv_ready` / `text_only` / `miss` 分类；
- KDN 到 Instance 的 KV 传输预测和链路预留；
- `ProxyTask` 中的缓存状态和请求 Trace；
- `ordered` / `text_bypass` Ready 释放策略；
- IWS 文本与 KVCache 注入决策基础。

现有机制已经证明 CacheRoute 可以显式管理“知识准备”和“计算等待”，但仍存在：

- prepare 阶段包含多种资源需求，却主要表现为一条粗粒度队列；
- 网络传输、LMCache Load、Prefill 和 Decode 的依赖与资源预算尚未统一建模；
- 文本绕行只是局部释放规则，还不是通用的工作守恒多队列机制；
- 网络 KV 任务和纯计算任务的并行收益缺少稳定指标和实验基线；
- 同一 Artifact 的重复加载、任务取消、重试和共享等待仍需系统化；
- 多知识块仅分类后拼接文本，没有 ExecutionGraph 和 FusionPlan；
- Proxy 缺少统一 KVCache Manager 与 Instance 级缓存视图。

### 3.3 vLLM + LMCache 基础

CacheRoute 已经能够通过 vLLM + LMCache + Redis 完成 KVCache 构建和复用实验。后续继续利用 LMCache 提供的：

- vLLM KV Connector；
- 外部 KV 命中 Token 查询；
- 异步加载和保存；
- CPU、磁盘、Redis、P2P 或其他后端；
- 非前缀复用和 CacheBlend 类能力；
- KV 事件和运行时观测。

v0.2.0 的关键不是更换底层，而是建立稳定的 CacheRoute 控制与执行接口，使 KDN 和 Proxy 不绑定某个 LMCache 后端的内部表示。

## 4. v0.2.0 目标架构

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

## 5. 核心对象与执行模型

### 5.1 KnowledgeObject

表示与模型无关的知识内容：

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

表示特定模型和运行配置下生成的 KVCache 制品：

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

表示一个 Artifact 的具体可访问位置：

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

ExecutionGraph 是 Proxy 队列机制的统一输入。每个节点表示一项工作，每条边表示依赖：

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

推荐的 `resource_class`：

```text
CONTROL        KDN 查询、计划解析
NET_KV         网络 KVCache 传输
CACHE_LOAD     LMCache 本地加载与确认
PREFILL        纯文本或残余 Token 计算
DECODE         Decode 占用与完成跟踪
FUSION         多块融合与选择性重计算准备
```

## 6. 迭代总览

| 版本 | 主题 | 主要交付 |
|---|---|---|
| v0.1.10 | 契约与观测基线 | 兼容性指纹、控制/数据平面契约、Queue Trace |
| v0.1.11 | KDN 控制平面目录 | KnowledgeObject / Artifact / Replica / Task Registry |
| v0.1.12 | KDN 数据平面底座 | Data Worker、Runtime Adapter、Task Ticket、能力注册 |
| v0.1.13 | KDN 生命周期与恢复 | 原子发布、Reconcile、控制/数据平面故障隔离 |
| v0.1.14 | Proxy KVCache Manager | Instance 缓存视图、CachePlan、Single-flight 基础 |
| v0.1.15 | 注入与计算队列模型 | ExecutionGraph、资源队列、依赖释放、计算快速路径 |
| v0.1.16 | 网络与计算并行流水线 | 工作守恒并行、链路/Instance 时间线、Overlap Benchmark |
| v0.1.17 | 队列机制普适性与稳定性 | 准入、背压、公平、老化、自适应并发和故障回退 |
| v0.1.18 | KDN 维护策略 | TTL/LRU、价值、复制、迁移、预取和 Trace Replay |
| v0.1.19 | 多知识块非前缀融合 | 匹配规划、并行准备、选择性重计算和质量回退 |
| v0.2.0 | 集成与稳定发布 | 完整闭环、故障测试、基准、稳定接口和研究基线 |

## 7. 分版本规划

## v0.1.10：契约与观测基线

### 拟解决的问题

后续所有能力依赖统一对象身份、兼容性、控制/数据平面任务语义和队列阶段 Trace。

### 主要步骤

1. 定义模型、Tokenizer、Adapter、KV 布局、精度和并行配置指纹。
2. 扩展 Instance 注册，上报 vLLM、LMCache 和 KV 能力。
3. 定义 Artifact、Replica、DataPlaneTask 和 Queue Work 状态枚举。
4. 定义 KDN 控制面与数据面的版本化协议：
   - Endpoint 注册；
   - 任务提交；
   - Lease；
   - 状态查询；
   - 结果回报；
   - 幂等键。
5. 统一请求 Trace：
   - KDN 查询；
   - 计划构建；
   - 控制面等待；
   - 网络队列与传输；
   - Cache Load；
   - Prefill 排队与计算；
   - Decode；
   - 融合与回退。
6. 增加 `predicted_*`、`actual_*` 和 `source` 字段，避免混淆预测与测量。
7. 旧 `kv_ready`、旧请求和旧 Redis 路径保持兼容。

### 验收标准

- 不兼容 Instance 或 Artifact 能被识别；
- 控制/数据平面消息具有明确版本；
- 单请求能输出知识准备和计算阶段的稳定时间分解；
- 不改变当前注入决策和转发结果。

## v0.1.11：KDN 控制平面目录

### 拟解决的问题

当前知识记录、KV 状态和文件位置耦合，无法支持多模型 Artifact、多副本和独立数据面。

### 主要步骤

1. 保留 Legacy 表，新增或抽象 KnowledgeObject、CacheArtifact、CacheReplica、DataPlaneEndpoint 和 Task Registry。
2. 建立一个 KnowledgeObject 对多个 Artifact、一个 Artifact 对多个 Replica 的关系。
3. 生成稳定 Artifact ID 和 Replica ID。
4. 将 `KV_database/<kid>` 映射为 Legacy Artifact / Replica，不立即移动文件。
5. 扩展查询接口：
   - 按知识和兼容性查 Artifact；
   - 查 Replica 和 DataPlaneEndpoint；
   - 查容量、状态和任务；
   - 保留文本查询接口。
6. Snapshot 只向 Scheduler 暴露粗粒度可用性，不传播大规模副本细节。
7. 增加迁移、目录校验和 Debug API。

### 验收标准

- 同一知识可登记多个模型或配置的 Artifact；
- 同一 Artifact 可登记多个数据面副本；
- 旧 `kv_ready` 可映射到 Legacy Artifact；
- 控制平面查询不要求访问 KV dump 内容。

## v0.1.12：KDN 数据平面底座

### 拟解决的问题

KDN 当前服务同时处理目录、文件和 Redis 注入，难以替换后端、独立扩展或隔离传输故障。

### 主要步骤

1. 定义 Data Worker 生命周期和能力注册。
2. 定义 Cache Runtime Adapter：
   - query；
   - publish；
   - transfer / prefetch；
   - wait / cancel；
   - verify；
   - evict；
   - collect stats。
3. 实现 LMCache Runtime Adapter，优先使用公开接口、事件或 CLI。
4. 将现有 Redis 注入封装为 LegacyRedisAdapter。
5. 控制面创建 DataPlaneTask，返回 Task Ticket / Lease，不再传递大数据和 Redis 密码给 Proxy。
6. Data Worker 执行任务并主动上报结果；支持幂等、重试和取消。
7. 支持多个 Worker 注册同类后端，并报告容量、并发、队列和健康。
8. 提供 Mock Adapter 和故障注入，用于无 GPU CI。

### 验收标准

- 控制面和数据面可作为独立进程运行；
- Proxy 不需要理解 LMCache Redis Key；
- 同一任务重复提交不会生成重复副本；
- Data Worker 失败返回结构化错误；
- Legacy Redis 路径仍可回归。

## v0.1.13：KDN 生命周期、一致性与恢复

### 拟解决的问题

目录、文件和后端副本可能不一致，控制/数据平面重启或任务中断可能留下错误 READY 状态。

### 主要步骤

1. 实现 Artifact、Replica 和 DataPlaneTask 状态机。
2. 使用两阶段发布：BUILDING -> STAGING -> READY。
3. 使用 Checksum、大小、Manifest 和 Schema Version 校验。
4. 实现 Reconcile：
   - 元数据有记录但数据缺失；
   - 数据存在但元数据无记录；
   - 未完成任务、临时目录和过期 Lease；
   - Worker generation 变化；
   - Replica 损坏和孤儿数据。
5. 控制面重启后恢复任务状态；数据面重连后报告未完成任务。
6. 删除使用 DELETING 并等待引用和任务释放。
7. 控制面不可用时，已授权任务可在 Lease 范围内完成；数据面不可用时目录查询保持可用。
8. 暴露恢复统计、最近失败和人工 Reconcile 工具。

### 验收标准

- 构建中对象不会被错误复用；
- 控制面和数据面独立重启后可恢复一致状态；
- 人工损坏副本后能阻止复用；
- 重复任务和过期 Lease 可被清理；
- 删除失败不会产生虚假可用对象。

## v0.1.14：Proxy KVCache Manager

### 拟解决的问题

Proxy 缺少统一 Instance 缓存视图、请求 CachePlan 和共享准备任务管理。

### 主要步骤

1. 引入 Proxy KVCache Manager：
   - Artifact 摘要缓存；
   - 每 Instance 可访问、加载中、已加载、失败和过期视图；
   - DataPlaneTask / Cache Load Task 映射；
   - CachePlan / FusionPlan 管理；
   - LMCache / Instance 事件接收。
2. 定义本地状态 UNKNOWN、AVAILABLE_REMOTE、TRANSFERRING、LOADING、AVAILABLE_LOCAL、FAILED、EXPIRED。
3. 将 `ProxyTask` 的缓存字段收敛到 `cache_plan` 与 `cache_trace`，保留兼容镜像。
4. 实现同 Artifact、同目标 Instance 的 Single-flight。
5. Instance 重启、generation 变化或注销时使本地视图失效。
6. 增加 CachePlan、缓存视图、共享任务和错误 Debug API。

### 验收标准

- Proxy 能区分全局存在、传输中、目标可加载和已本地可用；
- 同一目标的并发请求共享准备任务；
- Instance 重启后不误用旧状态；
- 当前文本和单知识 KV 路径保持兼容。

## v0.1.15：知识注入与计算队列模型

### 拟解决的问题

现有 prepare / ready 双队列缺少对控制、网络、Cache Load 和计算依赖的统一表达，无法系统性避免慢 KV 导致的队头阻塞。

### 主要步骤

1. 将 CachePlan 编译为 ExecutionGraph。
2. 定义独立工作队列或逻辑队列：
   - CONTROL Resolve Queue；
   - NET_KV Transfer Queue；
   - CACHE_LOAD Queue；
   - PREFILL Compute Queue；
   - DECODE Tracking Queue；
   - FUSION Prepare Queue。
3. QueueCoordinator 维护节点依赖、引用数、取消传播和事件唤醒。
4. 纯文本和本地命中任务使用 Compute Fast Path，不进入远端 KV 等待。
5. 保留 prepare / ready 外部语义，但内部由 ExecutionGraph 决定何时 Ready。
6. 为每个资源类建立独立并发预算和基本时间线。
7. 同一共享准备节点完成时批量唤醒所有等待请求。
8. 记录每个节点的排队、执行、等待依赖和阻塞原因。
9. 为旧 `ordered` / `text_bypass` 提供兼容映射。

### 验收标准

- 文本任务不再被无关慢 KV 任务阻塞；
- 同一请求依赖未满足时不会被错误提交计算；
- 共享任务仅执行一次；
- 取消请求能够正确释放图节点引用；
- ExecutionGraph 可通过 Debug API 查看和复现。

## v0.1.16：网络 KVCache 与纯计算并行流水线

### 拟解决的问题

建立队列模型后，需要真正让网络数据准备和 GPU 计算重叠，减少 GPU 等待 KV、网络等待提交和串行屏障造成的空闲。

### 主要步骤

1. 实现工作守恒 QueueCoordinator：
   - 网络可用时持续发起 NET_KV；
   - Prefill 资源可用时持续释放可计算任务；
   - 一个资源阻塞不阻塞其他资源类。
2. 建立独立时间线：
   - 每 KDN/DataPlane 链路；
   - 每目标 Instance Cache Load；
   - 每 Instance Prefill Slot；
   - Decode 占用摘要。
3. 支持网络传输与其他请求 Prefill/Decode 并行。
4. 支持同请求多个知识块在不同链路或 Worker 上并行准备。
5. 支持 Transfer Coalescing 和 Single-flight，减少小任务开销与重复字节。
6. 支持有限 Look-ahead：在计算队列仍有可执行任务时提前准备后续 KV，但受带宽和内存预算约束。
7. 使用事件驱动唤醒，不使用固定间隔轮询作为主要释放机制。
8. 定义并测量：
   - network-compute overlap ratio；
   - GPU idle due to cache wait；
   - network idle with queued transfer；
   - serialized baseline time；
   - pipeline makespan；
   - overlap saved time；
   - TTFT 和吞吐变化。
9. 建立序列化、简单 text_bypass 和完整并行三组对比基线。

### 验收标准

- KV 传输期间其他可计算请求能够持续执行；
- 多链路和多 Instance 不被一个全局锁串行化；
- 工作负载存在并行机会时，Pipeline Makespan 优于序列化基线；
- 并行机制不会破坏请求顺序约束和响应正确性；
- 并行收益能通过 Trace 和 Benchmark 重复验证。

## v0.1.17：队列机制普适性、稳定性与策略接口

### 拟解决的问题

仅实现并行不足以适应不同模型、后端、带宽和注入比例；还需要准入、背压、公平性、故障处理和自适应并发。

### 主要步骤

1. 建立分层准入与背压：
   - 请求总量；
   - 每 Instance；
   - 每链路；
   - 每 Data Worker；
   - 每租户或实验组可选预算。
2. 支持优先级、Aging、Deadline Hint 和 Starvation Protection。
3. 支持大 KV 任务分片或让行，避免长期占据链路。
4. 支持文本、KV、Hybrid 和多块 Fusion 的统一队列策略接口。
5. 支持自适应并发：根据实际吞吐、排队和错误率调整 Transfer / Load 并发，但保留静态模式用于实验。
6. 建立回退与熔断：
   - KDN 控制面不可用；
   - Data Worker 过载；
   - 网络超时；
   - LMCache Load 失败；
   - Instance 下线；
   - 重试预算耗尽。
7. 明确重试优先级不能无限高于新请求，避免重试风暴。
8. 暴露策略插件：Priority Policy、Bypass Policy、Concurrency Policy、Admission Policy。
9. 建立普适性实验矩阵：
   - 不同模型与 KV 大小；
   - 单/多 KDN；
   - 单/多 Instance；
   - 低/高带宽与不同 RTT；
   - 文本/KV/Hybrid 比例；
   - 均匀、突发、热点和长尾工作负载。
10. 以机制稳定为目标，不在本版本引入 Pareto 或学习型全局调度。

### 验收标准

- 高 KV 负载下文本任务不会永久饥饿；
- 高文本负载下 KV 任务也能获得可配置服务份额；
- 过载时队列有明确拒绝、降级或背压结果；
- 故障不会造成永久挂起、引用泄漏或无限重试；
- 同一机制能覆盖单知识、Hybrid 和多知识准备场景；
- 实验可以独立切换策略并复现结果。

## v0.1.18：KDN KVCache 维护策略

### 拟解决的问题

在目录、数据面和队列反馈稳定后，KDN 可以安全研究缓存准入、淘汰、复制、迁移和预取。

### 主要步骤

1. 建立统一访问和收益统计：命中次数、命中 Token、节省 Prefill、传输成本、队列等待、失败和引用。
2. 建立 Backend / Tier 容量、水位、预留和可回收模型。
3. 实现准入、TTL、LRU、Pin 和安全淘汰基线。
4. 实现至少一种可解释的价值感知策略，与 LRU 对比。
5. 支持热点副本、层级提升/下沉、失败回滚和最后副本保护。
6. 支持受预算约束的预取，并利用 Proxy 目标 Instance、队列空闲窗口和历史序列。
7. 后台维护任务使用独立低优先级预算，不与在线 NET_KV 无约束竞争。
8. 提供 Dry-run 和 Trace Replay，离线比较命中率、容量、传输量、计算节省和队列干扰。
9. 将多知识块共同出现关系作为可选特征，为 v0.1.19 提供基础。

### 验收标准

- TTL/LRU 和至少一种价值感知策略可配置切换；
- 活跃引用、hard pin 和最后一个健康副本不会被错误删除；
- 后台维护不会导致在线队列失控；
- 热点副本和预取决策可追踪；
- Trace Replay 能生成可比较结果。

## v0.1.19：多知识块非前缀融合

### 拟解决的问题

当前多个知识块主要按文本拼接处理，不能表达非前缀、部分命中、重叠和多来源准备。

### 主要步骤

1. 将请求知识表示为有序 Knowledge Block 列表，并构建 Prompt Layout。
2. 查询每个块的兼容 Artifact 与 Replica。
3. 实现完全、部分、非前缀、重叠和未命中分类。
4. 构建 Coverage Map，避免同一 Token 重复覆盖。
5. 生成 FusionPlan：Artifact、来源、目标、重算区间、顺序、回退和风险。
6. 将 FusionPlan 编译为 ExecutionGraph：
   - 多块可以并行传输；
   - 同一 Artifact 共享任务；
   - 依赖局部满足后触发后续节点；
   - 融合前确保必需块完成。
7. 适配 LMCache 非前缀复用、CacheBlend 或等价公开接口。
8. 支持选择性重计算和质量保护。
9. 不支持或失败时依次降级为单前缀 KV、部分 KV + 文本、全文本。
10. 建立多块数量、顺序、命中比例、网络层级和重算比例实验。

### 验收标准

- 至少支持两个知识块的非前缀融合复用；
- 多块准备能利用队列并行且不会形成重复任务风暴；
- 实际命中 Token、重算 Token、传输和融合开销可观察；
- 质量或运行时异常能够正确回退；
- 与纯文本和单前缀基线相比能输出正确、可重复的结果。

## v0.2.0：集成、稳定与研究基线发布

### 主要步骤

1. 冻结 KnowledgeObject、CacheArtifact、CacheReplica、DataPlaneEndpoint、DataPlaneTask、CachePlan、FusionPlan、ExecutionGraph 和 Trace Schema。
2. 完成 Legacy `kv_ready` 与 Redis 注入迁移和弃用说明。
3. 完成端到端场景：
   - 单知识文本；
   - 单知识 KV；
   - 网络 KV 与纯计算并行；
   - Hybrid 混合负载；
   - 多知识部分命中与非前缀融合；
   - KDN/Data Worker/LMCache 故障回退；
   - KDN 重启恢复；
   - Instance 重启与本地状态失效；
   - 水位触发维护策略。
4. 建立故障测试：控制面不可用、数据面不可用、任务中断、文件损坏、传输超时、Instance 下线、淘汰并发和迁移失败。
5. 建立统一 Benchmark：
   - TTFT P50/P95/P99 和吞吐；
   - KV 命中 Token 率、残余 Prefill；
   - 网络字节、队列等待和传输时间；
   - 网络/计算利用率与 Overlap Ratio；
   - GPU Cache-wait Idle；
   - Pipeline Makespan 与序列化基线；
   - 缓存容量、写放大、维护次数；
   - 回退率、错误率、融合收益和质量。
6. 提供策略基线：
   - 串行准备；
   - text_bypass；
   - 工作守恒并行；
   - 静态与自适应并发；
   - 无维护、TTL、LRU、价值感知；
   - 无融合、前缀复用、非前缀融合。
7. 补齐架构、KDN 平面、队列机制、维护策略、Fusion、部署、迁移和实验复现文档。
8. Proxy UI 和 KDN Debug API 能展示任务图、资源队列、数据面状态和关键并行指标；完整 KDN 前端不作为阻塞项。
9. 所有实验能力可独立启停，默认值和错误组合提示明确。

### v0.2.0 发布标准

- KDN 控制面与数据面可独立部署、扩展和恢复；
- KDN 能可靠维护多模型、多配置 Artifact 和多副本；
- Proxy 有独立 KVCache Manager、CachePlan 和 ExecutionGraph；
- 网络 KVCache 传输可与无依赖的纯计算任务并行；
- 队列机制具备 Single-flight、准入、背压、公平、取消、重试和回退；
- 至少支持两个知识块的非前缀融合；
- KDN 至少提供 TTL/LRU 和一种价值感知维护策略；
- vLLM / LMCache 执行细节通过 Adapter 隔离；
- 当前文本、单知识和 Legacy 路径保持兼容；
- 关键故障场景有自动测试或可重复脚本；
- 队列并行、维护策略和融合能力均有可复现实验结果。

## 8. 知识注入与计算队列研究框架

### 8.1 核心研究命题

CacheRoute 的差异化能力不是简单选择文本还是 KV，而是：

> 在知识准备具有网络、存储和加载延迟，而模型计算具有 GPU 排队和执行延迟的条件下，如何通过依赖感知、多资源队列编排，使知识传输、缓存加载和纯计算最大化重叠，同时保证正确性、公平性和可回退性。

### 8.2 必须保证的系统不变量

- 依赖未满足的计算不能提前执行；
- 不依赖慢任务的工作不能被无关依赖阻塞；
- 共享准备任务只执行一次；
- 任一资源类的阻塞不应冻结其他资源类；
- 取消、失败和超时必须沿依赖图传播；
- 回退后不得重复注入相同知识；
- 资源预算、引用数和任务状态最终一致；
- 相同输入、目录快照和策略参数应产生可复现计划。

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

策略输入包括：任务类型、依赖、预计成本、实际队列、链路、Instance、缓存状态、Deadline Hint 和实验标签。策略输出只能调整优先级、预算、是否绕行、是否回退和并发，不能绕过状态机正确性。

### 8.4 关键评价指标

- TTFT 和尾延迟；
- 吞吐和完成时间；
- Network-Compute Overlap Ratio；
- GPU Idle Due to Cache Wait；
- Network Idle With Pending Work；
- Queue Wait Breakdown；
- Pipeline Makespan / Serialized Makespan；
- Head-of-line Blocking Time；
- Text、KV 和 Hybrid 的公平性；
- Single-flight 节省任务数和字节；
- 回退、取消、重试和任务泄漏率。

### 8.5 重点实验

1. 固定请求数，改变文本/KV 比例。
2. 固定计算能力，改变链路带宽和 RTT。
3. 固定网络，改变知识块大小和命中率。
4. 单 KDN 单 Instance 到多 KDN 多 Instance。
5. 均匀、突发、热点和长尾 Artifact。
6. 串行、text_bypass、静态并行和自适应并行。
7. 后台维护关闭与开启时的在线干扰。
8. 多知识块顺序、共享和并行加载比例。

## 9. KDN 控制与数据平面接口框架

### 9.1 控制面接口类别

- Catalog Query；
- Artifact / Replica Lifecycle；
- DataPlane Registration / Heartbeat；
- Task Create / Cancel / Inspect；
- Lease Issue / Renew / Expire；
- Maintenance Decision / Dry-run；
- Event / Result Ingest；
- Reconcile / Repair。

### 9.2 数据面接口类别

- Publish；
- Fetch / Prefetch；
- Copy / Replicate；
- Promote / Demote；
- Verify；
- Delete；
- Task Status / Result；
- Runtime Metrics。

### 9.3 分离带来的灵活性

- LMCache 后端变化不要求改 KDN 目录模型；
- 单一 KDN 控制面可管理多个异构 Data Worker；
- Data Worker 可部署在 KDN 节点、Proxy 资源池或 Instance 附近；
- 不同传输后端可按能力和部署环境切换；
- 维护策略只生成任务，不直接操作后端；
- 网络实验可替换 DataPlane Adapter，而不污染控制 API；
- 控制面和数据面可以独立压测、故障注入和扩容。

## 10. KDN 维护策略研究框架

### 10.1 策略输入

- Artifact 大小、Token 数和构建成本；
- 近期与长期访问频率；
- 命中 Token 和实际节省 Prefill；
- 网络队列、传输、Cache Load 和选择性重计算开销；
- 存储层级、目标 Instance 分布和副本故障域；
- 容量水位、在线任务和维护预算；
- Pin、实验和租户约束；
- 多知识块共同出现关系；
- 预测值及置信度。

### 10.2 策略输出

```text
ADMIT / REJECT_BUILD
KEEP / EVICT
PIN / UNPIN
REPLICATE / REMOVE_REPLICA
PROMOTE_TIER / DEMOTE_TIER
PREFETCH / CANCEL_PREFETCH
REFRESH / REBUILD
```

### 10.3 评价指标

- 请求 TTFT、尾延迟和吞吐；
- KV 命中 Token 和节省 GPU 时间；
- 容量利用率、写放大和缓存抖动；
- 网络传输量和在线队列干扰；
- 预取准确率和污染率；
- 多知识块融合收益；
- 故障恢复和策略稳定性。

## 11. Proxy、KDN 与运行时状态边界

### KDN 控制平面是全局权威状态

维护 Artifact 完整性、兼容性、Replica、容量、Pin、策略、任务和全局访问统计。

### KDN 数据平面是数据任务事实来源

维护实际数据操作进度、字节、来源/目标、后端错误和最终结果。

### Proxy 是短期执行状态

维护目标 Instance 可访问性、共享准备任务、CachePlan/FusionPlan/ExecutionGraph、短期负缓存、队列状态和反馈缓冲。

### Instance / LMCache 是加载与命中的运行时事实来源

提供实际命中 Token、加载完成、Block 错误、存储事件和异步保存完成。

KDN 返回 `READY` 不等于目标 Instance 已加载完成；Proxy 短期视图失效也不等于全局 Artifact 应被删除。

## 12. 测试与实验要求

### 12.1 单元测试

- Artifact / Replica / Task 状态机；
- 控制/数据平面协议和幂等键；
- ExecutionGraph 依赖、取消和回退；
- Single-flight；
- 队列优先级、Aging、公平和背压；
- CachePlan / FusionPlan 确定性；
- Trace 字段和兼容解析。

### 12.2 组件测试

- KDN 目录与 Data Worker 独立启动；
- Runtime Adapter Mock；
- 控制面或数据面单独重启恢复；
- Proxy KVCache Manager；
- QueueCoordinator 多资源并行；
- Maintenance Dry-run 与执行；
- LMCache 事件接入。

### 12.3 端到端测试

- vLLM + LMCache + CacheRoute 完整启动；
- 文本、前缀 KV、Hybrid、部分 KV 和多块融合；
- 网络传输与纯计算并行；
- 自动淘汰、复制、迁移和预取；
- 故障回退和重启恢复。

### 12.4 实验复现

每个实验保存：

- 配置文件和代码版本；
- 模型、LMCache 和 vLLM 版本；
- 工作负载 Trace；
- KDN 初始状态和 Data Worker 拓扑；
- 队列与维护策略参数；
- 请求级 ExecutionGraph 和结果；
- 汇总指标和异常记录。

## 13. 版本依赖与并行开发建议

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

可并行工作：

- v0.1.10 同步准备 Trace Schema 和能力指纹；
- v0.1.11 同步开发目录迁移工具；
- v0.1.12 同步开发 Mock Data Worker；
- v0.1.14 同步准备 ExecutionGraph 测试模型；
- v0.1.15–v0.1.17 同步建立序列化与并行 Benchmark；
- v0.1.17 后可并行设计维护策略接口和多知识块工作负载；
- v0.1.18 的后台任务必须复用 v0.1.17 的低优先级预算和背压；
- v0.1.19 必须复用 ExecutionGraph，不建立第二套融合队列。

## 14. v0.2.0 之后

达到 v0.2.0 后，再基于稳定的缓存事实、数据任务和队列反馈推进：

1. `kv_aware` Proxy Instance 路由；
2. KDN、Proxy、Instance 联合候选选择；
3. 分层 Pareto 筛选；
4. SLO 和不确定性感知调度；
5. LMCache MP / P2P 与高性能数据面；
6. Prefill / Decode 或 Encoder / Prefill / Decode 解耦；
7. 多租户配额、公平性和生产级高可用。

这些能力应建立在 v0.2.0 提供的可信控制面、可替换数据面和知识/计算并行队列之上。