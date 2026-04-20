import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from transformers import AutoTokenizer

from request_generator import (
    bounded_gather,
    generate_prompt_with_tokens,
    send_stream_request_for_tpot,
)


@dataclass
class TPOTTaskRecord:
    request_id: str
    batch_size: int
    prompt_length: int
    max_tokens: int
    ttft_seconds: float
    # 每个元素: {token_index, sequence_length, tpot_seconds}
    token_steps: List[Dict[str, Any]]


class TPOTRegressor:
    """
    目前以“测量/统计”为主，不做参数回归。
    输出矩阵：不同 (prompt_length, batch_size) 下每任务每 token 的 TPOT。
    """

    def __init__(self):
        self._records: Dict[Tuple[int, int], List[TPOTTaskRecord]] = {}

    def clear_data(self):
        self._records = {}

    def add_record(self, record: TPOTTaskRecord):
        key = (record.batch_size, record.prompt_length)
        self._records.setdefault(key, []).append(record)

    async def trigger_benchmark_requests(
        self,
        test_configs: List[Tuple[int, int]],
        vllm_config: Dict[str, Any],
        max_tokens: int,
        repeats_per_config: int = 3,
        concurrency: Optional[int] = None,
    ):
        tokenizer = AutoTokenizer.from_pretrained(vllm_config["tokenizer_path"])
        timeout = aiohttp.ClientTimeout(total=900)
        request_counter = 0

        async with aiohttp.ClientSession(timeout=timeout) as session:
            for bs, pl in test_configs:
                print(f"[TPOT] Start config BS={bs}, PL={pl}, repeats={repeats_per_config}")

                for r in range(repeats_per_config):
                    prompts = [generate_prompt_with_tokens(tokenizer, pl) for _ in range(bs)]
                    run_coros = [
                        send_stream_request_for_tpot(
                            session=session,
                            host=vllm_config["host"],
                            port=vllm_config["port"],
                            model=vllm_config["model_id"],
                            prompt=prompt,
                            max_tokens=max_tokens,
                        )
                        for prompt in prompts
                    ]

                    start_round = time.perf_counter()
                    results = await bounded_gather(run_coros, concurrency=concurrency or bs)
                    round_ms = (time.perf_counter() - start_round) * 1000

                    success_count = 0
                    for task_idx, result in enumerate(results, start=1):
                        request_counter += 1
                        req_id = f"bs{bs}-pl{pl}-r{r+1}-t{task_idx}-{request_counter}"
                        if not result.success or result.ttft_seconds is None:
                            print(
                                f"[TPOT][WARN] req={req_id} failed, error={result.error}"
                            )
                            continue

                        success_count += 1
                        token_steps = []
                        for step in result.token_steps:
                            token_steps.append(
                                {
                                    "token_index": step.token_index,
                                    "sequence_length": pl + step.token_index,
                                    "tpot_seconds": step.delta_seconds,
                                }
                            )

                        self.add_record(
                            TPOTTaskRecord(
                                request_id=req_id,
                                batch_size=bs,
                                prompt_length=pl,
                                max_tokens=max_tokens,
                                ttft_seconds=result.ttft_seconds,
                                token_steps=token_steps,
                            )
                        )

                    print(
                        f"[TPOT] Finished BS={bs}, PL={pl}, repeat={r+1}, "
                        f"success={success_count}/{bs}, elapsed={round_ms:.1f}ms"
                    )

    def build_summary(self) -> Dict[str, Any]:
        summary: Dict[str, Any] = {"configs": []}

        for (bs, pl), records in sorted(self._records.items(), key=lambda x: (x[0][0], x[0][1])):
            tpot_values = [
                step["tpot_seconds"]
                for rec in records
                for step in rec.token_steps
                if step["token_index"] > 1
            ]
            ttft_values = [rec.ttft_seconds for rec in records]

            config_data = {
                "batch_size": bs,
                "prompt_length": pl,
                "tasks": len(records),
                "avg_ttft_ms": (statistics.mean(ttft_values) * 1000) if ttft_values else None,
                "avg_tpot_ms": (statistics.mean(tpot_values) * 1000) if tpot_values else None,
                "min_tpot_ms": (min(tpot_values) * 1000) if tpot_values else None,
                "max_tpot_ms": (max(tpot_values) * 1000) if tpot_values else None,
            }
            summary["configs"].append(config_data)

        return summary

    def export_json(self, output_path: str):
        payload = {
            "summary": self.build_summary(),
            "records": [
                asdict(rec)
                for records in self._records.values()
                for rec in records
            ],
        }
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[TPOT] Exported benchmark result => {path}")
