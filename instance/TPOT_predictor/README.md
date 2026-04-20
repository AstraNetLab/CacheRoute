# TPOT Predictor

`TPOT_predictor` 参考 `TTFT_predictor` 的结构实现，目标是采集并输出不同 `(prompt_length, batch_size)` 组合下，**每个任务、每个 token 的 TPOT（Time Per Output Token）**。

> 这里的 TPOT 指相邻两个输出 token 的时间差；首 token 时间记为 TTFT。

---

## 1. 目录结构

- `tpot_predictor.py`：对外异步入口，负责统一触发 benchmark。
- `tpot_regressor.py`：核心采集器（当前偏测量与汇总，不做线性拟合）。
- `request_generator.py`：生成目标 prompt，并发起流式请求，逐 token 抓取时间。
- `__init__.py`：导出常用接口。

---

## 2. 关键设计（对齐你的要求）

### 2.1 固定请求组约束

对同一组 `(batch_size, prompt_length)`：

- 每个任务使用相同 `prompt_length`。
- 每个任务使用相同 `max_tokens`。

即一次 round 的 `bs` 个请求只改变内容随机性，不改变长度口径。

### 2.2 每出一个 token 就抓一次

在 `send_stream_request_for_tpot(...)` 中按流式 chunk 记录时间点：

- 第 1 个 token：记录 `TTFT`。
- 第 n 个 token（n>=2）：`TPOT_n = t_n - t_(n-1)`。

### 2.3 每抓一次长度 +1

每条任务记录中都有：

- `token_index`：第几个生成 token。
- `sequence_length = prompt_length + token_index`：满足“每抓一次 length + 1”的要求。
- `tpot_seconds`：该 token 对应时间间隔。

---

## 3. 输出数据格式

运行后会导出 JSON（默认：`instance/TPOT_predictor/output/tpot_results.json`）：

- `summary.configs`：每个 `(bs, pl)` 的聚合统计（avg/min/max TPOT，avg TTFT）。
- `records`：每个任务的完整时间序列。

单个任务记录示例：

```json
{
  "request_id": "bs4-pl512-r1-t2-9",
  "batch_size": 4,
  "prompt_length": 512,
  "max_tokens": 16,
  "ttft_seconds": 0.134,
  "token_steps": [
    {"token_index": 1, "sequence_length": 513, "tpot_seconds": 0.134},
    {"token_index": 2, "sequence_length": 514, "tpot_seconds": 0.012},
    {"token_index": 3, "sequence_length": 515, "tpot_seconds": 0.011}
  ]
}
```

---

## 4. 使用方式

## 4.1 直接脚本运行

```bash
cd instance/TPOT_predictor
python tpot_predictor.py
```

默认行为：

- 遍历 `WARM_UP_CONFIGS_DEFAULT`。
- 每个配置重复 `repeats=2`（示例 main 中）。
- 每请求生成 `max_tokens=16`。

## 4.2 作为模块调用

```python
import asyncio
from tpot_predictor import collect_tpot_matrix

async def main():
    reg = await collect_tpot_matrix(
        configs=[(1, 256), (4, 512)],
        max_tokens=32,
        repeats=3,
    )
    reg.export_json("instance/TPOT_predictor/output/my_tpot.json")

asyncio.run(main())
```

---

## 5. 参数建议

- `max_tokens`：建议 >= 8，才能更稳定地观察 TPOT 分布。
- `repeats`：建议 3~5，减少偶然抖动。
- `concurrency`：默认跟随 `bs`；若环境容易超时，可手动调小。

---

## 6. 注意事项

1. 当前流式解析逻辑按“收到非空 chunk 即视为一个 token 事件”，依赖你的 vLLM 流式行为。
2. 若后续要更严谨，可改为解析 SSE 中 `delta.content` / `logprobs` 精确 token 数。
3. 本方案先保障“结构和流程可跑通”，并保持与 `TTFT_predictor` 相似的代码组织，便于后续扩展到回归预测。
