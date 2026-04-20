import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from tpot_regressor import TPOTRegressor

VLLM_CONFIG_DEFAULT = {
    "host": "0.0.0.0",
    "port": 8000,
    "model_id": "llama3-70b",
    "tokenizer_path": "/workspace/llm-stack/models/LLM-Research/Meta-Llama-3-70B-Instruct/",
}

BATCH_SIZES_TO_TEST = range(1, 9)
TOKEN_LENGTHS_TO_TEST = range(64, 2048, 64)

WARM_UP_CONFIGS_DEFAULT = [
    (bs, pl)
    for bs in BATCH_SIZES_TO_TEST
    for pl in TOKEN_LENGTHS_TO_TEST
    if bs * pl <= 10000
]

_regressor: Optional[TPOTRegressor] = None
_lock = asyncio.Lock()


async def get_regressor() -> TPOTRegressor:
    global _regressor
    async with _lock:
        if _regressor is None:
            print("[TPOT Predictor] Initializing collector...")
            _regressor = TPOTRegressor()
    return _regressor


async def collect_tpot_matrix(
    configs: List[Tuple[int, int]],
    vllm_config: Dict[str, Any] = VLLM_CONFIG_DEFAULT,
    max_tokens: int = 16,
    repeats: int = 3,
    concurrency: Optional[int] = None,
):
    regressor = await get_regressor()
    regressor.clear_data()
    await regressor.trigger_benchmark_requests(
        test_configs=configs,
        vllm_config=vllm_config,
        max_tokens=max_tokens,
        repeats_per_config=repeats,
        concurrency=concurrency,
    )
    return regressor


async def run_default_benchmark(
    max_tokens: int = 16,
    repeats: int = 3,
    output_path: str = "instance/TPOT_predictor/output/tpot_results.json",
):
    regressor = await collect_tpot_matrix(
        configs=WARM_UP_CONFIGS_DEFAULT,
        vllm_config=VLLM_CONFIG_DEFAULT,
        max_tokens=max_tokens,
        repeats=repeats,
    )
    regressor.export_json(output_path)
    return regressor.build_summary()


def summarize_results(summary: Dict[str, Any]) -> str:
    lines = ["\n=== TPOT Benchmark Summary ==="]
    for cfg in summary.get("configs", []):
        lines.append(
            "BS={batch_size}, PL={prompt_length}, tasks={tasks}, "
            "avg_ttft={avg_ttft_ms:.2f}ms, avg_tpot={avg_tpot_ms:.2f}ms, "
            "min/max_tpot={min_tpot_ms:.2f}/{max_tpot_ms:.2f}ms".format(
                **{
                    **cfg,
                    "avg_ttft_ms": cfg.get("avg_ttft_ms") or 0.0,
                    "avg_tpot_ms": cfg.get("avg_tpot_ms") or 0.0,
                    "min_tpot_ms": cfg.get("min_tpot_ms") or 0.0,
                    "max_tpot_ms": cfg.get("max_tpot_ms") or 0.0,
                }
            )
        )
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def _main():
        summary = await run_default_benchmark(max_tokens=16, repeats=2)
        print(summarize_results(summary))

    asyncio.run(_main())
