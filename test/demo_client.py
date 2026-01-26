#!/usr/bin/env python3
"""

已更新（2025.12.16）

简单的调度器客户端 Demo：
  - 向 scheduler 发送 HTTP 请求
  - 测试 /v1/chat/completions 和 /v1/completions
  - 显示完整的应用层负载（HTTP 头 + JSON body）
  - 两种模式 python --with-ui和默认（命令行模式）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _ensure_project_root_on_syspath() -> None:
    """
    兜底：允许你直接在 test/ 目录运行 demo_client.py，
    也能 import 到项目根目录下的 client/、UI/ 等包。
    """
    root = Path(__file__).resolve().parents[1]  # test/ -> project root
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def run_cli() -> None:
    """
    命令行模式：直接复用 client.py 的 main()。
    """
    _ensure_project_root_on_syspath()

    # 你的 client 模块如果是 client/client.py，则推荐这样 import
    # - 若你已做了 client/__init__.py from .client import *，也可直接 import client
    try:
        from client.client import run_repl as client_entry  # client/ 目录 + client.py
    except Exception:
        # 兜底：如果你把 client.py 放在根目录（非包结构）
        from client import run_repl as client_entry  # type: ignore

    print("[demo_client] entering REPL... (如果你看不到提示符，直接回车一次)", flush=True)
    client_entry()


def run_ui(host: str, port: int, scheduler_url: str) -> None:
    """
    UI 模式：启动 UI FastAPI App，并提示访问地址。
    """
    _ensure_project_root_on_syspath()

    # UI 工厂函数（你 UI 目录下 app.py 需要提供 create_client_ui_app）
    from UI.client_ui.app import create_client_ui_app  # type: ignore

    import uvicorn

    app = create_client_ui_app(default_scheduler_url=scheduler_url)

    ui_url = f"http://{host}:{port}/ui/client"
    print("\n" + "=" * 72)
    print("[Client UI] 已启动")
    print(f"[Client UI] 访问地址：{ui_url}")
    print("=" * 72 + "\n")

    uvicorn.run(app, host=host, port=port, reload=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CacheRoute Client demo: CLI by default; add --with-ui to start browser UI."
    )
    parser.add_argument(
        "--with-ui",
        action="store_true",
        help="启动浏览器 UI（FastAPI + Tailwind）而不是 CLI 模式",
    )
    parser.add_argument("--ui-host", default="127.0.0.1", help="UI 监听地址")
    parser.add_argument("--ui-port", type=int, default=7071, help="UI 监听端口")
    parser.add_argument(
        "--scheduler-url",
        default="http://127.0.0.1:7001/v1/chat/completions",
        help="UI 默认填充的 Scheduler URL",
    )

    args = parser.parse_args()

    if args.with_ui:
        run_ui(args.ui_host, args.ui_port, args.scheduler_url)
    else:
        run_cli()


if __name__ == "__main__":
    main()
