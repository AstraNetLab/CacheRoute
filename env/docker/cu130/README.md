# CUDA 13 / vLLM 0.25.1 / LMCache 0.5.2 profile

This directory provides the additive v1 development-image profile for the
modern CacheRoute runtime. It does not replace or modify the existing CUDA 12.8
/ vLLM 0.13.x / LMCache 0.3.11 environment.

The runtime compatibility architecture is described in
[`docs/runtime_compatibility_v1.md`](../../../docs/runtime_compatibility_v1.md).

## Target stack

| Component | Version |
|---|---|
| Base image | `nvidia/cuda:13.0.0-devel-ubuntu22.04` |
| Python | `3.12.x` |
| PyTorch | `2.11.0+cu130` |
| torchvision | `0.26.0+cu130` |
| torchaudio | `2.11.0+cu130` |
| vLLM | `0.25.1` |
| LMCache | `0.5.2` |

The image uses `/opt/venv` to isolate serving dependencies from Ubuntu system
Python packages. FFmpeg is installed because current TorchCodec wheels require
its shared libraries. Rust/Cargo and Tkinter remain available for the existing
CacheRoute resource-agent and desktop-dashboard workflows.

The image sets:

```bash
CACHEROUTE_RUNTIME_PROFILE=v1
```

This selects the modern compatibility path by default. Override it at container
startup only when explicitly testing `auto` or `legacy` behavior.

## Files

- `Dockerfile`: complete CUDA 13 development image.
- `constraints.txt`: exact serving-stack versions and shared compatibility
  ranges.
- `requirements-dev.txt`: CacheRoute application/development dependencies that
  are compatible with the target stack.

`requirements-dev.txt` intentionally excludes `Booktype==1.5`. That package is
from the Python 2 era and can overwrite the modern `redis` module with invalid
Python 2 source files.

## Build

Use this directory as the Docker build context. This keeps the context small and
avoids sending models, KDN databases, logs, or other repository data to the
Docker daemon.

```bash
cd /llm-stack/CacheRoute

sudo docker build \
  -f env/docker/cu130/Dockerfile \
  -t cacheroute:dev-vllm0.25.1-lmcache0.5.2-cu130 \
  env/docker/cu130
```

With Buildx:

```bash
sudo docker buildx build \
  --load \
  --progress=plain \
  -f env/docker/cu130/Dockerfile \
  -t cacheroute:dev-vllm0.25.1-lmcache0.5.2-cu130 \
  env/docker/cu130
```

## Create the development container

```bash
sudo docker run -d \
  --name cacheroute-dev-cu130 \
  --gpus all \
  --network host \
  --ipc=host \
  --shm-size=64g \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -e CACHEROUTE_RUNTIME_PROFILE=v1 \
  -e HF_HOME=/workspace/llm-stack/cache/hf \
  -e TORCH_HOME=/workspace/llm-stack/cache/torch \
  -e LMCACHE_HOME=/workspace/llm-stack/cache/lmcache \
  -e PYTHONPATH=/workspace/llm-stack/CacheRoute \
  -e PYTHONHASHSEED=0 \
  -v /llm-stack:/workspace/llm-stack \
  -w /workspace/llm-stack/CacheRoute \
  cacheroute:dev-vllm0.25.1-lmcache0.5.2-cu130
```

Enter the container:

```bash
sudo docker exec -it cacheroute-dev-cu130 bash
```

Install the mounted CacheRoute source without re-resolving the serving stack:

```bash
cd /workspace/llm-stack/CacheRoute
python3 -m pip install -e . --no-deps
python3 -m pip check
```

## Runtime sanity check

```bash
python3 - <<'PY'
import os
import sys
import torch

print("python:", sys.executable)
print("torch:", torch.__version__)
print("torch CUDA runtime:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())
print("GPU count:", torch.cuda.device_count())
print("CacheRoute profile:", os.getenv("CACHEROUTE_RUNTIME_PROFILE"))
PY
```

The active interpreter should be `/opt/venv/bin/python3`, CUDA should be
available when the container is started with `--gpus all`, and the CacheRoute
profile should be `v1`.

## LMCache MP runtime note

This profile targets LMCache MP mode and vLLM `LMCacheMPConnector`. Do not use
the legacy `LMCACHE_CONFIG_FILE`, `remote_url`, or
`--kv-offloading-backend lmcache` startup path as the primary interface.

When using LMCache MP, either unset PyTorch expandable segments:

```bash
unset PYTORCH_CUDA_ALLOC_CONF
```

or explicitly enable vLLM's CuMem allocator. The conservative validation path
uses `unset PYTORCH_CUDA_ALLOC_CONF`.

A minimal LMCache server uses a dedicated MP endpoint and optional RESP L2
adapter, while vLLM connects through `--kv-transfer-config` with
`LMCacheMPConnector`.

## KDN migration status

The v1 branch contains the first runtime compatibility slice for KDN KV
construction:

- modern model-scoped LMCache Redis keys are discovered automatically;
- legacy `vllm@*` keys remain supported;
- asynchronous remote writes use a first-key timeout and quiet-period finish;
- zero-key builds fail and are never marked `kv_ready`;
- raw key/value dump and restore were verified byte-for-byte in the migration
  environment.

This does not yet prove an end-to-end LMCache MP cache hit after injection.
Validation must compare LMCache hit-token and remote-read metrics before the PR
is considered complete.

## Validation status and scope

The image build from the environment work was validated with:

- Python `3.12.13`;
- PyTorch `2.11.0+cu130`;
- vLLM `0.25.1`;
- LMCache `0.5.2`;
- Transformers `5.12.1`;
- Redis Python client `8.0.1`;
- successful `pip check`;
- successful imports of Torch, TorchCodec, vLLM, LMCache, and Redis;
- successful startup of the existing CacheRoute Scheduler, KDN, Proxy, and
  Instance workflow after installing FFmpeg.

The modern environment profile and the runtime compatibility work are additive.
The legacy image, root `requirements.txt`, Scheduler routing, and stable legacy
runtime remain unchanged.
