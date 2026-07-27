# CacheRoute v1 end-to-end quick start

This guide covers the complete single-machine path for the modern CacheRoute runtime:

```text
Redis RESP L2
  -> LMCache 0.5.2 MP server :5555
  -> vLLM 0.25.1 + LMCacheMPConnector :8000
  -> Scheduler :7001/:7002
  -> KDN Server :9101
  -> Proxy :8001/:8002
  -> Instance :9001
  -> Client/UI :7071
```

Use this guide for the CUDA 13 / PyTorch 2.11 / vLLM 0.25.1 / LMCache 0.5.2 profile. Do not mix it with the legacy YAML-based LMCache startup path.

## 0. Assumptions

The commands assume:

- the repository is mounted at `/workspace/llm-stack/CacheRoute`;
- the model is located at `/workspace/llm-stack/models/LLM-Research/Meta-Llama-3-70B-Instruct`;
- the served model name is `llama3-70b`;
- Redis, LMCache, vLLM, and CacheRoute use host networking and loopback addresses;
- each long-running process is started in a separate terminal;
- `core/config.py` has `USE_MOCK = False` and model paths matching this deployment.

For a new image/container, first follow [`env/docker/cu130/README.md`](../env/docker/cu130/README.md). An already-built compatible container does not need to rebuild the Docker image.

## 1. Select the v1 runtime profile

```bash
cd /workspace/llm-stack/CacheRoute
git switch main
git pull --ff-only origin main

export CACHEROUTE_RUNTIME_PROFILE=v1
export PYTHONPATH=/workspace/llm-stack/CacheRoute
```

Verify the compatibility layer:

```bash
python3 - <<'PY'
from core.runtime_compat import normalize_runtime_profile
print(normalize_runtime_profile())
PY
# Expected: v1
```

Every new terminal that starts a CacheRoute component should export `CACHEROUTE_RUNTIME_PROFILE=v1`. Environment variables are inherited only by processes started after the export.

## 2. Start or verify Redis

When Redis is already running:

```bash
redis-cli -h 127.0.0.1 -p 6379 ping
# Expected: PONG
```

To create a local Redis container for the first time:

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

For later runs:

```bash
sudo docker start lmcache-redis
```

Do not run KDN `--flushdb` against an online shared Redis database unless its contents are disposable.

## 3. Terminal 1: start LMCache MP

```bash
cd /workspace/llm-stack/CacheRoute
export CACHEROUTE_RUNTIME_PROFILE=v1
bash env/docker/cu130/scripts/start_lmcache_mp.sh
```

Default endpoints:

```text
LMCache MP:    tcp://127.0.0.1:5555
LMCache HTTP:  http://127.0.0.1:8080
Redis RESP L2: 127.0.0.1:6379
```

Confirm the listening ports:

```bash
ss -lntp | grep -E ':(5555|8080)\b'
```

The v1 path deliberately unsets `LMCACHE_CONFIG_FILE`. It does not use the legacy `remote_url` YAML interface.

## 4. Terminal 2: start vLLM with LMCacheMPConnector

Start vLLM only after LMCache MP is listening on port `5555`:

```bash
cd /workspace/llm-stack/CacheRoute
export CACHEROUTE_RUNTIME_PROFILE=v1
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export MODEL_DIR=/workspace/llm-stack/models/LLM-Research/Meta-Llama-3-70B-Instruct

bash env/docker/cu130/scripts/start_vllm_mp.sh
```

Wait for the model endpoint:

```bash
curl -sS http://127.0.0.1:8000/v1/models | python3 -m json.tool
```

Check that LMCache metrics are exposed:

```bash
curl -sS http://127.0.0.1:8000/metrics | grep -i lmcache | head -n 50
```

## 5. Terminal 3: start the Scheduler

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

The Scheduler service plane listens on `127.0.0.1:7001` and its control plane listens on `127.0.0.1:7002`.

## 6. Terminal 4: start the KDN Server

```bash
cd /workspace/llm-stack/CacheRoute/test
export CACHEROUTE_RUNTIME_PROFILE=v1
python3 demo_kdn.py
```

The KDN Server listens on `127.0.0.1:9101`. Normal v1 knowledge builds do not require a manual `--match`.

## 7. Terminal 5: register knowledge and build KVCache

Create a sample knowledge file:

```bash
cd /workspace/llm-stack/CacheRoute
mkdir -p data/quickstart

cat > data/quickstart/cacheroute_v1.txt <<'EOF'
CacheRoute is a knowledge-oriented LLM scheduling framework. It reduces repeated prefill computation by storing and reusing KVCache blocks for frequently requested external knowledge. The Scheduler selects a KDN server and a Proxy, while the Proxy chooses between text recomputation and KVCache reuse.
EOF
```

Start the KDN CLI:

```bash
python3 kdn_server/kdn_register_cli.py
```

At the CLI prompt:

```text
:buildkv_file /workspace/llm-stack/CacheRoute/data/quickstart/cacheroute_v1.txt --api-url http://127.0.0.1:8000/v1/chat/completions --model llama3-70b
:pool
```

A successful build must report `dumped_keys > 0`. Inspect the generated metadata:

```bash
cat kdn_server/KV_database/<kid>/run_meta.json
```

Expected fields include `"runtime_profile": "v1"`, `"key_formats": ["v1"]`, and a non-zero `dumped_keys` value.

## 8. Terminal 6: start the Proxy

```bash
cd /workspace/llm-stack/CacheRoute/test
export CACHEROUTE_RUNTIME_PROFILE=v1

python3 demo_proxy.py \
  --strategy round_robin \
  --injection-strategy iws \
  --ready-release-policy text_bypass
```

The Proxy listens on `127.0.0.1:8001`, its control plane on `127.0.0.1:8002`, and its UI is normally available at `http://127.0.0.1:8202`.

## 9. Terminal 7: start the Instance

```bash
cd /workspace/llm-stack/CacheRoute/test
export CACHEROUTE_RUNTIME_PROFILE=v1

python3 demo_instance.py \
  --host 127.0.0.1 \
  --port 9001 \
  --proxy-cp-url http://127.0.0.1:8002
```

For a minimal functional test without the resource agent, add `--no-resource-monitor`.

Confirm control-plane registration:

```bash
curl -sS http://127.0.0.1:7001/debug/status | python3 -m json.tool
curl -sS 'http://127.0.0.1:8002/v1/instance/list?include_dead=true' | python3 -m json.tool
```

## 10. Terminal 8: start the Client

```bash
cd /workspace/llm-stack/CacheRoute/test
export CACHEROUTE_RUNTIME_PROFILE=v1
python3 demo_client.py --with-ui
```

Open `http://127.0.0.1:7071/ui/client`. For terminal-only operation, run `python3 demo_client.py`.

## 11. Send an end-to-end request

Send the request through the Scheduler rather than directly to vLLM:

```bash
curl http://127.0.0.1:7001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "llama3-70b",
    "messages": [
      {
        "role": "user",
        "content": "What does CacheRoute reuse to reduce repeated prefill computation?"
      }
    ],
    "temperature": 0,
    "max_tokens": 64,
    "stream": false,
    "RAG": true
  }'
```

Inspect routing decisions:

```bash
curl -sS http://127.0.0.1:7001/debug/strategy | python3 -m json.tool
```

Expected path:

```text
Client -> Scheduler :7001 -> Proxy :8001 -> Instance :9001
       -> vLLM :8000 -> LMCache MP :5555 -> Redis RESP L2 :6379
```

## 12. Validate actual cache consumption

A successful KDN Redis injection proves transport integrity, not an LMCache hit. Capture LMCache hit-token and remote-read metrics before and after a request:

```bash
curl -sS http://127.0.0.1:8000/metrics \
  | grep -E 'lmcache.*(hit|requested|remote_read|retrieve)'
```

Do not rely only on TTFT differences.

## Troubleshooting boundaries

- No keys produced during KDN build: verify the v1 profile, Redis endpoint, model request success, and LMCache MP logs.
- Redis keys exist but the request misses: compare model path/identity, tensor-parallel layout, KV dtype, chunk size, hash algorithm, and exact token prefix.
- `vllm serve` cannot connect: start LMCache MP first and verify port `5555`.
- Old YAML settings are still active: unset `LMCACHE_CONFIG_FILE` and restart LMCache/vLLM.
- Profile changes do not appear: restart all affected processes after exporting `CACHEROUTE_RUNTIME_PROFILE=v1`.
