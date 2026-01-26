import os, sys
import uvicorn

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from kdn_server.kdn_api import kdn

KDN_TEXT_DB_DIR = ROOT_DIR / "kdn_server" / "text_database"
KDN_DATA_YAML = ROOT_DIR / "data" / "kdn_text_base.yaml"
KDN_KV_DB_DIR = ROOT_DIR / "kdn_server" / "KV_database"

if __name__ == "__main__":
    # 这里暴露配置（你想要的“demo里配置，不在模块里写死”）
    os.environ["KDN_TEXT_DB_DIR"] = str(KDN_TEXT_DB_DIR)
    os.environ["KDN_KV_DB_DIR"] = str(KDN_KV_DB_DIR)
    os.environ["KDN_EMBEDDING_MODEL"] = "/workspace/llm-stack/CacheRoute/model/embedder/intfloat__multilingual-e5-large-instruct"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    uvicorn.run(kdn, host="127.0.0.1", port=9101, log_level="info")
