"""
依次启动
demo_scheduler_v1_instance
demo_scheduler_v1
demo_scheduler_v1_proxy
demo_scheduler_v1_client（关掉，转client.py）
"""

import subprocess
import time
import sys
import socket
import threading


def wait_for_port(host: str, port: int, timeout: float = 30.0):
    """端口探活"""
    start = time.time()
    while True:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                print(f"[OK] {host}:{port} 已经可以连接")
                return
        except OSError:
            if time.time() - start > timeout:
                raise TimeoutError(f"等待 {host}:{port} 启动超过 {timeout}s，服务似乎启动失败")
            time.sleep(0.2)


def stream_output(process: subprocess.Popen, name: str):
    """时读取子进程输出"""
    def _stream(pipe, prefix):
        for line in iter(pipe.readline, b''):
            print(f"{line.decode().rstrip()}")
    threading.Thread(target=_stream, args=(process.stdout, "STDOUT"), daemon=True).start()
    threading.Thread(target=_stream, args=(process.stderr, "STDERR"), daemon=True).start()


def start_service(script: str, name: str) -> subprocess.Popen:
    """启动后台服务（保持运行）"""
    print(f"[START] 启动 {name} ({script})")
    p = subprocess.Popen(
        [sys.executable, script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        close_fds=True
    )
    stream_output(p, name)
    return p


def run_client(script: str):
    """启动 client（同步执行）"""
    print(f"[START] 启动 Client ({script})")
    # Client 前台执行，完成后退出
    p = subprocess.Popen(
        [sys.executable, script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stream_output(p, "Client")
    p.wait()
    print("[DONE] Client 执行完成")


if __name__ == "__main__":
    proxy = None
    scheduler = None
    Instance = None

    try:
        # 启动KDN服务器
        kdn = start_service("demo_kdn.py", "KDN")
        wait_for_port("127.0.0.1", 9101)

        # 启动 Instance
        Instance = start_service("demo_instance.py", "Instance")
        wait_for_port("127.0.0.1", 9001)

        # 启动 Proxy
        proxy = start_service("demo_proxy.py", "Proxy")
        wait_for_port("127.0.0.1", 8001)

        # 启动 Scheduler
        scheduler = start_service("demo_scheduler.py", "Scheduler")
        wait_for_port("127.0.0.1", 7001)

        # 启动 Client（这个demo为发送两条固定request，新的接口运行client/client.py）
        # run_client("demo_client.py")

        print("\n系统仍保持运行，你可以按 Ctrl + C 退出。")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[STOP] 收到 Ctrl + C，正在关闭子进程...")

    finally:
        if kdn and kdn.poll() is None:
            kdn.terminate()
        if scheduler and scheduler.poll() is None:
            scheduler.terminate()
        if proxy and proxy.poll() is None:
            proxy.terminate()
        if Instance and Instance.poll() is None:
            Instance.terminate()
        print("[CLEAN] 所有进程已结束")
