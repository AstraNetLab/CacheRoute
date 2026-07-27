# CUDA 13 / vLLM 0.25.1 / LMCache 0.5.2 profile

This directory provides the additive v1 development-image profile for the
modern CacheRoute runtime. It does not replace or modify the existing CUDA 12.8
/ vLLM 0.13.x / LMCache 0.3.11 environment.

The runtime compatibility architecture is described in
[`docs/runtime_compatibility_v1.md`](../../../docs/runtime_compatibility_v1.md).

## Choose this profile only for the modern stack

| Profile | Serving stack | LMCache startup interface |
|---|---|---|
| Legacy | vLLM 0.13.x + LMCache 0.3.11 | YAML through `LMCACHE_CONFIG_FILE` and the historical vLLM offloading flags |
| v1 | vLLM 0.25.1 + LMCache 0.5.2 | Standalone `lmcache server` plus vLLM `LMCacheMPConnector` |

Do not combine the two interfaces. In v1 mode, unset `LMCACHE_CONFIG_FILE` and
do not use `remote_url`, `--kv-offloading-backend lmcache`, or the old
`python3 -m vllm.entrypoints.openai.api_server` example as the primary startup
path.

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
- `scripts/start_lmcache_mp.sh`: reusable LMCache 0.5.2 MP + RESP L2 startup.
- `scripts/start_vllm_mp.sh`: reusable vLLM 0.25.1 + `LMCacheMPConnector`
  startup.

`requirements-dev.txt` intentionally excludes `Booktype==1.5`. That package is
from the Python 2 era and can overwrite the modern `redis` module with invalid
Python 2 source files.

## Use an existing container without rebuilding

The scripts live in the mounted CacheRoute repository, so an already-created
container does not need to run through the Dockerfile again.

Update the branch and select the v1 profile:

```bash
cd /workspace/llm-stack/CacheRoute
git fetch origin
git switch v1/runtime-compat
git pull --ff-only origin v1/runtime-compat

export CACHEROUTE_RUNTIME_PROFILE=v1
```

Persist the profile for interactive root shells when useful:

```bash
grep -q 'CACHEROUTE_RUNTIME_PROFILE' /root/.bashrc || \
  echo 'export CACHEROUTE_RUNTIME_PROFILE=v1' >> /root/.bashrc
```

Long-running services only see environment variables present when they start.
Restart LMCache, vLLM, KDN, Proxy, and Instance after switching profiles.

## Runtime startup order

Use separate terminals in this order:

1. Redis RESP L2 backend;
2. LMCache MP server;
3. vLLM with `LMCacheMPConnector`;
4. CacheRoute Scheduler, KDN, Proxy, Instance, and Client.

### 1. Verify Redis

```bash
redis-cli -h 127.0.0.1 -p 6379 ping
# Expected: PONG
```

### 2. Start LMCache MP

Recommended repository script:

```bash
cd /workspace/llm-stack/CacheRoute
export CACHEROUTE_RUNTIME_PROFILE=v1
bash env/docker/cu130/scripts/start_lmcache_mp.sh
```

Equivalent validated command:

```bash
unset LMCACHE_CONFIG_FILE
export CACHEROUTE_RUNTIME_PROFILE=v1
export LMCACHE_LOG_LEVEL=INFO
export PYTHONHASHSEED=0

lmcache server \
  --instance-id cacheroute-lmcache-1 \
  --host 127.0.0.1 \
  --port 5555 \
  --http-host 127.0.0.1 \
  --http-port 8080 \
  --l1-size-gb 80 \
  --chunk-size 256 \
  --hash-algorithm sha256_cbor \
  --eviction-policy LRU \
  --max-workers 8 \
  --l2-store-policy default \
  --l2-adapter '{
    "type": "resp",
    "host": "127.0.0.1",
    "port": 6379,
    "num_workers": 8
  }'
```

Confirm that the MP and HTTP ports are listening:

```bash
ss -lntp | grep -E ':(5555|8080)\b'
```

### 3. Start vLLM

Start this only after LMCache is listening on port `5555`.

Recommended repository script:

```bash
cd /workspace/llm-stack/CacheRoute
export CACHEROUTE_RUNTIME_PROFILE=v1
bash env/docker/cu130/scripts/start_vllm_mp.sh
```

Equivalent validated command:

```bash
export CACHEROUTE_RUNTIME_PROFILE=v1
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export MODEL_DIR=/workspace/llm-stack/models/LLM-Research/Meta-Llama-3-70B-Instruct
export PYTHONHASHSEED=0
export OMP_NUM_THREADS=8

unset LMCACHE_CONFIG_FILE
unset PYTORCH_CUDA_ALLOC_CONF

vllm serve "$MODEL_DIR" \
  --served-model-name llama3-70b \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 8 \
  --gpu-memory-utilization 0.75 \
  --dtype auto \
  --max-model-len 4096 \
  --max-num-seqs 8 \
  --max-num-batched-tokens 16384 \
  --disable-hybrid-kv-cache-manager \
  --no-enable-prefix-caching \
  --kv-transfer-config '{
    "kv_connector": "LMCacheMPConnector",
    "kv_connector_module_path": "lmcache.integration.vllm.lmcache_mp_connector",
    "kv_role": "kv_both",
    "kv_connector_extra_config": {
      "lmcache.mp.host": "tcp://127.0.0.1",
      "lmcache.mp.port": 5555
    }
  }' \
  --kv-cache-metrics
```

Wait for the OpenAI-compatible endpoint:

```bash
curl -sS http://127.0.0.1:8000/v1/models | python3 -m json.tool
```

The scripts expose the main values as environment variables. For example:

```bash
MODEL_DIR=/other/model \
TENSOR_PARALLEL_SIZE=4 \
CUDA_VISIBLE_DEVICES=0,1,2,3 \
bash env/docker/cu130/scripts/start_vllm_mp.sh
```

```bash
LMCACHE_L1_SIZE_GB=40 \
REDIS_HOST=172.18.0.121 \
bash env/docker/cu130/scripts/start_lmcache_mp.sh
```

Additional command-line arguments are appended unchanged to each underlying
command.

## Cache identity requirements

KDN construction and the target Instance must agree on the cache identity. At a
minimum, keep the following aligned when building and consuming reusable KV:

- model identity/path and served model;
- tensor-parallel topology and worker layout;
- KV dtype and model configuration;
- LMCache chunk size (`256` in this profile);
- LMCache hash algorithm (`sha256_cbor` in this profile);
- Redis RESP L2 endpoint and database semantics.

A successful Redis `SET` or byte-for-byte KDN round trip does not by itself
prove a cache hit. Validate consumption with LMCache hit-token and remote-read
metrics.

## Build the image for a new container

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

## Create a new development container

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
