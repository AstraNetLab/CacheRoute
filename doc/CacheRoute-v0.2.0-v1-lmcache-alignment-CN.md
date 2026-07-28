# CacheRoute v0.2.0：v1 KDN 与 LMCache 原生能力对齐修订

> 状态：架构修订，作为现有 v0.2.0 中英文规划的补充和优先解释
> 运行基线：vLLM 0.25.1 + LMCache 0.5.2 + PyTorch 2.11.0
> 开发政策：新功能进入 `v1`；`legacy` 保持可用但功能冻结

## 1. 修订原因

迁移到当前 vLLM 与 LMCache MP 环境后，LMCache 已经提供了比旧版本更完整的缓存数据与维护能力，包括：

- Token Database 与 Token/Hash Lookup；
- vLLM `LMCacheMPConnector` 到 LMCache MP 的直接数据路径；
- L1 与持久化 L2；
- 多个 L2 Adapter 的级联查询与写入；
- 异步 L1→L2 Store 和 L2→L1 Prefetch；
- Store/Prefetch Policy；
- L1/L2 独立容量、使用率和淘汰；
- Cache Object 枚举与删除；
- Warm Prefetch、Pin/Unpin、Operation Status；
- MP HTTP API、Coordinator、SDK、Metrics 与 Events；
- 多 Server、L2 Event、Quota 和维护编排。

CacheRoute 不应在 KDN 中重复实现这些能力的简化版本。重复实现会造成：

- 与 LMCache Token/Chunk/Key/Layout 语义不一致；
- 无法继承 LMCache 后续多层级、Adapter、锁和异步加载演进；
- v1 与 Legacy 逻辑交叉；
- KDN 成为第二套物理缓存事实来源；
- 升级时需要同时维护两套简单但不兼容的实现。

## 2. 新的正式定位

> **KDN Server = Knowledge Control Plane + CacheRoute Cache Service Facade + LMCache Orchestration Gateway。**

KDN 仍是独立部署、独立扩展、可由 Scheduler 管理的服务实体，但在 v1 中不再默认充当 LMCache 的另一套远端 KV 数据服务器。

### 2.1 数据热路径

```text
vLLM
  <-> LMCacheMPConnector
  <-> LMCache MP
      <-> L1
      <-> cascaded L2 adapters
```

高频 Lookup、Store、Retrieve、Prefetch 和 KV 数据传输不经过 KDN 业务服务。

### 2.2 CacheRoute 控制路径

```text
Scheduler / Proxy / Instance
          -> KDN Cache Service Facade
          -> LMCache Orchestration Gateway
          -> LMCache MP HTTP / Coordinator / SDK / Metrics / Events
```

KDN 负责：

- KnowledgeObject 与版本；
- CacheArtifact 身份和兼容性；
- KnowledgeObject 到 Token/Artifact 的映射；
- Desired State 和缓存策略；
- Lookup/Prefetch/Pin/Clear/Rebuild 操作意图；
- 幂等任务、审计、授权、结构化错误和回退；
- LMCache 观测的归一化和短期缓存；
- 请求结果、命中价值和维护反馈。

LMCache 负责：

- Token 分块、Hash 和 Key；
- 物理 KV 对象和 Layout；
- L1/L2 驻留；
- Adapter 级联；
- Serde；
- Lock/Unlock；
- Store、Retrieve、Prefetch；
- 容量统计和淘汰；
- 物理操作完成状态。

## 3. KDN 保留的统一服务接口

KDN 仍需要自己的稳定 API，但这些 API 是 CacheRoute 领域接口，不是另一套物理 KV 存储协议。

### 3.1 Knowledge API

```text
RegisterKnowledge
UpdateKnowledgeVersion
ResolveKnowledge
ListCompatibleArtifacts
GetPolicyDecision
ReportRequestOutcome
```

### 3.2 Cache Service API

```text
GetCacheObservation
LookupArtifact
LookupTokens
CreatePrefetchIntent
CreatePinIntent
CreateClearIntent
CreateRebuildIntent
GetOperationStatus
GetLMCacheEndpoints
GetTierAndAdapterSummary
GetMaintenanceStatus
```

接口参数使用：

- Knowledge ID；
- Artifact ID；
- Token 序列或 Token Reference；
- Instance Capability；
- LMCache Endpoint ID；
- 逻辑 Operation ID。

接口不得把以下内容作为稳定域模型：

- Redis Key；
- Redis URL 或密码；
- LMCache 私有 Python 对象；
- LMCache 内部 Chunk Key；
- 物理 KV Payload；
- 私有序列化对象。

## 4. v1 与 Legacy 边界

### 4.1 v1

- 所有新功能只开发在 `v1`；
- 使用 LMCache MP 和公开控制/观测接口；
- 使用 Adapter/Factory/Capability Snapshot 隔离版本差异；
- 新代码不直接扫描或复制 Redis Key；
- 缺少能力时返回 `unsupported`、`incompatible` 或明确文本回退；
- 不允许 v1 请求静默切换到 Legacy 写路径。

### 4.2 Legacy

- 保留当前 Redis scan/dump/restore/inject；
- 保留旧启动、请求和实验流程；
- 功能冻结，仅接受可用性、安全、严重缺陷和兼容性修复；
- 所有物理操作封装在 `LegacyCacheAdapter` 或等价边界；
- Legacy Key 和目录不能成为 v1 Artifact 身份；
- Legacy 数据进入 v1 必须经过显式迁移或重建。

### 4.3 Auto

`auto` 只用于迁移发现。进程启动时必须将其解析并冻结为明确 Profile：

```text
auto -> v1
```

或：

```text
auto -> legacy
```

同一进程或单次请求中不得根据 Key 是否存在而动态切换主执行语义。

## 5. LMCache Gateway

Gateway 是唯一允许了解 LMCache 具体版本和接口形态的模块。

### 5.1 推荐 Adapter

```text
MPHTTPGateway
MPCoordinatorGateway
MPSDKGateway
MPMetricsEventGateway
MockGateway
LegacyCacheAdapter
```

可选：

```text
L2PluginGateway
```

仅当 CacheRoute 需要 LMCache 尚未提供的后端能力时，才实现 L2 Plugin；它仍应遵循 LMCache Adapter 契约。

### 5.2 启动期能力发现

v1 Gateway 启动时应：

1. 查询 LMCache 版本和 Build ID；
2. 查询 Config 和已加载 Adapter；
3. 探测需要的 HTTP Route、Metric 和 Event；
4. 构建不可变 Capability Snapshot；
5. 验证 Connector、Chunk Size、Hash、Layout、Serde 和 Tier；
6. 生成 Endpoint Generation；
7. 将 Profile 写入 Instance Capability 和 Trace。

未知能力不得视为支持。

### 5.3 稳定对象

```text
RuntimeProfile
LMCacheCompatibilityProfile
LMCacheEndpoint
CacheArtifact
CacheReplicaObservation
CacheOperationTask
QueueWork
CachePlan
ExecutionGraph
```

`CacheReplicaObservation` 是带 TTL 的短期观测，不是 KDN 自己拥有的物理副本。

## 6. 版本路线修订

| 版本 | 修订后主题 | 主要交付 |
|---|---|---|
| v0.1.10 | v1/Legacy 契约与观测基线 | RuntimeProfile、Gateway Profile、状态、Trace、Legacy 投影 |
| v0.1.11 | Knowledge Control + LMCache Observation | Knowledge/Artifact、Token Mapping、Endpoint/Adapter/Tier 观测 |
| v0.1.12 | LMCache-backed KDN Cache Service MVP | MP HTTP/Coordinator Gateway、Lookup/Prefetch/Pin/Clear |
| v0.1.13 | 多层级、多 Adapter 与版本兼容 | Adapter Cascade、容量/淘汰观测、兼容矩阵、恢复/重建 |
| v0.1.14 | Proxy KVCache Manager | 基于 KDN/LMCache 观测的短期 Instance View、Single-flight |
| v0.1.15-v0.1.17 | 执行队列与网络计算并行 | ExecutionGraph、背压、公平、并发与 Overlap |
| v0.1.18 | KDN 知识型策略 | Prefetch/Pin/Clear/Rebuild 意图和价值模型 |
| v0.1.19 | 多知识块融合 | Token/Artifact 并行查询、选择性重计算、质量回退 |
| v0.2.0 | 集成研究基线 | v1 默认、Legacy 保留、跨 LMCache 版本兼容 |

## 7. 不应重复实现的能力

v1 KDN 不实现：

- Token Database；
- Chunk Hash 和物理 Key 生成；
- L1/L2 StorageManager；
- 多 Adapter 级联查询；
- L1/L2 淘汰线程；
- Store/Prefetch Controller；
- KV Serde；
- KV Lock/Unlock；
- Cache Object 物理目录；
- LMCache 已提供的 Warm Prefetch、Pin 或 Clear 的简化版本。

KDN 可以实现：

- 知识级价值评估；
- 哪个 Artifact 应预热、Pin、清理或重建；
- 将策略意图编译为 LMCache 操作；
- 多 LMCache Endpoint 的选择和粗粒度编排；
- LMCache 观测的归一化、TTL 和置信度；
- 版本兼容门禁和回退；
- 请求级实验 Trace。

## 8. 测试原则

### v1

- Mock Gateway CPU-only 契约测试；
- MP HTTP Gateway 测试；
- Coordinator Gateway 测试；
- 两种 LMCache Adapter/Tier 配置；
- Token Lookup 与 Warm Prefetch；
- Cache Object、容量和淘汰观测；
- LMCache Endpoint 重启与 Generation 变化；
- 实际 hit-token 和 remote-read 指标；
- LMCache 小版本升级 Conformance Test。

### Legacy

- 旧启动路径；
- Redis scan/dump/restore/inject；
- 旧请求格式；
- 文本和回退路径；
- Legacy 代码变更不能影响 v1 测试；
- v1 代码变更不能破坏 Legacy 最小回归集。

## 9. 优先解释规则

本文档修订并替代现有 v0.2.0 规划中以下旧表述：

- “KDN Remote Cache Serving Plane 是 v1 默认数据热路径”；
- “LMCache 将 KDN 作为默认远端 KV Store”；
- “KDN 自己实现 Provider 级联、容量或淘汰”；
- “新功能可以同时进入 v1 和 Legacy”。

未被本文档修改的知识策略、Proxy ExecutionGraph、网络与计算并行、多知识块融合和实验指标规划继续有效。
