# CUDA 13 / vLLM 0.25.1 / LMCache 0.5.2 profile

This directory provides the additive v1 development-image profile for the
modern CacheRoute runtime. It does not replace or modify the existing CUDA 12.8
/ vLLM 0.13.x / LMCache 0.3.11 environment.

Start with the repository-level guides:

- complete runtime path: [`doc/quickstart_v1.md`](../../../doc/quickstart_v1.md);
- compatibility design: [`doc/runtime_compatibility_v1.md`](../../../doc/runtime_compatibility_v1.md);
- completed migration evidence: [`doc/v1_migration_closeout.md`](../../../doc/v1_migration_closeout.md).

## Choose this profile only for the modern stack

| Profile | Serving stack | LMCache startup interface |
|---|---|---|
| Legacy | vLLM 0.13.x + LMCache 0.3.11 | YAML through `LMCACHE_CONFIG_FILE` and historical vLLM offloading flags |
| v1 | vLLM 0.25.1 + LMCache 0.5.2 | standalone `lmcache server` plus vLLM `LMCacheMPConnector` |

Do not combine the two interfaces. In v1 mode, unset `LMCACHE_CONFIG_FILE` and
do not use `remote_url`, `--kv-offloading-backend lmcache`, or the historical
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
Python packages. FFmpeg is installed for TorchCodec. Rust/Cargo and Tkinter
remain available for the resource-agent and dashboard workflows.

The image sets `CACHEROUTE_RUNTIME_PROFILE=v1` by default.

## Files

- `Dockerfile`: complete CUDA 13 development image;
- `constraints.txt`: exact serving-stack versions and shared compatibility
  ranges;
- `requirements-dev.txt`: CacheRoute dependencies compatible with the target
  serving stack;
- `scripts/activate_v1.sh`: shared shell activation for every service terminal;
- `scripts/check_v1_environment.py`: non-destructive version, CUDA, model,
  Redis, and endpoint validation;
- `scripts/start_lmcache_mp.sh`: LMCache 0.5.2 MP + RESP L2 startup;
- `scripts/start_vllm_mp.sh`: vLLM 0.25.1 + `LMCacheMPConnector` startup.

`requirements-dev.txt` intentionally excludes `Booktype==1.5`. That Python-2-era
package can overwrite the modern `redis` module with invalid source files.

## Existing compatible container: no rebuild required

The runtime scripts live in the mounted repository, so an already-created
container can use the merged `main` branch directly:

```bash
cd /workspace/llm-stack/CacheRoute
git switch main
git pull --ff-only origin main

source env/docker/cu130/scripts/activate_v1.sh
```

Do not switch back to the historical `v1/runtime-compat` development branch;
that work has already been merged into `main`.

The activation script:

- sets `CACHEROUTE_RUNTIME_PROFILE=v1`;
- adds the repository root to `PYTHONPATH` without duplicating it;
- sets stable `PYTHONHASHSEED` and `OMP_NUM_THREADS` defaults;
- clears legacy `LMCACHE_CONFIG_FILE`;
- clears `PYTORCH_CUDA_ALLOC_CONF` for the validated MP path.

It must be sourced in every new terminal:

```bash
source env/docker/cu130/scripts/activate_v1.sh
```

Long-running services only see variables present when they start. Restart
LMCache, vLLM, KDN, Proxy, and Instance after changing profiles.

## Non-destructive environment validation

Before starting services:

```bash
python3 env/docker/cu130/scripts/check_v1_environment.py
```

This checks:

- repository location and v1 profile;
- Python, PyTorch, vLLM, and LMCache versions;
- PyTorch CUDA runtime, CUDA availability, and GPU count;
- model directory;
- required repository scripts;
- Redis connectivity when available;
- vLLM and LMCache endpoints as warnings when they are not running.

After Redis, LMCache, and vLLM are started, require all endpoints:

```bash
python3 env/docker/cu130/scripts/check_v1_environment.py --require-running
```

Useful overrides include:

```bash
python3 env/docker/cu130/scripts/check_v1_environment.py \
  --model-dir /other/model \
  --expected-gpus 4 \
  --redis-host 172.18.0.121
```

Use `--allow-no-gpu` only for image/CI inspection where GPU access is not
expected.

## Runtime startup order

Use separate terminals in this order:

1. Redis RESP L2 backend;
2. LMCache MP server;
3. vLLM with `LMCacheMPConnector`;
4. CacheRoute Scheduler, KDN, Proxy, Instance, and Client.

### 1. Verify Redis

`redis-cli` is optional. The Python client is sufficient:

```bash
python3 - <<'PY'
import redis
r = redis.Redis(host="127.0.0.1", port=6379, db=0)
print("PING:", r.ping())
print("DBSIZE:", r.dbsize())
PY
```

### 2. Start LMCache MP

```bash
cd /workspace/llm-stack/CacheRoute
source env/docker/cu130/scripts/activate_v1.sh
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

Confirm the MP and HTTP ports:

```bash
ss -lntp | grep -E ':(5555|8080)\b'
```

### 3. Start vLLM

Start vLLM only after LMCache is listening on port `5555`:

```bash
cd /workspace/llm-stack/CacheRoute
source env/docker/cu130/scripts/activate_v1.sh
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export MODEL_DIR=/workspace/llm-stack/models/LLM-Research/Meta-Llama-3-70B-Instruct
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

### Parameter overrides

The repository scripts expose their main settings as environment variables:

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

Additional command-line arguments are appended unchanged to the underlying
commands.

## Metrics endpoints

The endpoints and namespaces are different:

| Endpoint | Metrics |
|---|---|
| `http://127.0.0.1:8000/metrics` | vLLM, including `vllm:external_prefix_cache_queries_total`, `vllm:external_prefix_cache_hits_total`, and `vllm:prompt_tokens_cached_total` |
| `http://127.0.0.1:8080/metrics` | LMCache MP, including `lmcache_mp_lookup_*`, `lmcache_mp_l1_*`, and `lmcache_mp_l2_*` |

LMCache lookup metrics may not exist before the first request. A direct KDN
Redis restore bypasses LMCache store accounting, so `lmcache_mp_l2_usage_bytes`
is not a reliable test for injected data. Use lookup/hit/load metrics.

## Cache identity requirements

KDN construction and the consuming Instance must agree on:

- model identity/path and served model;
- tokenizer, chat template, and exact token prefix;
- tensor-parallel topology and worker layout;
- KV dtype and model configuration;
- LMCache chunk size (`256` here);
- LMCache hash algorithm (`sha256_cbor` here);
- connector/key generation;
- Redis database semantics.

A successful Redis `SET` or byte-for-byte KDN round trip does not alone prove a
cache hit. The final acceptance test is LMCache/vLLM consumption metrics.

## Build the image for a new container

Use this directory as the Docker build context. It avoids sending models, KDN
databases, logs, or other repository data to the Docker daemon.

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
source env/docker/cu130/scripts/activate_v1.sh
python3 env/docker/cu130/scripts/check_v1_environment.py
```

## Completed KDN migration validation

The modern runtime was validated end to end with the dataset document whose KID
is `668f6bd1ad2419d9dfbcda0b689311b8b6696c7ed772001bea7bd12573137b4a`:

```text
KDN keys persisted locally:          96
Redis keys restored:                 96
Payload bytes restored:              1,006,632,960
Missing/extra/mismatched entries:    0
LMCache L2 lookup hits:              96/96 chunks
LMCache lookup tokens:               3072/3072
LMCache token hit rate:              100%
vLLM external cached tokens:         3072
LMCache L2 prefetch failures:        0
```

Reproduce the staged validation with:

```bash
DOC=/workspace/llm-stack/CacheRoute/data/CacheRoute_dataset/knowledge_document/668f6bd1ad2419d9dfbcda0b689311b8b6696c7ed772001bea7bd12573137b4a.txt

python3 scripts/validate_v1_kdn_roundtrip.py build --document "$DOC"
python3 scripts/validate_v1_kdn_roundtrip.py inspect --document "$DOC"
```

For a destructive restore against an isolated Redis DB:

```bash
python3 scripts/validate_v1_kdn_roundtrip.py inject \
  --document "$DOC" \
  --flush-redis \
  --yes
```

Restart LMCache and vLLM after restore, then prove consumption:

```bash
python3 scripts/validate_v1_kdn_roundtrip.py consume --document "$DOC"
```

The injector implementation is `kdn_server/kv_injector.py`. Normal v1
registration does not require `--match` and should not use `--flushdb`.

## Compatibility and scope

The modern environment profile is additive. The legacy Dockerfile, root
`requirements.txt`, Scheduler routing, and stable legacy runtime remain
unchanged. Subsequent Scheduler, Proxy, Instance, predictor, and UI development
can use this v1 stack as the modern baseline.
