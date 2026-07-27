<img width="1400" height="369" alt="CacheRoute" src="https://github.com/user-attachments/assets/6050e71f-0e37-4cf9-b712-26e11242c9cd" />

<p align="center">
  <b>Flexible KV cache reuse for knowledge-intensive LLM serving</b>
</p>

<p align="center">
  <i>Built on vLLM and LMCache. Designed for compute-network-aware knowledge injection across LLM systems.</i>
</p>

<p align="center">
  <a href="https://github.com/AstraNetLab/CacheRoute/releases">
    <img src="https://img.shields.io/badge/version-0.1.9-blue" alt="Version">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="License">
  </a>
  <a href="https://github.com/vllm-project/vllm">
    <img src="https://img.shields.io/badge/Built%20on-vLLM-6C5CE7?style=flat-square&logo=github&logoColor=white" alt="Built on vLLM">
  </a>
  <a href="https://github.com/LMCache/LMCache">
    <img src="https://img.shields.io/badge/Powered%20by-LMCache-00B894?style=flat-square&logo=github&logoColor=white" alt="Powered by LMCache">
  </a>
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Redis-KV%20Store-DC382D?logo=redis&logoColor=white" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" />
</p>

<p align="center">
  <a href="#why-cacheroute">Why CacheRoute?</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#choose-a-runtime-profile">Runtime Profiles</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#frontend-urls">Frontend URLs</a> •
  <a href="#api-usage">API</a> •
  <a href="#documentation">Docs</a>
</p>

## CacheRoute

CacheRoute is a lightweight LLM scheduling framework built on [vLLM](https://github.com/vllm-project/vllm) and [LMCache](https://github.com/LMCache/LMCache). It enables reusable knowledge KV cache blocks to move across LLM systems and dynamically chooses between text recomputation and KVCache injection according to task queues, compute load, and network load.

The system separates global routing, local injection decisions, model execution, and reusable-KV management into Scheduler, Proxy, Instance, and KDN Server components.

## Why CacheRoute?

- 🚀 **Less redundant prefill computation:** reuse repeated knowledge instead of recomputing long prompts.
- 🔁 **Cross-system KV cache reuse:** distribute reusable knowledge through KDN servers.
- 🌐 **Compute-network coordination:** choose between recomputation and KV transfer according to current system load.
- 🧭 **Knowledge-oriented routing:** route requests according to knowledge coverage and resource-pool state.

<p align="center">
  <img width="1400" alt="CacheRoute performance overview" src=".assets/cacheroute_readme_showcase.png" />
</p>

## Architecture

<p align="center">
  <img width="600" alt="CacheRoute architecture" src="https://github.com/user-attachments/assets/9150a874-4e04-4499-821b-39a850e56db6" />
</p>

- **Scheduler:** performs global resource-pool selection and knowledge-oriented routing.
- **Proxy:** manages the local Instance pool and selects text or KVCache knowledge injection.
- **Instance:** connects CacheRoute to vLLM + LMCache and reports execution/resource state.
- **KDN Server:** registers knowledge, persists reusable KV blocks, and injects them into target Redis/LMCache backends.
- **Client/UI:** sends OpenAI-compatible requests and exposes optional browser interfaces.

### Default ports

| Component | Service plane | Control / auxiliary | UI |
|---|---:|---:|---:|
| Scheduler | 7001 | 7002 | TBD |
| Proxy | 8001 | 8002 | 8202 |
| Instance | 9001 | 9002 | 9202 |
| KDN Server | 9101 | - | TBD |
| vLLM | 8000 | - | - |
| LMCache MP (v1) | 5555 | 8080 | - |
| Redis RESP L2 | 6379 | - | - |
| Client | - | - | 7071 |

## Choose a Runtime Profile

CacheRoute supports two serving generations through a compatibility layer. Select the profile before following any deployment commands.

| Runtime path | Status | Serving stack | LMCache/vLLM interface | Entry point |
|---|---|---|---|---|
| **Modern v1** | Current migration/development path | CUDA 13.0, PyTorch 2.11, vLLM 0.25.1, LMCache 0.5.2 | standalone `lmcache server` + RESP L2 + `LMCacheMPConnector` | [Complete v1 quick start](docs/quickstart_v1.md) |
| **Legacy stable** | Preserved compatibility path | CUDA 12.8, PyTorch 2.9.x, vLLM 0.13.x, LMCache 0.3.11 | `LMCACHE_CONFIG_FILE` YAML + historical vLLM offloading flags | [Legacy environment guide](env/README.md) |
| **Compatibility design** | Architecture reference | `legacy`, `v1`, and `auto` profiles | version-dependent behavior isolated behind adapters | [Runtime compatibility](docs/runtime_compatibility_v1.md) |

> [!WARNING]
> Do not mix the two serving interfaces. The v1 path does not use legacy `remote_url`, `LMCACHE_CONFIG_FILE`, `--kv-offloading-backend lmcache`, or the old `python3 -m vllm.entrypoints.openai.api_server` startup example.

Select a profile explicitly:

```bash
# Modern vLLM 0.25.1 + LMCache 0.5.2
export CACHEROUTE_RUNTIME_PROFILE=v1

# Historical vLLM 0.13.x + LMCache 0.3.11 behavior
export CACHEROUTE_RUNTIME_PROFILE=legacy

# Recognize either supported Redis-key layout
export CACHEROUTE_RUNTIME_PROFILE=auto
```

## Requirements

The serving stack is owned by its Docker image. Do not let the root application requirements upgrade PyTorch, vLLM, LMCache, or other CUDA-sensitive packages.

| Component | Legacy stable | Modern v1 |
|---|---|---|
| Base CUDA | 12.8 | 13.0.0 |
| Python | 3.12.x | 3.12.x in `/opt/venv` |
| PyTorch | 2.9.x | 2.11.0+cu130 |
| vLLM | 0.13.x | 0.25.1 |
| LMCache | 0.3.11 | 0.5.2 |
| Redis | 7 | RESP L2 backend on Redis 7 |
| Environment files | `env/docker/Dockerfile`, root `requirements.txt` | `env/docker/cu130/` |

For a new modern container, use [`env/docker/cu130/README.md`](env/docker/cu130/README.md). For an already-built compatible container, update the repository and use the checked-in startup scripts; rebuilding the image is not required.

## Quick Start

### Option 1: Lightweight scheduling demo without a model

Set `USE_MOCK = True` in `core/config.py`, then start the components in separate terminals:

```bash
cd test
python3 demo_scheduler.py --cacheroute
python3 demo_kdn.py
python3 demo_proxy.py \
  --strategy round_robin \
  --injection-strategy iws \
  --ready-release-policy text_bypass
python3 demo_instance.py --port 9001 --host 127.0.0.1
python3 demo_client.py --with-ui
```

### Option 2: Modern v1 full single-machine path

The complete command-by-command guide is [`docs/quickstart_v1.md`](docs/quickstart_v1.md). The following is the full service order and minimum command path.

#### 1. Prepare the current container

```bash
cd /workspace/llm-stack/CacheRoute
git switch main
git pull --ff-only origin main

export CACHEROUTE_RUNTIME_PROFILE=v1
export PYTHONPATH=/workspace/llm-stack/CacheRoute
```

Verify:

```bash
python3 - <<'PY'
from core.runtime_compat import normalize_runtime_profile
print(normalize_runtime_profile())
PY
# Expected: v1
```

Each new terminal must export `CACHEROUTE_RUNTIME_PROFILE=v1` before starting a CacheRoute component.

#### 2. Start or verify Redis RESP L2

```bash
redis-cli -h 127.0.0.1 -p 6379 ping
# Expected: PONG
```

Create the Redis container when needed:

```bash
sudo docker run -d \
  --name lmcache-redis \
  --network host \
  redis:7 \
  redis-server \
    --bind 0.0.0.0 \
    --protected-mode no \
    --save "" \
    --appendonly no \
    --maxmemory 200gb \
    --maxmemory-policy allkeys-lru
```

#### 3. Terminal 1: start LMCache MP

```bash
cd /workspace/llm-stack/CacheRoute
export CACHEROUTE_RUNTIME_PROFILE=v1
bash env/docker/cu130/scripts/start_lmcache_mp.sh
```

The defaults are LMCache MP `127.0.0.1:5555`, HTTP `127.0.0.1:8080`, chunk size `256`, hash algorithm `sha256_cbor`, and Redis RESP L2 `127.0.0.1:6379`.

Check the ports:

```bash
ss -lntp | grep -E ':(5555|8080)\b'
```

#### 4. Terminal 2: start vLLM with LMCacheMPConnector

```bash
cd /workspace/llm-stack/CacheRoute
export CACHEROUTE_RUNTIME_PROFILE=v1
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export MODEL_DIR=/workspace/llm-stack/models/LLM-Research/Meta-Llama-3-70B-Instruct
bash env/docker/cu130/scripts/start_vllm_mp.sh
```

Wait until vLLM is ready:

```bash
curl -sS http://127.0.0.1:8000/v1/models | python3 -m json.tool
curl -sS http://127.0.0.1:8000/metrics | grep -i lmcache | head -n 50
```

#### 5. Terminals 3-4: start Scheduler and KDN

Scheduler:

```bash
cd /workspace/llm-stack/CacheRoute/test
export CACHEROUTE_RUNTIME_PROFILE=v1
python3 demo_scheduler.py \
  --cacheroute \
  --kdn-pending-overload-th 8 \
  --kdn-active-overload-th 4 \
  --kdn-queue-ms-overload-th 30 \
  --cacheroute-log-decision 1
```

KDN Server:

```bash
cd /workspace/llm-stack/CacheRoute/test
export CACHEROUTE_RUNTIME_PROFILE=v1
python3 demo_kdn.py
```

#### 6. Register knowledge and build its KVCache

```bash
cd /workspace/llm-stack/CacheRoute
mkdir -p data/quickstart
cat > data/quickstart/cacheroute_v1.txt <<'EOF'
CacheRoute is a knowledge-oriented LLM scheduling framework. It reduces repeated prefill computation by storing and reusing KVCache blocks for frequently requested external knowledge.
EOF

python3 kdn_server/kdn_register_cli.py
```

At the KDN CLI prompt:

```text
:buildkv_file /workspace/llm-stack/CacheRoute/data/quickstart/cacheroute_v1.txt --api-url http://127.0.0.1:8000/v1/chat/completions --model llama3-70b
:pool
```

Normal v1 registration does not require `--match`. A successful build must report `dumped_keys > 0`; inspect `kdn_server/KV_database/<kid>/run_meta.json` for `runtime_profile: v1` and `key_formats: [v1]`.

#### 7. Terminals 5-6: start Proxy and Instance

Proxy:

```bash
cd /workspace/llm-stack/CacheRoute/test
export CACHEROUTE_RUNTIME_PROFILE=v1
python3 demo_proxy.py \
  --strategy round_robin \
  --injection-strategy iws \
  --ready-release-policy text_bypass
```

Instance:

```bash
cd /workspace/llm-stack/CacheRoute/test
export CACHEROUTE_RUNTIME_PROFILE=v1
python3 demo_instance.py \
  --host 127.0.0.1 \
  --port 9001 \
  --proxy-cp-url http://127.0.0.1:8002
```

Confirm registration:

```bash
curl -sS http://127.0.0.1:7001/debug/status | python3 -m json.tool
curl -sS 'http://127.0.0.1:8002/v1/instance/list?include_dead=true' | python3 -m json.tool
```

#### 8. Terminal 7: start the Client and send a request

```bash
cd /workspace/llm-stack/CacheRoute/test
export CACHEROUTE_RUNTIME_PROFILE=v1
python3 demo_client.py --with-ui
```

Or send a request directly through the Scheduler:

```bash
curl http://127.0.0.1:7001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "llama3-70b",
    "messages": [{
      "role": "user",
      "content": "What does CacheRoute reuse to reduce repeated prefill computation?"
    }],
    "temperature": 0,
    "max_tokens": 64,
    "stream": false,
    "RAG": true
  }'
```

Expected service path:

```text
Client -> Scheduler :7001 -> Proxy :8001 -> Instance :9001
       -> vLLM :8000 -> LMCache MP :5555 -> Redis RESP L2 :6379
```

Validate actual cache consumption through LMCache hit-token and remote-read metrics, not only TTFT:

```bash
curl -sS http://127.0.0.1:8000/metrics \
  | grep -E 'lmcache.*(hit|requested|remote_read|retrieve)'
```

### Option 3: Legacy stable deployment

The legacy path remains available for vLLM 0.13.x + LMCache 0.3.11:

```bash
export CACHEROUTE_RUNTIME_PROFILE=legacy
```

Use [`env/README.md`](env/README.md) for the legacy Docker image, YAML LMCache configuration, historical vLLM startup flags, source-build notes, and complete environment repair steps.

## Frontend URLs

| Component | URL | Start command |
|---|---|---|
| Proxy UI | `http://127.0.0.1:8202` | started by `demo_proxy.py` unless `--no-proxy-ui` is used |
| Instance browser dashboard | `http://127.0.0.1:9202` | `python3 instance/resource_dashboard/dashboard_server.py --dashboard-listen 0.0.0.0:9202 --agent-listen 127.0.0.1:9201` |
| Client UI | `http://127.0.0.1:7071/ui/client` | `python3 demo_client.py --with-ui` |

The URLs assume a single-machine host-network deployment. Publish or remap ports for bridged containers and multi-machine deployments.

## API Usage

CacheRoute exposes OpenAI-compatible endpoints through the Scheduler.

| Endpoint | Mode |
|---|---|
| `/v1/chat/completions` | Chat completion |
| `/v1/completions` | Text completion |

Example:

```bash
curl http://127.0.0.1:7001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "llama3-70b",
    "messages": [{"role": "user", "content": "What is CacheRoute?"}],
    "max_tokens": 64,
    "stream": false,
    "RAG": true
  }'
```

Important request fields:

| Field | Required | Description |
|---|---|---|
| `model` | Yes | Served vLLM model name. |
| `messages` / `prompt` | Yes | Chat or completion input. |
| `max_tokens` | No | Generation token limit. |
| `stream` | No | Enable streaming responses. |
| `RAG` | No | Enable CacheRoute knowledge injection. |

## Current Status

Implemented capabilities include:

- Scheduler-side knowledge-oriented routing;
- Proxy-side dynamic text/KVCache injection decisions;
- KDN text and KVCache registration, persistence, and Redis injection;
- runtime profiles for legacy and v1 LMCache Redis-key layouts;
- v1 asynchronous KDN key capture with zero-key failure handling;
- OpenAI-compatible request forwarding;
- Proxy UI and optional Instance resource dashboard;
- debugging APIs such as `/debug/status` and `/debug/strategy`.

The v1 raw Redis dump/restore path has been validated byte-for-byte. End-to-end injected-cache consumption should still be confirmed with LMCache hit-token and remote-read metrics.

## Documentation

| Document | Description |
|---|---|
| [`docs/quickstart_v1.md`](docs/quickstart_v1.md) | Complete modern v1 path from Redis and LMCache MP through KDN registration and end-to-end cache-hit validation. |
| [`env/docker/cu130/README.md`](env/docker/cu130/README.md) | CUDA 13 / vLLM 0.25.1 / LMCache 0.5.2 image, container, startup scripts, and parameter overrides. |
| [`docs/runtime_compatibility_v1.md`](docs/runtime_compatibility_v1.md) | `legacy`, `v1`, and `auto` compatibility design. |
| [`env/README.md`](env/README.md) | Legacy environment, source build, Docker, Rust, Tkinter, X11, and repair guidance. |
| [`core/README.md`](core/README.md) | Shared configuration, request model, and multi-machine settings. |
| [`scheduler/README.md`](scheduler/README.md) | Scheduler routing and control plane. |
| [`proxy/README.md`](proxy/README.md) | Instance pool, prepare/ready queues, injection strategy, and Proxy APIs. |
| [`instance/README.md`](instance/README.md) | Instance service, capability identity, execution signaling, and resource monitoring. |
| [`kdn_server/README.md`](kdn_server/README.md) | Knowledge registration, KV construction, persistence, and injection. |
| [`client/README.md`](client/README.md) | Client CLI, request examples, and workload tools. |
| [`test/README.md`](test/README.md) | Demo scripts and smoke tests. |

## License

CacheRoute is licensed under the [Apache License 2.0](LICENSE).
