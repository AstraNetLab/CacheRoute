import os
import inspect
from modelscope import snapshot_download

# 强制固定缓存目录，避免 cache_dir='.' 导致换目录重新开坑
CACHE_DIR = "/workspace/models"
MODEL_ID = "LLM-Research/Meta-Llama-3-70B-Instruct"
REV = "master"

# 降并发：大文件 + 代理/网关环境下最有效
os.environ.setdefault("MODELSCOPE_DOWNLOAD_PARALLELISM", "1")

kw = dict(cache_dir=CACHE_DIR, revision=REV)

sig = inspect.signature(snapshot_download)
if "max_workers" in sig.parameters:
    kw["max_workers"] = 1
if "resume_download" in sig.parameters:
    kw["resume_download"] = True

print("Downloading to:", CACHE_DIR)
path = snapshot_download(MODEL_ID, **kw)
print("Done:", path)

