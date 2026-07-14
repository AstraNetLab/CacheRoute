"""
demo_proxy.py

启动 Proxy 服务，用于接收 Scheduler 转发的 Request payload。
"""

import uvicorn
import sys
import argparse
import os
import subprocess
import atexit


from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from core import config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run CacheRoute Proxy")
    parser.add_argument("--host", type=str, default=None, help="proxy listen host (default from config/env)")
    parser.add_argument("--port", type=int, default=None, help="proxy listen port (default from config/env)")
    parser.add_argument(
        "--strategy",
        type=str,
        default=None,
        help="instance scheduling strategy (e.g., round_robin, least_inflight)",
    )
    parser.add_argument(
        "--kdn-links-json",
        type=str,
        default=config.PROXY_KDN_LINKS_JSON,
        help="optional JSON string for PROXY_KDN_LINKS_JSON (CacheRoute topology tiers)",
    )
    parser.add_argument(
        "--injection-strategy",
        type=str,
        default=None,
        help="proxy injection strategy (default|iws)",
    )
    parser.add_argument(
        "--ready-release-policy",
        type=str,
        default=None,
        choices=("ordered", "text_bypass"),
        help="ready release policy (ordered|text_bypass)",
    )
    parser.add_argument(
        "--proxy-ui",
        dest="proxy_ui",
        action="store_true",
        default=True,
        help="start lightweight browser Proxy UI (default: enabled)",
    )
    parser.add_argument(
        "--no-proxy-ui",
        dest="proxy_ui",
        action="store_false",
        help="do not start the browser Proxy UI",
    )
    parser.add_argument(
        "--proxy-ui-listen",
        type=str,
        default=os.environ.get("PROXY_UI_LISTEN", "127.0.0.1:8202"),
        help="Proxy UI listen address as host:port",
    )
    parser.add_argument(
        "--proxy-ui-url",
        type=str,
        default=os.environ.get("PROXY_UI_URL", ""),
        help="browser-facing Proxy UI URL to print",
    )
    args = parser.parse_args()

    if args.strategy:
        os.environ["PROXY_INSTANCE_STRATEGY"] = args.strategy
    if args.injection_strategy:
        normalized = args.injection_strategy.strip().lower()
        if normalized not in {"default", "iws"}:
            parser.error("--injection-strategy must be one of: default, iws")
        os.environ["PROXY_INJECTION_STRATEGY"] = normalized
    if args.kdn_links_json and str(args.kdn_links_json).strip():
        os.environ["PROXY_KDN_LINKS_JSON"] = args.kdn_links_json
    if args.ready_release_policy:
        os.environ["PROXY_READY_RELEASE_POLICY"] = args.ready_release_policy

    cfg_host = os.environ.get("PROXY_DP_HOST", config.PROXY_DP_HOST)
    cfg_port = int(os.environ.get("PROXY_DP_PORT", config.PROXY_DP_PORT))
    host = args.host if args.host is not None else cfg_host
    port = args.port if args.port is not None else cfg_port

    # Keep data-plane bind address and scheduler-advertised address aligned for demos.
    os.environ["PROXY_ADVERTISE_HOST"] = host
    os.environ["PROXY_ADVERTISE_PORT"] = str(port)
    os.environ["PROXY_DP_HOST"] = host
    os.environ["PROXY_DP_PORT"] = str(port)

    ui_proc = None
    if args.proxy_ui:
        try:
            ui_host, ui_port_raw = args.proxy_ui_listen.rsplit(":", 1)
            ui_port = int(ui_port_raw)
        except ValueError:
            parser.error("--proxy-ui-listen must use host:port format")

        cp_host = os.environ.get("PROXY_CP_HOST", config.PROXY_CP_HOST)
        cp_port = int(os.environ.get("PROXY_CP_PORT", config.PROXY_CP_PORT))
        ui_env = os.environ.copy()
        ui_env.setdefault("PROXY_UI_PROXY_CP_URL", f"http://{cp_host}:{cp_port}")
        ui_env.setdefault("PROXY_UI_SCHEDULER_CP_URL", os.environ.get("SCHEDULER_CP_URL", config.SCHEDULER_CP_URL))
        ui_env.setdefault("PROXY_UI_PROXY_ID", os.environ.get("PROXY_ID", f"hp_{host}:{port}"))
        ui_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "UI.proxy_ui.proxy_ui_server:app",
                "--host",
                ui_host,
                "--port",
                str(ui_port),
                "--log-level",
                "warning",
            ],
            cwd=str(ROOT_DIR),
            env=ui_env,
        )

        def _cleanup_proxy_ui():
            if ui_proc and ui_proc.poll() is None:
                ui_proc.terminate()

        atexit.register(_cleanup_proxy_ui)
        ui_url = args.proxy_ui_url.strip() or f"http://{ui_host}:{ui_port}"
        print(f"[demo_proxy] Proxy UI available at: {ui_url}", flush=True)

    from proxy import proxy  # 确保在设置环境变量后导入

    try:
        # 选择一个与 Scheduler 不同的端口，例如 8001
        uvicorn.run(proxy, host=host, port=port, reload=False)
    finally:
        if ui_proc and ui_proc.poll() is None:
            ui_proc.terminate()
            try:
                ui_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                ui_proc.kill()
