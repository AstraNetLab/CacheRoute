# CacheRoute Blog / Update Log

这里维护 CacheRoute 原型系统的阶段性工程记录。更细粒度的调试过程、代码讨论和审查意见以 GitHub Issues / Pull Requests 为准。

## 阅读方式

- **最新进展**放在最前面。
- 每条记录按“背景 / 改动 / 验证 / 后续”组织。
- 旧 README 中的历史内容已整理为结构化 changelog，保留关键动机、文件范围和维护者信息。

---

## 260713：Instance Resource Agent demo 集成与资源状态上报

### 背景

本轮目标是把 Instance 侧资源采集链路从“手动启动 Rust Agent + 手动 reporter”推进到 demo 可直接验证的状态，使 Proxy 能看到本地 Instance 的 CPU、内存、GPU、网络和资源时间戳状态。

### 改动

- `test/demo_instance.py` 默认启用资源监控。
- demo Instance 显式接管 Rust Resource Agent 生命周期：启动 / 复用、readiness 检查、周期上报、shutdown 清理、SIGTERM/SIGKILL fallback。
- 上报只在 Instance 成功注册到 Proxy 后启动，避免 Proxy 收到 `unknown_instance`。
- `instance/resource_agent/proxy_reporter.py` 的上报 payload 增加 metadata：
  - `reported_instance_id`
  - `report_monotonic_ms`
  - `report_wall_time_ms`
  - `agent_snapshot_timestamp_ms`
- Proxy `InstancePool.resource` 增加规范化资源字段和时间戳字段。
- Proxy 控制面新增 / 完善资源查看入口：
  - `GET /debug/instance_resources`
  - `GET /v1/instance/list?include_dead=true`
- Proxy 资源 snapshot 成功日志降噪：第一次成功保留 INFO，后续成功更新转为 DEBUG。
- 新增 `test/demo_resource_monitor_e2e.py`，用于启动 Proxy + Instance、等待资源上报、关闭 Instance 并检查 demo-owned agent 是否清理。
- 新增 `test/README.md`，整理 `test/` 下 demo 文件职责。

### 验证命令

启动 Proxy：

```bash
cd test
python3 demo_proxy.py \
  --host 127.0.0.1 \
  --port 8001 \
  --strategy round_robin \
  --injection-strategy iws
```

启动 Instance：

```bash
cd test
python3 demo_instance.py \
  --host 127.0.0.1 \
  --port 9001 \
  --proxy-cp-url http://127.0.0.1:8002
```

查看 Proxy 收到的资源状态：

```bash
curl -sS "http://127.0.0.1:8002/debug/instance_resources" | python3 -m json.tool
curl -sS "http://127.0.0.1:8002/v1/instance/list?include_dead=true" | python3 -m json.tool
```

单独检查 Rust Agent：

```bash
curl -sS http://127.0.0.1:9201/healthz
curl -sS http://127.0.0.1:9201/v1/resource/snapshot | python3 -m json.tool
```

运行 e2e smoke：

```bash
python3 test/demo_resource_monitor_e2e.py \
  --agent-listen 127.0.0.1:19201 \
  --agent-url http://127.0.0.1:19201
```

### 当前状态

Issue #86 的核心目标基本完成：Instance demo 能默认启动或复用 Resource Agent，注册后向 Proxy 上报资源，Proxy 能通过 API 查看资源状态。资源状态目前仍是**观测数据**，尚未进入 Proxy Instance 选择策略。

### 后续

1. 基于 `InstancePool.resource` 设计资源感知 Instance selection 策略。
2. 在 Instance 侧补充队列、KVCache block、vLLM runtime 等更细粒度指标。
3. 将 GPU 采集从 `nvidia-smi` 轮询替换为更低开销方案。
4. 继续改进 Resource Dashboard UI，使多 GPU 场景更易读。

维护者：heyao

---

## 260713：后续计划

目前知识注入侧的全局调度器已有雏形，本地资源池的调度主要实现了动态知识注入决策，实例选择模块仍需继续整理。

<img width="400" alt="image" src="https://github.com/user-attachments/assets/965b2b48-afe2-4c26-8784-ae52f7f4bcbe" />

后续原型系统工程计划：

1. **资源池级实例调度策略**
   - 基于 Rust Agent 实现实例资源感知与管理。
   - 通过 API / gRPC 上报至 Proxy。
   - Proxy 维护实例 KVCache 和资源状态，并向 KDN / Scheduler 上报必要摘要。
2. **KDN 服务器改进**
   - 当前 KDN 服务器支持知识注册、查询和反馈。
   - 后续需要控制平面，对知识资源进行更细粒度维护，为 KVCache 放置策略服务。

维护者：heyao

---

## 260312：提升 Perf Client 能力，修复 KEYS 失配问题，完善 KDN 能力

### 改动

- 排查 LMCache key 不能跨容器周期复用的问题，确认 `chat-template` 中的 Today-Date 信息导致 chunk hash 变化。
- `perf_client.py` 支持 hybrid 模式 `Injection_type`，用于测试混合策略性能。
- KDN 服务器构建网络传输模型，支持批次内并发、均分带宽、批次间串行传输，并支持批次窗口配置。

### 涉及文件

- `model/tokenizer_config.json`
- `client/perf_client.py`
- `kdn_server/kv_injector.py`
- `kdn_server/kdn_api.py`
- `test/demo_kdn.py`

### 后续

- KDN 服务器 UI。
- Instance 侧资源检索平台。
- 双 inflight 维护池级业务流状态。
- 知识清单中可用 LLM 系统状态更新。

维护者：heyao

---

## 260311：提升 Client 显示与发包能力

### 改动

- Client 增加任务时间戳显示。
- 扩展 `perf_client.py`，简化 `workload.json`，新增 `client/taskset/` 生成任务 JSON。
- `perf_client.py` 增加 RPS 模式，用于持续压测和性能曲线实验。

### 涉及文件

- `client/taskset/`
- `client/client.py`
- `client/perf_client.py`

维护者：heyao

---

## 260310：提升 KDN 批量注册与显示能力

### 改动

- 支持从 JSON 批量注册知识文本，初始化 KDN 知识库。
- 改善 KDN CLI 输出，允许查看整体资源池状态。

### 涉及文件

- `kdn_server/util/knowledge_manifest.json`
- `kdn_server/util/batch_register_kdn.py`
- `kdn_server/kdn_api.py`
- `kdn_server/kdn_register_cli.py`
- `kdn_server/text_db.py`

维护者：heyao

---

## 260309：实现 Proxy 并行处理任务队列，完善时间戳与 Client 发包器

### 改动

- 将 `prepare-ready` 串行处理升级为队列 + prepare 并发控制 + 活动计数。
- 为每个 Instance 启用多个 prepare worker。
- Chat / completion 返回结果附带 `cacheroute_meta`，用于观察性能。
- 新增 `perf_client.py` 和 `workload.json`，支持持续发包压力测试。
- 支持透传 `Injection_type` 字段，作为策略调试控制。
- 继续观察 LMCache keys 复用问题。

### 示例

```bash
python3 perf_client.py \
  --base-url http://127.0.0.1:7001 \
  --workload-file workload.json \
  --requests 2 \
  --concurrency 8 \
  --allow-duplicate \
  --seed 7
```

### 后续

- KDN 服务器 UI。
- Instance 资源检索平台。
- 双 inflight 池级业务流维护。
- 可用 LLM 系统状态更新。

维护者：heyao

---

## 260306：大更新 v0.1.4，打通文本与 KVCache 注入全流程

### 改动

- 实现基于 KVCache 的知识注入。
- 当 `Injection_type=kvcache` 时，Proxy 先完成文本分类和注入准备，再通知 Instance 将 KVCache 注入到本地 Redis，收到 ACK 后任务进入 ready 队列。
- `proxy.manager` 对知识需求分类为 `kv_ready`、`text_only`、`miss`。
- 打通 Proxy -> Instance -> KDN Server 的 KV 注入子链路。
- 集成 KVCache 注入行为和消息格式。

### 涉及文件

- `instance/kv_service.py`
- `instance/control_plane.py`
- `proxy/queue/task.py`
- `proxy/queue/manager.py`
- `proxy/queue/knowledge.py`
- `instance/instance_api.py`
- `core/config.py`
- `kdn_server/kdn_api.py`

维护者：heyao

---

## 260305：构建 Proxy 内 Prepare + Ready 双任务队列结构

### 改动

- 串通文本知识注入与 KVCache 注入。
- 添加 `Injection_type` 变量标记任务注入策略。
- Proxy 主 handler 不再直接调用 `forward_request`，而是把任务交给队列模块。
- 引入 per-instance `prepare/ready` 双队列。
- 知识注入迁移到 prepare queue worker。
- ready queue worker 负责真正转发到 Instance 并回传输出。

### 涉及文件

- `proxy/queue/__init__.py`
- `proxy/queue/task.py`
- `proxy/queue/manager.py`
- `proxy/queue/knowledge.py`
- `proxy/queue/instance_queues.py`
- `core/request.py`
- `scheduler/scheduler.py`
- `proxy/proxy.py`

维护者：heyao

---

## 260304：完善 Scheduler 与 Proxy 日志输出

### 改动

- Scheduler 心跳日志改为周期统计，减少命令行噪声。
- Proxy 心跳日志改为周期统计，避免海量输出。

### 涉及文件

- `scheduler/resource/hb_log.py`
- `proxy/resource/hb_log.py`
- `core/config.py`
- `scheduler/scheduler.py`
- `scheduler/resource/control_plane.py`
- `scheduler/knowledge/kdn_sync.py`
- `proxy/proxy.py`

维护者：heyao

---

## 260303：完善 Scheduler 的 Proxy 资源池信息维护

### 改动

- Proxy 注册时上报静态能力描述：最大并发、实例数、KVCache 容量、更新策略等。
- Scheduler 基于流事件维护 proxy inflight，并通过 proxy 心跳低频校准。

### 涉及文件

- `core/request.py`
- `core/config.py`
- `scheduler/scheduler.py`
- `scheduler/scheduler_cli.py`
- `scheduler/resource/control_plane.py`
- `scheduler/resource/proxy_pool.py`
- `proxy/proxy.py`
- `proxy/sclient/scheduler_client.py`

维护者：heyao

---

## 260302：Scheduler 显示优化，KDN + Proxy 调度策略集成

### 改动

- `scheduler_cli` status 支持查看 KDN 资源池。
- 优化 KDN refresh，先构建新表再 swap，避免并发刷新混乱。
- 将 KDN 选择策略集成进 Scheduler strategy。
- KDN 注册成功后立即触发 refresh。

### 涉及文件

- `core/request.py`
- `scheduler/scheduler.py`
- `scheduler/scheduler_cli.py`
- `scheduler/resource/control_plane.py`
- `scheduler/knowledge/kdn_sync.py`
- `scheduler/strategy/base.py`
- `scheduler/strategy/round_robin.py`
- `store/knowledge_base.py`

维护者：heyao

---

## 260202：Proxy、Scheduler 池资源结构优化

### 改动

- 支持 Proxy 策略接入 Instance 池。
- Proxy 初始化时支持加载策略，不再依赖 Scheduler `build_request` 赋值。
- Scheduler 通过 KDN 池维护知识清单。
- 明确启动顺序：Scheduler -> KDN / Proxy -> Instance。

### 涉及文件

- `core/config.py`
- `scheduler/scheduler.py`
- `scheduler/resource/control_plane.py`
- `scheduler/knowledge/kdn_sync.py`
- `scheduler/resource/kdn_pool.py`
- `kdn_server/sclient/scheduler_client.py`
- `proxy/proxy_cli.py`
- `proxy/README.md`
- `test/demo_kdn.py`
- `README.md`
- `proxy/strategy/base.py`
- `proxy/strategy/factory.py`
- `proxy/strategy/round_robin.py`

维护者：heyao

---

## 260201：Proxy CLI 显示输出功能

### 改动

- 支持 `proxy_cli.py` 显示 Instance 池和 Proxy 信息。
- 补充 Proxy README 使用方法。

### 涉及文件

- `proxy/proxy_cli.py`
- `proxy/README.md`

维护者：heyao

---

## 260131：Instance 功能完善

### 改动

- Instance 支持启动多个不同端口，解决多个 Instance 下 Proxy 注册覆盖问题。
- 优化 Proxy 和 Instance 之间的交互日志。

### 涉及文件

- `proxy/resource/p_control_plane.py`
- `instance/instance_api.py`
- `test/demo_instance.py`

维护者：heyao

---

## 260130：v0.1.1 Proxy 与 Instance 接口功能完善

### 改动

- 实现 Proxy 控制平面 FastAPI，默认端口 `8002`。
- 构建 `InstancePool` 维护 Instance 静态信息、负载和 `last_seen`。
- Proxy lifespan 构建 InstancePool、注入控制平面并启动控制平面。
- Instance 支持向 Proxy register / heartbeat / unregister。

### 涉及文件

- `proxy/proxy.py`
- `core/config.py`
- `instance/instance_api.py`
- `test/demo_instance.py`
- `proxy/resource/instance_pool.py`
- `proxy/resource/p_control_plane.py`
- `instance/pclient/proxy_client.py`

维护者：heyao

---

## 260129：Proxy 功能完善

### 改动

- Proxy 启动时自动注册 Scheduler，周期心跳，退出注销。
- 新增 `proxy/sclient` 维护 Scheduler client。
- 新增 `proxy/metrics` 预留本地资源整合。
- 明确 Proxy 双平面结构：业务平面 `8001`，控制平面 `8002`。

### 涉及文件

- `proxy/proxy.py`
- `core/config.py`
- `proxy/sclient/scheduler_client.py`
- `proxy/metrics/local_metrics.py`

维护者：heyao

---

## 260128：Scheduler 控制平面维护结构构建，Proxy 对接接口构建

### 改动

- 新增 Proxy pool 静态 / 动态信息结构体。
- Scheduler 启动业务平面、资源池和控制平面。
- Scheduler 实现轮询调度策略。
- `demo_scheduler.py` 增加 `--strategy` 参数。
- 调度策略判定迁移至 `build_request`。
- 丰富 Scheduler CLI。

### 涉及文件

- `core/config.py`
- `core/request.py`
- `scheduler/resource/control_plane.py`
- `scheduler/scheduler.py`
- `scheduler/scheduler_cli.py`
- `test/demo_scheduler.py`
- `scheduler/resource/proxy_pool.py`
- `scheduler/strategy/base.py`
- `scheduler/strategy/factory.py`
- `scheduler/strategy/round_robin.py`

维护者：heyao

---

## 260127：说明性文件更新，Scheduler 控制平面接口部署

### 改动

- 更新 `env/README.md`，记录 vLLM + LMCache 镜像构建步骤。
- 新增启动脚本，支持容器和多窗口测试。
- `demo_scheduler.py` 本地配置参数抽离到 `core/config.py`。
- Scheduler 目录按 knowledge / resource 调整。
- 新增 Scheduler 控制平面接口。

### 涉及文件

- `env/README.md`
- `core/config.py`
- `test/demo_scheduler.py`
- `scheduler/scheduler.py`
- `test/quick_start_docker.sh`
- `scheduler/resource/control_plane.py`

维护者：chen, heyao

---

## 260126：v0.1.0 重构 Scheduler / Proxy / Request 的知识库维护

### 改动

- KDN `/search/text` 支持按 field 回传。
- KDN 支持 `/snapshot` 返回知识库状态。
- Scheduler 初始化从 KDN snapshot 抓取知识索引并构建知识清单。
- `knowledge_base` 支持 sha256 到 int64 映射。
- 优化 Scheduler CLI。
- Scheduler 支持动态同步 KDN 知识库状态，采用两阶段增量刷新。

### 涉及文件

- `kdn_server/text_db.py`
- `kdn_server/kdn_api.py`
- `scheduler/__init__.py`
- `scheduler/scheduler.py`
- `scheduler/kdn_client.py`
- `scheduler/scheduler_cli`
- `store/knowledge_base.py`
- `core/request.py`
- `proxy/proxy.py`
- `test/demo_scheduler.py`
- `scheduler/kdn_sync.py`

维护者：heyao

---

## 260123：完善 KDN 服务器功能

### 改动

- 集成 `kv_builder` 状态位，扩展文本块数据位，可通过 `kid` 查询是否已有 KVCache。
- SQLite 增加 KV 元字段，`kv_builder` 完成后回写。
- `kdn_register_cli.py` 集成注册、查询文本知识和 KVCache 块。

### 涉及文件

- `kdn_server/text_db.py`
- `kdn_server/kdn_api.py`
- `kdn_server/kv_builder.py`
- `kdn_server/kdn_register_cli.py`
- `scheduler/kdn_client.py`

维护者：heyao

---

## 260121：构建 KDN 服务器数据结构

### 改动

- 规范化 KDN 知识块存储与命名，采用文本 hash 生成唯一 ID。
- 使用 SQLite 构建索引。
- 构造 KVCache 库，支持从 Redis 存储 CacheGen 压缩 KVCache。
- 实现 KVCache 向 Redis 重新注入。
- 维护 KDN Server README。

### 涉及文件

- `test/demo_kdn.py`
- `kdn_server/kdn_api.py`
- `kdn_server/text_db.py`
- `kdn_server/kdn_register_cli.py`
- `kdn_server/kv_builder.py`
- `kdn_server/kv_injector.py`
- `util/kdn_build_kv.py`

维护者：heyao

---

## 260120：系统优化

### 改动

- 优化 `client.py` 流式传输显示。
- 解决 Proxy 在 chat / completion 模式下无法嵌入知识的问题。

### 涉及文件

- `client/client.py`
- `proxy/proxy.py`

维护者：heyao
