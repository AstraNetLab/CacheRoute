#!/usr/bin/env python3
"""Non-destructive validation for the CacheRoute v1 serving environment."""
from __future__ import annotations

import argparse
import json
import os
import sys
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[4]
TARGET_VERSIONS = {
    "torch": "2.11.0",
    "vllm": "0.25.1",
    "lmcache": "0.5.2",
}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.details: dict[str, Any] = {}

    def ok(self, message: str) -> None:
        print(f"[OK] {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"[WARN] {message}")

    def error(self, message: str) -> None:
        self.errors.append(message)
        print(f"[ERROR] {message}")


def normalized_version(value: str) -> str:
    return value.split("+", 1)[0]


def http_get(url: str, timeout: float = 5.0) -> tuple[int, str]:
    request = Request(url, headers={"User-Agent": "CacheRoute-v1-check"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def check_http(
    report: Report,
    name: str,
    url: str,
    marker: str | None,
    require_running: bool,
) -> None:
    try:
        status, body = http_get(url)
    except (URLError, TimeoutError, OSError) as exc:
        message = f"{name} unavailable at {url}: {exc}"
        if require_running:
            report.error(message)
        else:
            report.warn(message)
        return

    if status != 200:
        message = f"{name} returned HTTP {status} at {url}"
        if require_running:
            report.error(message)
        else:
            report.warn(message)
        return

    if marker and marker not in body:
        message = f"{name} is reachable but marker {marker!r} is absent"
        if require_running:
            report.error(message)
        else:
            report.warn(message)
        return

    report.ok(f"{name}: HTTP 200 ({len(body)} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-dir",
        default=os.getenv(
            "MODEL_DIR",
            "/workspace/llm-stack/models/LLM-Research/Meta-Llama-3-70B-Instruct",
        ),
    )
    parser.add_argument("--redis-host", default=os.getenv("REDIS_HOST", "127.0.0.1"))
    parser.add_argument("--redis-port", type=int, default=int(os.getenv("REDIS_PORT", "6379")))
    parser.add_argument("--redis-db", type=int, default=int(os.getenv("REDIS_DB", "0")))
    parser.add_argument("--vllm-url", default="http://127.0.0.1:8000")
    parser.add_argument("--lmcache-http-url", default="http://127.0.0.1:8080")
    parser.add_argument("--expected-gpus", type=int, default=None)
    parser.add_argument("--allow-no-gpu", action="store_true")
    parser.add_argument("--skip-redis", action="store_true")
    parser.add_argument(
        "--require-running",
        action="store_true",
        help="Treat unavailable Redis/LMCache/vLLM services as errors.",
    )
    args = parser.parse_args()

    report = Report()
    print("===== CacheRoute v1 environment check =====")

    report.details["repo_root"] = str(REPO_ROOT)
    if (REPO_ROOT / "core" / "runtime_compat.py").is_file():
        report.ok(f"repository root: {REPO_ROOT}")
    else:
        report.error(f"repository root is invalid: {REPO_ROOT}")

    profile = os.getenv("CACHEROUTE_RUNTIME_PROFILE", "")
    report.details["runtime_profile"] = profile
    if profile == "v1":
        report.ok("CACHEROUTE_RUNTIME_PROFILE=v1")
    else:
        report.error(
            "CACHEROUTE_RUNTIME_PROFILE must be v1; source "
            "env/docker/cu130/scripts/activate_v1.sh first"
        )

    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    report.details["python"] = python_version
    if sys.version_info >= (3, 12):
        report.ok(f"Python {python_version}: {sys.executable}")
    else:
        report.error(f"Python >=3.12 required, found {python_version}")

    for package, expected in TARGET_VERSIONS.items():
        try:
            actual = metadata.version(package)
        except metadata.PackageNotFoundError:
            report.error(f"missing package: {package}=={expected}")
            continue
        report.details[package] = actual
        if normalized_version(actual) == expected:
            report.ok(f"{package} {actual}")
        else:
            report.error(f"{package} expected {expected}, found {actual}")

    try:
        import torch
    except Exception as exc:
        report.error(f"torch import failed: {exc}")
    else:
        cuda_runtime = str(torch.version.cuda)
        cuda_available = bool(torch.cuda.is_available())
        gpu_count = int(torch.cuda.device_count())
        report.details.update(
            {
                "torch_cuda_runtime": cuda_runtime,
                "cuda_available": cuda_available,
                "gpu_count": gpu_count,
            }
        )
        if cuda_runtime.startswith("13.0"):
            report.ok(f"PyTorch CUDA runtime {cuda_runtime}")
        else:
            report.error(f"expected PyTorch CUDA runtime 13.0, found {cuda_runtime}")

        if cuda_available:
            report.ok(f"CUDA available; visible GPU count={gpu_count}")
        elif args.allow_no_gpu:
            report.warn("CUDA is unavailable, accepted by --allow-no-gpu")
        else:
            report.error("CUDA is unavailable; run the container with --gpus all")

        expected_gpus = args.expected_gpus
        if expected_gpus is None:
            visible = os.getenv("CUDA_VISIBLE_DEVICES", "").strip()
            expected_gpus = len([item for item in visible.split(",") if item.strip()]) if visible else 8
        if cuda_available and gpu_count < expected_gpus:
            report.error(f"expected at least {expected_gpus} visible GPUs, found {gpu_count}")

    model_dir = Path(args.model_dir)
    report.details["model_dir"] = str(model_dir)
    if model_dir.is_dir():
        report.ok(f"model directory exists: {model_dir}")
    else:
        report.error(f"model directory not found: {model_dir}")

    required_scripts = [
        REPO_ROOT / "env/docker/cu130/scripts/start_lmcache_mp.sh",
        REPO_ROOT / "env/docker/cu130/scripts/start_vllm_mp.sh",
        REPO_ROOT / "scripts/validate_v1_kdn_roundtrip.py",
    ]
    for script in required_scripts:
        if script.is_file():
            report.ok(f"script exists: {script.relative_to(REPO_ROOT)}")
        else:
            report.error(f"script missing: {script.relative_to(REPO_ROOT)}")

    if not args.skip_redis:
        try:
            import redis

            client = redis.Redis(
                host=args.redis_host,
                port=args.redis_port,
                db=args.redis_db,
                decode_responses=False,
                socket_connect_timeout=3,
                socket_timeout=5,
            )
            pong = bool(client.ping())
            size = int(client.dbsize())
            report.details["redis_dbsize"] = size
            if pong:
                report.ok(
                    f"Redis {args.redis_host}:{args.redis_port}/{args.redis_db}; DBSIZE={size}"
                )
        except Exception as exc:
            message = f"Redis unavailable: {exc}"
            if args.require_running:
                report.error(message)
            else:
                report.warn(message)

    check_http(
        report,
        "vLLM model endpoint",
        f"{args.vllm_url.rstrip('/')}/v1/models",
        None,
        args.require_running,
    )
    check_http(
        report,
        "vLLM metrics",
        f"{args.vllm_url.rstrip('/')}/metrics",
        "vllm:external_prefix_cache_queries_total",
        args.require_running,
    )
    check_http(
        report,
        "LMCache MP metrics",
        f"{args.lmcache_http_url.rstrip('/')}/metrics",
        "lmcache_mp_l2_adapters",
        args.require_running,
    )

    print("\n===== Summary =====")
    print(json.dumps(report.details, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"errors={len(report.errors)} warnings={len(report.warnings)}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
