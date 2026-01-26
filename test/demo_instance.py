import uvicorn
import os
import sys

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from instance import instance  # 确保与 Proxy.py 在同一包/目录下

def main():
    # ====== 启动 Instance 服务 ======
    # 注意：这里的端口 8081 是 “Proxy -> Instance” 用的端口
    uvicorn.run(instance, host="127.0.0.1", port=9001, reload=False)

if __name__ == "__main__":
    main()