import time
from typing import Dict, Any
from CacheRoute.model import model_config
from CacheRoute.core import Request
from CacheRoute.core import TokenizerRegistry


"""
    本地验证 Request.build_request 对不同请求格式的兼容性：
        1) legacy: {"model", "user_prompt"}
        2) /v1/chat/completions: {"model", "messages":[...], ...}
        3) /v1/completions: {"model", "prompt": ... , ...}
"""
FAKE_USER_IP = "192.168.1.123"

def build_legacy_payload() -> Dict[str, Any]:
    """旧版 TCP 协议：直接传递 user_prompt。"""
    return {
        "model": "/workspace/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
        "user_prompt": "这是 legacy 协议下的简单问句。",
    }

def build_chat_completions_payload() -> Dict[str, Any]:
    """/v1/chat/completions 风格：使用 messages。"""
    return {
        "model": "/workspace/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Who are you?"},
        ],
        "max_tokens": 256,
        "temperature": 0.7,
        "top_p": 0.95,
        "stream": True,
    }

def build_completions_payload() -> Dict[str, Any]:
    """/v1/completions 风格：使用 prompt。"""
    return {
        "model": "/workspace/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
        "prompt": "用中文简单介绍一下算力网络和 KDN 的区别。",
        "max_tokens": 512,
        "temperature": 0.3,
        "top_p": 1.0,
        "stream": False,
    }

if __name__ == "__main__":
    # 调度器预热tokenizer
    TokenizerRegistry.warmup_tokenizers("/workspace/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B")

    start = time.perf_counter()
    payload_legacy = build_legacy_payload()
    req_legacy = Request.build_request(
        url_path="http://127.0.0.1:8000/v1/completions",
        payload=payload_legacy,
        user_addr=FAKE_USER_IP,
        request_id=1,
    )
    print(req_legacy)

    # 2) /v1/chat/completions
    payload_chat = build_chat_completions_payload()
    req_chat = Request.build_request(
        url_path="http://127.0.0.1:8000/v1/completions",
        payload=payload_chat,
        user_addr=FAKE_USER_IP,
        request_id=2,
    )
    print(req_chat)

    # 3) /v1/completions
    payload_comp = build_completions_payload()
    req_comp = Request.build_request(
        url_path="http://127.0.0.1:8000/v1/completions",
        payload=payload_comp,
        user_addr=FAKE_USER_IP,
        request_id=3,
    )
    print(req_comp)
    end = time.perf_counter()
    time = (end - start) * 1000
    print(f"build_request_info 耗时：{time:.4f} ms")

    # 读取任务的模型参数
    model_config = model_config.get_config_by_model(req_legacy.Prompt.model)
    print(model_config)