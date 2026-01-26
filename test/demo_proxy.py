"""
demo_proxy.py

启动 Proxy 服务，用于接收 Scheduler 转发的 Request payload。
"""

import uvicorn
import sys

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from proxy import proxy  # 确保与 Proxy.py 在同一包/目录下


if __name__ == "__main__":
    # 选择一个与 Scheduler 不同的端口，例如 8001
    uvicorn.run(proxy, host="127.0.0.1", port=8001, reload=False)
