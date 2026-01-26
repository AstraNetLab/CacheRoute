# demo_scheduler.py
"""
Scheduler_v1启动demo：
  - 引用 scheduler.py 里的 api
  - 使用 uvicorn 启动 HTTP 服务
"""

import os, sys, logging, time
import uvicorn
import threading

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from scheduler import scheduler


# 在 demo 里配置要预热的模型路径以及知识库路径
MODEL_PATH = "/workspace/llm-stack/models/LLM-Research/Meta-Llama-3-70B-Instruct"
KNOWLEDGE_YAML_PATH = ROOT_DIR / "data" / "knowledge_base.yaml"
EMBEDDING_MODEL = "/workspace/llm-stack/CacheRoute/model/embedder/intfloat__multilingual-e5-large-instruct"
KDN_BASE_URL = "http://127.0.0.1:9101"

def main():
    # logging配置
    logging.basicConfig(
        level=logging.INFO,  # 根 logger 级别设为 INFO
        format=" [%(levelname)s] %(name)s: %(message)s",
    )

    # 把模型路径暴露给 scheduler（scheduler.py 里通过 os.getenv 读取）
    os.environ["SCHEDULER_MODEL_PATH"] = MODEL_PATH
    os.environ["SCHEDULER_TOKENIZER_MAP"]='{"llama3-70b":"/workspace/llm-stack/models/LLM-Research/Meta-Llama-3-70B-Instruct"}'
    os.environ["SCHEDULER_KNOWLEDGE_YAML"] = str(KNOWLEDGE_YAML_PATH)
    os.environ["SCHEDULER_KDN_BASE_URL"] = str(KDN_BASE_URL).rstrip("/")
    os.environ["SCHEDULER_EMBEDDING_MODEL"] = EMBEDDING_MODEL
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


    # 配置 uvicorn.Server
    config = uvicorn.Config(scheduler, host="127.0.0.1", port=7001, reload=False)
    server = uvicorn.Server(config)
    server.run()
    print("[DEMO] Scheduler stopped, demo exit.")


if __name__ == "__main__":
    main()
