import asyncio
import hashlib
import itertools
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional

import aiohttp

_REQUEST_SEQ = itertools.count()


def _timehash_uuid() -> str:
    raw = f"{time.time_ns()}-{next(_REQUEST_SEQ)}"
    digest32 = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return str(uuid.UUID(digest32))


def generate_prompt_with_tokens(tokenizer, target_token_count: int) -> str:
    """生成 token 数不小于目标值的 prompt。"""
    if target_token_count <= 0:
        return ""

    uuid_prefix = f"request_uuid={_timehash_uuid()} "
    prefix_token_ids = tokenizer.encode(uuid_prefix, add_special_tokens=False)
    if not prefix_token_ids:
        return "Error"

    prompt_ids = list(prefix_token_ids)
    if len(prompt_ids) < target_token_count:
        base_text = "This is a long context test for TPOT benchmark. "
        base_token_ids = tokenizer.encode(base_text, add_special_tokens=False)
        if not base_token_ids:
            return "Error"

        remain = target_token_count - len(prompt_ids)
        body_token_ids = []
        while len(body_token_ids) < remain:
            body_token_ids.extend(base_token_ids)
        prompt_ids.extend(body_token_ids[:remain])
    else:
        prompt_ids = prompt_ids[:target_token_count]

    prompt = tokenizer.decode(prompt_ids, skip_special_tokens=False)

    final_token_ids = tokenizer.encode(prompt, add_special_tokens=False)
    if len(final_token_ids) >= target_token_count:
        return prompt

    while len(final_token_ids) < target_token_count:
        prompt += " padding_chunk_for_tpot_benchmark."
        final_token_ids = tokenizer.encode(prompt, add_special_tokens=False)
    return prompt


@dataclass
class TokenStep:
    token_index: int
    generated_length: int
    delta_seconds: float


@dataclass
class TaskTPOTResult:
    success: bool
    ttft_seconds: Optional[float]
    token_steps: List[TokenStep]
    error: Optional[str] = None


async def send_stream_request_for_tpot(
    session: aiohttp.ClientSession,
    host: str,
    port: int,
    model: str,
    prompt: str,
    max_tokens: int,
) -> TaskTPOTResult:
    """
    流式请求并按 token 抓取 TPOT。

    约定：
    - TTFT = 第一个 token 到达时间 - 请求发起时间
    - 第 n 个 token 的 TPOT = 第 n 个 token 到达时间 - 第 n-1 个 token 到达时间
    - 每抓到一个 token，generated_length = prompt_len + n
    """
    api_url = f"http://{host}:{port}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": 0.01,
    }

    start_ts = time.perf_counter()
    last_token_ts: Optional[float] = None
    token_idx = 0
    token_steps: List[TokenStep] = []
    ttft_seconds: Optional[float] = None

    try:
        async with session.post(api_url, headers=headers, json=payload) as resp:
            if resp.status != 200:
                err = await resp.text()
                return TaskTPOTResult(
                    success=False,
                    ttft_seconds=None,
                    token_steps=[],
                    error=f"non-200 status={resp.status}, body={err[:200]}",
                )

            async for chunk in resp.content.iter_any():
                if not chunk:
                    continue

                # 只要收到一个非空 chunk，就认为至少产出了一个 token（在当前 vLLM 流式输出假设下）
                now_ts = time.perf_counter()
                token_idx += 1
                if last_token_ts is None:
                    ttft_seconds = now_ts - start_ts
                    delta = ttft_seconds
                else:
                    delta = now_ts - last_token_ts

                token_steps.append(
                    TokenStep(
                        token_index=token_idx,
                        generated_length=token_idx,
                        delta_seconds=delta,
                    )
                )
                last_token_ts = now_ts

                if token_idx >= max_tokens:
                    break

            if token_idx == 0:
                fallback = await resp.text()
                return TaskTPOTResult(
                    success=False,
                    ttft_seconds=None,
                    token_steps=[],
                    error=f"empty stream, fallback={fallback[:200]}",
                )

            return TaskTPOTResult(
                success=True,
                ttft_seconds=ttft_seconds,
                token_steps=token_steps,
                error=None,
            )

    except Exception as exc:
        return TaskTPOTResult(
            success=False,
            ttft_seconds=None,
            token_steps=[],
            error=str(exc),
        )


async def bounded_gather(coros: List, concurrency: int):
    semaphore = asyncio.Semaphore(concurrency)

    async def _run(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(*[_run(c) for c in coros])
