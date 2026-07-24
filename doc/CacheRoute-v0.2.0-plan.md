# CacheRoute v0.2.0 演进规划

> 状态：规划草案  
> 当前基线：v0.1.9  
> 目标版本：v0.2.0  
> 核心底座：vLLM + LMCache  
> 核心研究方向：KDN KVCache 维护策略、Proxy KVCache Management、多知识块非前缀匹配与融合复用

## 1. 整体目标

CacheRoute v0.2.0 的目标不是实现一个新的 KVCache 存储系统，也不是优先引入复杂的全局调度算法，而是在现有 vLLM + LMCache 基础上建立一套可持续研究和演进的知识型 KVCache 管理框架。

v0.2.0 需要形成以下完整闭环：

```text
知识注册
  -> KVCache 制品构建
  -> KDN 统一登记与生命周期维护
  -> Proxy 获取请求级缓存视图
  -> 生成 KVCache 准备与融合计划
  -> LMCache / vLLM 执行加载、复用或选择性重计算
  -> 上报命中、传输、加载、计算和质量结果
  -> KDN 根据反馈执行保留、淘汰、复制、迁移和预取
```

重点建设三条主线。

### 1.1 KDN Server KVCache 管理底座

KDN Server 从当前“文本知识库 + KV dump 文件 + `kv_ready` 标记 + Redis 注入服务”演进为 KVCache 的全局目录和维护控制面，负责：

- 区分知识对象与模型相关的 KVCache 制品；
- 维护制品状态、存储位置、副本、存储层级和兼容性；
- 提供可恢复、可校验、可观测的生命周期管理；
- 承载缓存准入、淘汰、保留、复制、迁移和预取策略；
- 向 Scheduler、Proxy 和运维工具提供稳定的查询与任务接口；
- 将实际 KV 数据读写交给 LMCache 或其他可插拔运行时后端。

### 1.2 Proxy KVCache Management

Proxy 不复制 KDN 的全局元数据职责，而是维护请求执行所需的局部 KVCache 状态，负责：

- 维护各 Instance 可访问、正在加载和近期使用的缓存视图；
- 将请求的多个知识块转换为可执行的缓存准备计划；
- 协调 KDN 查询、LMCache 预取、加载确认、失败回退和请求释放；
- 将缓存准备过程纳入现有 prepare / ready 队列和时间线；
- 记录请求级缓存命中、等待、传输、加载、残余 Prefill 和融合结果；
- 为后续 `kv_aware` 路由及更复杂调度提供稳定数据，但不在本阶段强制实现 Pareto 调度。

### 1.3 多知识块非前缀匹配与融合复用

现有流程主要把多个知识块拼接成文本，并依赖前缀形式的 KVCache 命中。v0.2.0 需要支持：

- 一个请求携带多个独立知识块；
- 在 Prompt 任意位置识别可复用知识块，而不是只匹配连续前缀；
- 对完全命中、部分命中、重叠命中和顺序变化进行统一规划；
- 通过 LMCache 的非前缀复用、CacheBlend 或等价能力执行融合；
- 对必要 Token 进行选择性重计算，避免直接拼接 KV 引入质量错误；
- 在融合不可用、质量校验失败或运行时异常时稳定回退到文本重算。

## 2. 总体要求与边界

### 2.1 角色边界

v0.2.0 应保持以下职责边界：

```text
Scheduler
- 选择目标 Proxy / KDN 资源池
- 保留知识感知和资源感知的全局候选能力
- 暂不承担细粒度 KVCache 生命周期和融合执行

KDN Server
- 维护知识对象、KVCache 制品、副本和策略状态
- 执行缓存维护策略和后台任务
- 不承载 vLLM 推理
- 长期不依赖直接写入 LMCache 内部 Redis Key 作为唯一接口

Proxy
- 维护请求级和 Instance 级 KVCache 工作视图
- 生成、执行和观察缓存准备计划
- 不成为全局 KVCache 元数据的权威数据库

Instance
- 作为 Proxy 与 vLLM / LMCache 之间的执行适配层
- 上报能力、缓存事件和执行结果
- 不承担全局缓存放置决策

LMCache
- 负责 KVCache 的实际存储、加载、传输、序列化和与 vLLM 的连接
- CacheRoute 不重复实现 LMCache 已提供的数据面能力

vLLM
- 负责模型执行、Paged KV 管理和推理调度
```

### 2.2 工程原则

所有迭代应满足：

1. 每个版本可独立运行和验证，不以一次性大重构替代连续迭代。
2. 保留当前文本注入和 Redis 注入实验路径，直到替代路径通过端到端验证。
3. 新字段默认可选，旧请求和旧 KDN 数据能够继续工作。
4. 所有状态变化必须可观察，不能只在日志中隐式发生。
5. 维护策略必须可插拔、可关闭、可复现实验，不能散落在 API Handler 中。
6. 运行时失败必须有明确降级路径，优先保证请求正确性。
7. 将预测值与实际值分开记录，避免用模拟值冒充运行时测量。
8. `demo_*.py` 只负责启动和参数解析，业务逻辑保留在正式模块中。

### 2.3 v0.2.0 范围内暂不优先实现

以下能力可以保留接口和数据准备，但不作为 v0.2.0 发布阻塞项：

- 分层 Pareto 调度；
- 强化学习或 Bandit 在线决策；
- 完整 Prefill / Decode 解耦；
- 自研 RDMA 传输引擎；
- 全量迁移到 LMCache MP 模式；
- 跨地域、多租户生产级控制面；
- 替代 LMCache 的 KV 存储实现。

Pareto 调度应在缓存对象、运行时事件和策略反馈稳定之后再实现，否则调度器只能基于不完整或不可靠状态进行优化。

## 3. 现有工作基础

### 3.1 KDN Server 基础

当前 KDN 已具备：

- SQLite 支撑的文本知识索引；
- 基于内容哈希的 `kid`；
- 文本文件、Embedding、长度等知识元数据；
- `kv_ready`、`kv_rel_dir`、`kv_dumped_keys` 和 `kv_updated_at` 等 KV 状态；
- `KV_database/<kid>/blocks`、`manifest.jsonl` 和 `run_meta.json` 形式的 KV dump；
- 文本注册、查询、删除、快照和 KV 构建接口；
- 将 dump 内容直接写入目标 Redis 的 KV 注入路径；
- KDN 注册、心跳、网络队列模拟和基础传输统计。

这些能力可以继续作为兼容路径和实验基线，但当前存在以下结构性限制：

- 一个 `kid` 只能表达一个粗粒度 KV 状态，无法表达多个模型、并行配置或 KV 布局；
- `kv_ready` 只有可用或不可用，无法表达构建中、传输中、失败、过期和删除中；
- 文本知识与 KVCache 制品耦合在同一张表；
- KV dump 文件、SQLite 状态和 Redis 中的数据可能不一致；
- 没有副本、存储层级、容量、访问统计和维护策略；
- KDN 直接依赖 LMCache 当前 Redis Key 和序列化格式；
- 缺少启动恢复、后台校验和孤儿数据清理。

### 3.2 Proxy 基础

当前 Proxy 已具备：

- 本地 Instance 池和 `round_robin`、`least_load` 策略接口；
- Proxy 维护的 `inflight`、队列深度和预测 backlog；
- prepare / ready 双队列和每 Instance 预留时间线；
- KDN 文本查询与 `kv_ready` / `text_only` / `miss` 分类；
- KDN 到 Instance 的 KV 传输时间预测和链路预留；
- `ProxyTask` 中的 `kv_ready_kids`、`text_only_kids`、`miss_kids`、`kv_ack` 和 `trace`；
- Instance 资源、KDN 链路、队列压力和请求过程的观测入口；
- IWS 文本与 KVCache 注入模式决策基础。

当前不足是：

- 缓存状态仅保存在单个任务字段或 KDN 查询结果中；
- Proxy 没有统一的 KVCache Manager 和本地缓存目录；
- 无法区分“全局存在”“目标 Instance 可访问”“正在加载”“已经装载”“加载失败”；
- 多知识块仅按 `kv_ready` 和 `text_only` 分类后拼接文本；
- 没有请求级 Cache Plan、融合计划和部分复用状态机；
- 没有从 LMCache / vLLM 事件反向更新 Proxy 和 KDN 的闭环。

### 3.3 vLLM + LMCache 基础

当前 CacheRoute 已经能够通过 vLLM + LMCache + Redis 完成 KVCache 构建和复用实验。后续应继续利用 LMCache 提供的：

- vLLM KV Connector；
- 外部 KV 命中 Token 查询；
- 异步加载和保存；
- CPU、磁盘、Redis、P2P 或其他后端；
- 非前缀复用和 CacheBlend 类能力；
- KV 事件和运行时观测。

v0.2.0 的关键不是更换底层，而是建立稳定的 CacheRoute 控制接口，使 KDN 和 Proxy 不再绑定某一个 LMCache 后端的内部表示。

## 4. v0.2.0 目标架构

```text
                           Scheduler
                               |
                   global knowledge-aware route
                               |
                              Proxy
       +-----------------------+-----------------------+
       |                                               |
Proxy KVCache Manager                          Queue Manager
- local cache directory                        - prepare/ready queue
- per-instance cache view                      - reservation timeline
- request CachePlan                            - release/fallback
- LMCache event view
       |
       | query / prefetch / wait / report
       |
                         KDN Server
       +-----------------------+-----------------------+
       |                       |                       |
Knowledge Catalog      Cache Artifact Catalog   Maintenance Engine
- knowledge_id         - artifact_id            - admission
- text / embedding     - compatibility          - eviction
- version              - state / replicas       - replication
                        - tier / size             - migration
                        - runtime stats           - prefetch
                               |
                      Cache Runtime Adapter
                  +------------+-------------+
                  |                          |
          LMCache Adapter           Legacy Redis Adapter
                  |
             vLLM Connector
```

### 4.1 核心对象

#### KnowledgeObject

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

#### CacheArtifact

表示知识在特定模型和运行配置下生成的 KVCache 制品：

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

#### CacheReplica

表示一个制品的具体可访问位置：

```text
replica_id
artifact_id
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

#### CachePlan

表示 Proxy 针对一个请求生成的执行计划：

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

## 5. 迭代总览

| 版本 | 主题 | 主要交付 |
|---|---|---|
| v0.1.10 | 契约与观测基线 | 兼容性指纹、统一状态字段、Trace 契约 |
| v0.1.11 | KDN 对象目录 | KnowledgeObject / CacheArtifact 分离与迁移 |
| v0.1.12 | KDN 生命周期底座 | 状态机、原子发布、恢复和一致性校验 |
| v0.1.13 | Cache Runtime Adapter | LMCache 适配接口和 Legacy Redis 兼容路径 |
| v0.1.14 | Proxy KVCache Manager 基础 | Instance 级缓存视图和请求 CachePlan |
| v0.1.15 | Proxy-KDN 缓存编排 | 异步准备任务、等待、重试、回退和队列集成 |
| v0.1.16 | KDN 维护策略 v1 | 准入、TTL/LRU、Pin、容量水位和安全淘汰 |
| v0.1.17 | KDN 维护策略 v2 | 热度、价值、复制、迁移、预取和 Trace Replay |
| v0.1.18 | 多知识块匹配规划 | 非前缀匹配、覆盖规划、去重和 Dry-run |
| v0.1.19 | 多知识块融合执行 | LMCache 非前缀复用、选择性重计算和质量回退 |
| v0.2.0 | 集成与稳定发布 | 闭环维护、E2E、故障测试、基准和稳定接口 |

## 6. 分版本规划

## v0.1.10：契约与观测基线

### 拟解决的问题

后续所有功能都依赖统一的对象身份、兼容性和状态语义。当前系统主要依赖 `kid`、模型名和 `kv_ready`，不足以支撑多个模型制品、部分加载和运行时反馈。

### 主要步骤

1. 定义并集中管理以下指纹：
   - `model_fingerprint`；
   - `tokenizer_fingerprint`；
   - `adapter_fingerprint`；
   - `kv_layout_version`；
   - `kv_dtype`、`tp_size`、`pp_size` 和 `chunk_size`。
2. 扩展 Instance 注册或资源元数据，上报 vLLM、LMCache 和 KV 能力。
3. 定义统一的缓存状态枚举，但暂不迁移所有旧逻辑：
   - `ABSENT`；
   - `BUILDING`；
   - `STAGING`；
   - `READY`；
   - `LOADING`；
   - `FAILED`；
   - `STALE`；
   - `DELETING`。
4. 统一请求 Trace 中的缓存阶段字段：
   - KDN 查询；
   - 缓存匹配；
   - 准备排队；
   - 传输；
   - LMCache 加载；
   - 残余 Prefill；
   - 融合或回退。
5. 为新增字段提供缺省值和兼容解析，旧 `kv_ready` 继续可用。
6. 增加 Debug API 或 CLI 输出，显示 Instance 能力和缓存契约版本。

### 验收标准

- 相同模型名但配置不兼容的 Instance 能被识别；
- 旧请求和旧 KDN 数据仍能运行；
- 单请求能输出完整且命名稳定的缓存时间分解；
- 不改变当前文本/KV 注入选择结果。

### 非目标

- 不实现复杂缓存选择；
- 不改变 Redis 注入数据面；
- 不实现 Pareto 调度。

## v0.1.11：KDN 知识对象与 KVCache 制品目录

### 拟解决的问题

当前一条知识记录只能附带一套 KVCache 状态，无法支持一个知识对应多个模型、并行度和 KV 布局，也无法独立维护制品生命周期。

### 主要步骤

1. 保留现有 `knowledge_blocks` 表，新增或抽象：
   - `knowledge_objects`；
   - `cache_artifacts`；
   - `cache_replicas`。
2. 明确一对多关系：
   - 一个 KnowledgeObject 可以对应多个 CacheArtifact；
   - 一个 CacheArtifact 可以对应多个 CacheReplica。
3. 生成稳定 `artifact_id`，建议由以下信息共同确定：
   - `knowledge_id`；
   - 模型和 Tokenizer 指纹；
   - Adapter；
   - KV 布局、并行配置和精度。
4. 将 `KV_database/<kid>` 兼容映射为默认 Legacy Artifact，不立即移动旧文件。
5. 为当前 `manifest.jsonl` 和 `run_meta.json` 增加 schema version 与兼容元数据。
6. 扩展 KDN 查询接口：
   - 按 `knowledge_id` 查询可用 Artifact；
   - 按兼容性筛选；
   - 查询副本和存储层级；
   - 保留现有 `/knowledge/search/text`。
7. 扩展 KDN Snapshot，使 Scheduler 可以获取粗粒度 Artifact 可用性，但不下发大规模副本细节。
8. 增加一次性或启动时迁移工具，将旧 `kv_ready` 数据映射到新目录。

### 验收标准

- 同一个 `kid` 可以登记至少两个不同模型或配置的 Artifact；
- 旧 `kv_ready=1` 记录能被映射为一个 Legacy Artifact；
- KDN 能按目标 Instance 能力返回兼容 Artifact；
- 文本注册、删除和 Snapshot 旧接口保持兼容。

## v0.1.12：KDN 生命周期、一致性与恢复底座

### 拟解决的问题

SQLite、dump 文件和远端缓存后端之间可能不一致。仅使用 `kv_ready` 会让部分构建、失败写入和残留目录被误认为可用。

### 主要步骤

1. 实现 Artifact 状态机和合法迁移检查。
2. 将构建流程改为两阶段发布：
   - 创建 `BUILDING` Artifact；
   - 写入临时目录；
   - 生成 Manifest、大小和 Checksum；
   - 校验成功后进入 `STAGING`；
   - 后端发布成功后原子切换为 `READY`。
3. 构建失败时记录错误码、错误摘要和可重试信息。
4. 实现启动恢复与 Reconcile：
   - 检查数据库记录但文件缺失；
   - 检查文件存在但数据库无记录；
   - 检查临时目录和未完成构建；
   - 校验 Manifest、文件数、大小和 Checksum；
   - 将异常对象标记为 `STALE` 或 `FAILED`。
5. 删除流程使用 `DELETING` 状态，并区分元数据删除与物理数据删除。
6. 增加后台任务框架，用于：
   - 周期校验；
   - 失败重试；
   - 孤儿清理；
   - 状态修复。
7. 暴露生命周期 Debug API、统计计数和最近失败任务。
8. 对关键写操作增加幂等键，避免重复请求创建多个制品。

### 验收标准

- 构建过程中不会暴露为 `READY`；
- KDN 重启后可以恢复未完成和异常状态；
- 人工删除一个 dump 文件后，Reconcile 能发现并阻止复用；
- 重复构建请求不会产生不可控重复目录；
- 删除失败不会留下“元数据已删但仍被调度”的对象。

## v0.1.13：Cache Runtime Adapter 与 LMCache 执行接口

### 拟解决的问题

KDN 当前通过读取 dump 并直接执行 Redis `SET` 注入，绑定 LMCache 内部 Key 和序列化格式，无法自然切换 CPU、磁盘、P2P、Mooncake 或其他 LMCache 后端。

### 主要步骤

1. 定义 Cache Runtime Adapter 接口，至少包含：
   - `query_artifact`；
   - `publish_artifact`；
   - `prefetch_artifact`；
   - `wait_task`；
   - `cancel_task`；
   - `evict_artifact`；
   - `verify_artifact`；
   - `collect_stats`。
2. 实现 `LMCacheRuntimeAdapter`，优先使用 LMCache 对外 API、事件或 CLI，而不是内部 Redis Key。
3. 将现有注入实现封装为 `LegacyRedisAdapter`，明确仅用于兼容和实验。
4. KDN API 从“传递 Redis Host/Password”演进为：
   - 指定 Artifact；
   - 指定目标 Cache Runtime / Instance；
   - 返回异步 `task_id`；
   - 查询任务状态和实际传输统计。
5. Adapter 返回统一执行结果：
   - 成功或失败；
   - 实际字节数；
   - 来源和目标存储层级；
   - 排队、传输和加载时间；
   - 重试次数和错误类别。
6. 保留旧接口但标记 Legacy，并在日志和文档中提示迁移路径。
7. 为 Adapter 提供 Mock 实现，支持无 GPU CI 和故障注入。

### 验收标准

- Proxy/KDN 的新路径不需要了解 LMCache Redis Key；
- 同一控制接口可以切换 LMCache Adapter 和 Legacy Redis Adapter；
- 缓存准备任务可异步查询、取消和重试；
- Adapter 失败时能够返回结构化错误而不是只抛出 HTTP 500；
- 旧 Redis 注入流程继续可用于回归测试。

## v0.1.14：Proxy KVCache Manager 基础

### 拟解决的问题

Proxy 当前只有任务局部字段，缺少统一的 Instance 级缓存视图和请求级 Cache Plan，无法支撑后续管理、复用和融合。

### 主要步骤

1. 在 Proxy 正式模块中引入 KVCache Manager，职责包括：
   - 维护全局 Artifact 摘要的短期缓存；
   - 维护每个 Instance 的可访问 / 已装载 / 加载中 / 失败缓存视图；
   - 维护运行中的缓存准备任务；
   - 生成请求 CachePlan；
   - 接收 LMCache / Instance 缓存事件。
2. 定义 Proxy 本地状态：
   - `UNKNOWN`；
   - `AVAILABLE_REMOTE`；
   - `PREFETCHING`；
   - `AVAILABLE_LOCAL`；
   - `LOAD_FAILED`；
   - `EXPIRED`。
3. 将 `ProxyTask` 的缓存字段逐步收敛到 `cache_plan` 和 `cache_trace`，旧字段保留兼容镜像。
4. 建立 CachePlan Builder：
   - 输入请求知识块、目标 Instance 和 KDN 查询结果；
   - 输出命中块、缺失块、来源、副本、预计动作和回退方式。
5. 增加 Proxy Debug API：
   - Instance 缓存视图；
   - 正在运行的 Prefetch / Load Task；
   - 最近 CachePlan；
   - 缓存事件和错误计数。
6. 为本地状态增加 TTL 和刷新机制，防止长期使用过期 KDN 信息。
7. Instance 注销或重启时清理相应本地状态，但不删除 KDN 全局 Artifact。

### 验收标准

- Proxy 能区分远端存在和目标 Instance 已可用；
- 同一 Artifact 的并发请求可以共享一个正在执行的准备任务；
- Instance 重启后 Proxy 不会错误认为旧本地缓存仍然可用；
- CachePlan 可通过 Debug API 完整查看；
- 当前文本和单知识块 KV 路径仍可运行。

## v0.1.15：Proxy-KDN 缓存准备与队列编排

### 拟解决的问题

即使已经有 CachePlan，仍需将查询、预取、加载确认、失败回退和请求释放纳入现有 prepare / ready 队列，避免重复传输、阻塞和错误释放。

### 主要步骤

1. 为 CachePlan 定义执行状态：
   - `CREATED`；
   - `RESOLVING`；
   - `PREFETCHING`；
   - `WAITING_LOAD`；
   - `READY`；
   - `PARTIAL_READY`；
   - `FALLBACK_TEXT`；
   - `FAILED`；
   - `CANCELLED`。
2. QueueManager 只调用 KVCache Manager，不直接拼接 KDN 运行时细节。
3. 实现同 Artifact、同目标 Instance 的 Single-flight 合并。
4. 建立超时、重试和取消策略：
   - KDN 查询超时；
   - Prefetch 超时；
   - Instance 加载确认超时；
   - 请求取消后的引用释放。
5. 明确部分知识命中的回退规则：
   - 命中块复用 + 缺失块文本；
   - 全部文本回退；
   - 请求拒绝仅用于无法保证正确性的场景。
6. 将缓存准备时间接入现有预留时间线，记录预测与实际差异。
7. 防止 Head-of-line Blocking：
   - 文本任务可按现有策略绕过慢 KV 准备；
   - 同一 Artifact 等待者共享结果；
   - 长任务有独立并发上限。
8. 将运行结果反馈给 KDN：
   - hit / miss；
   - 实际命中 Token；
   - 加载成功 / 失败；
   - 实际时间和字节；
   - 最终回退模式。

### 验收标准

- 多个请求并发访问同一 Artifact 时只触发一次目标加载；
- 请求取消不会留下永久占用的任务引用；
- KV 准备失败后请求能按策略文本回退；
- prepare / ready 队列无明显死锁和顺序错误；
- 每个请求可复现完整的缓存准备状态迁移。

## v0.1.16：KDN KVCache 维护策略 v1

### 拟解决的问题

KDN 底座建立后，需要优先实现安全、可解释的缓存维护能力。第一版目标是控制容量、防止错误淘汰并形成可比较的策略基线。

### 主要步骤

1. 建立统一访问统计：
   - `last_access_at`；
   - 窗口命中次数；
   - 累计命中次数；
   - 命中 Token；
   - 构建成本；
   - 加载 / 传输成本；
   - 失败次数；
   - 当前引用数。
2. 实现容量模型：
   - 每个 Backend / Tier 总容量；
   - 已用、预留和可回收容量；
   - 高、低水位；
   - 单对象和单任务上限。
3. 实现准入策略 v1：
   - 容量足够时允许；
   - 超过对象大小上限时拒绝；
   - 构建失败或兼容性不完整时拒绝发布；
   - 允许按配置关闭自动准入。
4. 实现淘汰策略基线：
   - TTL；
   - LRU；
   - 大对象优先或大小约束作为可选策略；
   - 仅从 `READY` 且无引用对象中选择。
5. 实现 Pin：
   - hard pin 不可自动淘汰；
   - soft pin 仅在高压力下淘汰；
   - 系统知识和实验固定知识可显式配置。
6. 实现安全淘汰流程：
   - 标记 `DELETING`；
   - 阻止新引用；
   - 等待活动引用释放；
   - 调用 Runtime Adapter 删除；
   - 更新 Replica 和 Artifact 状态。
7. 增加策略 Dry-run：输出将淘汰对象但不执行。
8. 增加策略决策日志和统计：
   - 入选原因；
   - 淘汰原因；
   - 释放字节；
   - 被 Pin 跳过数量。

### 验收标准

- 在可控容量下能够稳定触发 TTL/LRU 淘汰；
- 活跃请求引用的缓存不会被删除；
- hard pin 对象不会被自动淘汰；
- Dry-run 与实际执行候选一致；
- 策略关闭后系统行为回到手工维护模式。

## v0.1.17：KDN KVCache 维护策略 v2

### 拟解决的问题

TTL/LRU 只能保证基础容量管理，不能利用知识工作负载中的重复访问、构建成本和网络拓扑。第二版面向研究，建立可插拔的价值、复制、迁移和预取框架。

### 主要步骤

1. 定义策略接口：
   - Admission Policy；
   - Eviction Policy；
   - Replication / Placement Policy；
   - Tier Migration Policy；
   - Prefetch Policy；
   - Refresh / Rebuild Policy。
2. 建立缓存价值特征：
   - 短期和长期访问频率；
   - 可节省 Prefill Token 与时间；
   - 对象大小；
   - 构建成本；
   - 远端加载成本；
   - 副本数和故障域；
   - 未来访问预测置信度。
3. 实现至少一个可解释的大小 / 价值感知策略，与 LRU 做对比。
4. 支持热点副本：
   - 单副本到多副本；
   - 副本上限；
   - 副本冷却和回收；
   - 避免同一故障域重复放置。
5. 支持存储层级迁移：
   - 热对象提升；
   - 冷对象下沉；
   - 迁移期间保持至少一个可用副本；
   - 失败回滚。
6. 支持预取：
   - 根据近期请求序列；
   - 根据 Proxy 已选目标 Instance；
   - 根据多轮会话或批量工作负载；
   - 设置并发和带宽预算。
7. 建立 Trace Replay：
   - 从历史请求和缓存事件重放；
   - 离线比较策略命中率、字节占用、传输量和节省计算；
   - 同一 Trace 可重复运行不同策略。
8. 策略只产生决策，执行仍通过统一 Maintenance Task 和 Runtime Adapter。
9. 将策略结果反馈给 Proxy 观测页面，但不强制改变 Instance 选择算法。

### 验收标准

- 可以通过配置切换 LRU 和至少一种价值感知策略；
- 热点对象能自动创建和回收副本；
- 层级迁移失败不会导致最后一个可用副本丢失；
- Trace Replay 能生成可比较的策略结果；
- 策略决策和实际执行结果均可追踪。

## v0.1.18：多知识块非前缀匹配与执行规划

### 拟解决的问题

当前多知识块流程主要拼接文本并将 `kv_ready` 块放在前面，不能表达知识块位于 Prompt 中间、顺序变化、部分重叠或多个来源的情况。该版本先完成匹配和规划，不立即强制执行融合。

### 主要步骤

1. 将请求知识表示为有序 Knowledge Block 列表：
   - `knowledge_id`；
   - 原始顺序；
   - Token 范围；
   - 文本 Hash；
   - 必选 / 可选；
   - 分隔符和模板信息。
2. 定义 Prompt Layout，明确系统提示、知识块和用户问题的 Token 区间。
3. 查询每个 Knowledge Block 的兼容 Artifact 和可用 Replica。
4. 实现匹配类型：
   - 完全块命中；
   - 部分 Chunk 命中；
   - 非前缀位置命中；
   - 重叠命中；
   - 多个 Artifact 竞争同一范围；
   - 未命中。
5. 构建 Coverage Map，避免同一 Token 被多个制品重复覆盖。
6. 生成 FusionPlan：
   - 选用 Artifact；
   - 来源和目标；
   - 需要加载的块；
   - 需要重算的 Token 范围；
   - 最终知识顺序；
   - 文本回退范围；
   - 预计收益和风险标记。
7. 提供 Dry-run 模式，只输出计划，不改变推理请求。
8. 支持当前单前缀路径作为 FusionPlan 的特例。
9. 为规划器添加确定性测试：
   - 顺序变化；
   - 重复知识；
   - 部分命中；
   - Overlap；
   - 空知识列表；
   - Artifact 不兼容。
10. 记录计划复杂度，限制单请求最大知识块、最大候选 Artifact 和最大覆盖区间数量。

### 验收标准

- 给定相同请求和目录快照，FusionPlan 结果稳定；
- 能正确表示非前缀、部分命中和重叠；
- Dry-run 不改变现有推理输出；
- 单知识前缀请求仍生成与旧逻辑等价的计划；
- 规划失败时明确回退为纯文本。

## v0.1.19：多知识块非前缀融合执行

### 拟解决的问题

v0.1.18 只生成计划。本版本需要通过 LMCache / vLLM 实际执行多块复用和选择性重计算，并验证正确性、性能和失败回退。

### 主要步骤

1. 在 Runtime Adapter 中增加 Fusion 执行能力：
   - 查询非前缀复用支持；
   - 提交多个 Artifact；
   - 指定 Token 区间和顺序；
   - 指定选择性重计算范围；
   - 返回实际命中和重算结果。
2. 优先适配 LMCache 的非前缀复用、CacheBlend 或等价公开接口。
3. 如果运行时不支持 FusionPlan，自动降级：
   - 单前缀 KV；
   - 部分 KV + 文本；
   - 全文本。
4. Proxy KVCache Manager 执行 FusionPlan，并将状态接入 QueueManager。
5. 增加质量保护：
   - 基础输出一致性或任务指标检查；
   - 对关键实验支持 KV Fusion 与纯文本双跑；
   - 记录选择性重算比例；
   - 质量异常时关闭该 Artifact 或策略。
6. 处理多块并行加载和共享加载任务，避免重复传输。
7. 将实际命中、重算、融合开销和质量结果反馈给 KDN Maintenance Engine。
8. 维护策略开始利用多知识块结果：
   - 高频共同出现块；
   - 单块热点；
   - 融合收益低的对象；
   - 适合预取或复制的组合。
9. 建立端到端实验：
   - 不同块数量；
   - 不同顺序；
   - 不同命中比例；
   - 不同网络和缓存层级；
   - 不同选择性重算比例。

### 验收标准

- 至少支持两个知识块的非前缀融合复用；
- 实际命中 Token、重算 Token 和融合开销可观察；
- 运行时不支持或执行失败时能够正确回退；
- 多块加载不会产生重复任务风暴；
- 与纯文本基线相比能够输出正确且可重复的性能结果。

## v0.2.0：集成、稳定与研究基线发布

### 拟解决的问题

前序版本分别建立对象目录、生命周期、Runtime Adapter、Proxy 管理、维护策略和融合执行。v0.2.0 需要将这些能力稳定为一个可复现实验和持续开发的统一版本。

### 主要步骤

1. 固化 v0.2.0 稳定接口：
   - KnowledgeObject / CacheArtifact / CacheReplica；
   - Cache Runtime Adapter；
   - Proxy CachePlan / FusionPlan；
   - KDN Maintenance Policy；
   - 运行时事件和 Trace 字段。
2. 完成 Legacy 兼容策略：
   - 旧 `kv_ready` 数据迁移；
   - 旧 Redis 注入保留但默认标记 Legacy；
   - 明确后续弃用窗口；
   - 提供数据校验和迁移命令。
3. 完成端到端场景：
   - 单知识文本；
   - 单知识 KV；
   - 多知识部分命中；
   - 多知识非前缀融合；
   - KV 失败文本回退；
   - KDN 重启恢复；
   - Instance 重启和本地状态失效；
   - 容量水位触发维护策略。
4. 建立故障测试：
   - KDN 不可用；
   - LMCache 不可用；
   - 构建中断；
   - 文件损坏；
   - Prefetch 超时；
   - Instance 下线；
   - 淘汰与请求并发；
   - 副本迁移失败。
5. 建立统一 Benchmark 和 Trace：
   - TTFT P50 / P95 / P99；
   - 吞吐；
   - KV 命中 Token 率；
   - 实际网络字节；
   - 残余 Prefill Token；
   - 缓存容量和写放大；
   - 淘汰、复制、迁移和预取次数；
   - 回退率与错误率；
   - 多知识融合收益和质量指标。
6. 提供策略对比基线：
   - 无自动维护；
   - TTL；
   - LRU；
   - 价值感知策略；
   - 无融合；
   - 前缀复用；
   - 非前缀融合复用。
7. 补齐文档：
   - 架构和角色边界；
   - KDN 数据模型；
   - Proxy KVCache Management；
   - Runtime Adapter；
   - 维护策略开发；
   - 多知识块 Fusion；
   - 部署、迁移、调试和实验复现。
8. 将 Proxy UI 和 KDN 调试接口补充到可验证水平，不要求 v0.2.0 必须完成完整 KDN 前端。
9. 对配置进行清理：所有实验特性可独立启停，默认值明确，错误组合启动时给出清晰提示。
10. 发布前冻结 Wire Schema 和 Trace Schema，避免同一实验周期中字段持续漂移。

### v0.2.0 发布标准

- KDN 能可靠维护多个模型 / 配置的 CacheArtifact；
- Artifact 生命周期可恢复，异常对象不会被错误复用；
- KDN 至少提供 TTL/LRU 和一种价值感知维护策略；
- Proxy 有独立 KVCache Manager 和可观察 CachePlan；
- Cache 准备任务支持 Single-flight、超时、重试和文本回退；
- 至少完成两个知识块的非前缀融合复用；
- vLLM / LMCache 执行细节通过 Adapter 隔离；
- 当前单知识和文本路径保持兼容；
- 关键故障场景有自动测试或可重复脚本；
- 维护策略和融合能力有可复现的实验结果。

## 7. KDN 维护策略研究框架

KDN KVCache 维护是 v0.2.0 之后的核心研究主线。为避免策略代码与底座耦合，v0.1.16 起应按以下结构组织。

### 7.1 策略输入

- Artifact 大小、Token 数和构建成本；
- 近期与长期访问频率；
- 命中 Token 和实际节省 Prefill 时间；
- 传输、加载和选择性重计算开销；
- 存储层级和目标 Instance 分布；
- 当前副本数和故障域；
- 容量水位、网络压力和维护任务队列；
- Pin、租户或实验约束；
- 多知识块共同出现关系；
- 预测值及其置信度。

### 7.2 策略输出

```text
ADMIT / REJECT_BUILD
KEEP / EVICT
PIN / UNPIN
REPLICATE / REMOVE_REPLICA
PROMOTE_TIER / DEMOTE_TIER
PREFETCH / CANCEL_PREFETCH
REFRESH / REBUILD
```

### 7.3 策略评价指标

- 请求级 TTFT 和尾延迟；
- KV 命中 Token 率；
- 节省 Prefill Token 和 GPU 时间；
- 缓存容量利用率；
- 网络传输字节和峰值带宽；
- 构建、复制和迁移写放大；
- 缓存抖动和重复淘汰；
- 预取准确率和污染率；
- 多知识块融合收益；
- 故障恢复和策略稳定性。

### 7.4 第一阶段重点研究问题

1. 哪些知识对象值得构建 KVCache，而不是只在访问后被动保存？
2. 在容量受限时，应按时间、频率、大小还是节省计算价值淘汰？
3. 热点对象应复制到 KDN、Proxy 所在资源池还是具体 Instance 附近？
4. 预取收益如何覆盖传输成本、容量成本和对在线请求的干扰？
5. 多知识块共同出现是否应影响单块副本和预取策略？
6. 非前缀融合带来的选择性重计算成本如何进入缓存价值评估？
7. 维护策略如何在预测不准确时保持安全并避免频繁抖动？

## 8. Proxy KVCache Management 与 KDN 的状态边界

为了避免重复状态和一致性问题，应明确：

### KDN 是权威状态

KDN 维护：

- Artifact 是否存在和是否完整；
- Artifact 兼容性；
- Replica 位置和存储层级；
- 容量、Pin 和维护策略状态；
- 全局访问统计和生命周期。

### Proxy 是短期执行状态

Proxy 维护：

- 某目标 Instance 是否已经可访问 Artifact；
- Artifact 是否正在为当前 Instance 加载；
- 哪些请求正在等待同一任务；
- 当前请求的 CachePlan / FusionPlan；
- 短期负缓存、错误和 TTL；
- 实际执行事件和反馈缓冲。

### Instance / LMCache 是运行时事实来源

Instance / LMCache 提供：

- 实际命中 Token；
- 实际加载完成；
- Block 加载错误；
- 实际缓存存储事件；
- 请求结束和异步保存完成事件。

Proxy 不应仅因为 KDN 返回 `READY` 就认为目标 Instance 已完成加载；KDN 也不应仅因为 Proxy 的短期视图失效就删除全局 Artifact。

## 9. 测试与实验要求

每个版本至少应覆盖四类验证。

### 9.1 单元测试

- 状态机合法迁移；
- Artifact ID 和兼容性；
- CachePlan / FusionPlan 确定性；
- 策略候选和安全过滤；
- Trace 字段和兼容解析。

### 9.2 组件测试

- KDN SQLite 与文件一致性；
- Runtime Adapter Mock；
- Proxy KVCache Manager Single-flight；
- QueueManager 超时和取消；
- Maintenance Task Dry-run 与执行。

### 9.3 端到端测试

- vLLM + LMCache + CacheRoute 完整启动；
- 文本、前缀 KV、部分 KV 和多块融合；
- 自动淘汰、复制、迁移和预取；
- 故障回退和重启恢复。

### 9.4 实验复现

每个策略实验应保存：

- 配置文件；
- 代码版本；
- 模型和 LMCache / vLLM 版本；
- 工作负载 Trace；
- KDN 初始状态；
- 策略参数；
- 请求级结果；
- 汇总指标和异常记录。

## 10. 版本依赖与并行开发建议

```text
v0.1.10
   |
v0.1.11
   |
v0.1.12
   |
v0.1.13
   +----------------------+
   |                      |
v0.1.14               v0.1.16 early policy API design
   |                      |
v0.1.15                   |
   +----------+-----------+
              |
           v0.1.16
              |
           v0.1.17
              |
           v0.1.18
              |
           v0.1.19
              |
           v0.2.0
```

可并行的工作包括：

- v0.1.10 期间同步设计 Trace Schema 和兼容性指纹；
- v0.1.11 期间同步准备旧数据迁移测试；
- v0.1.12 期间开发 Runtime Adapter Mock；
- v0.1.14 期间先定义 Maintenance Policy 接口，但不启用策略；
- v0.1.16 / v0.1.17 期间并行准备多知识块工作负载和质量评测；
- v0.1.18 Dry-run 稳定后再接入 v0.1.19 实际融合，避免规划和执行同时调试。

## 11. 后续路线

达到 v0.2.0 后，再基于稳定的对象、事件和维护反馈推进：

1. `kv_aware` Proxy Instance 路由；
2. KDN、Proxy、Instance 联合候选选择；
3. 分层 Pareto 筛选；
4. SLO 和不确定性感知调度；
5. LMCache MP / P2P 和更高性能传输后端；
6. Prefill / Decode 或 Encoder / Prefill / Decode 解耦；
7. 多租户配额、公平性和生产级高可用。

这些能力应建立在 v0.2.0 提供的可信状态和执行闭环之上，而不是反向要求调度器推断底层缓存事实。
