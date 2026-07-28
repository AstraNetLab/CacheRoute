# CacheRoute v1 end-to-end quick start

This guide covers the complete single-machine path for the modern CacheRoute
runtime:

```text
Redis RESP L2
  -> LMCache 0.5.2 MP server :5555 / HTTP :8080
  -> vLLM 0.25.1 + LMCacheMPConnector :8000
  -> Scheduler :7001/:7002
  -> KDN Server :9101
  -> Proxy :8001/:8002
  -> Instance :9001
  -> Client/UI :7071
```

Use this path for CUDA 13 / PyTorch 2.11 / vLLM 0.25.1 / LMCache
0.5.2. The existing root README deployment remains the legacy stable path.
Do not mix its YAML/offloading commands with the v1 MP startup interface.

For the completed migration evidence and compatibility boundary, see
[`v1_migration_closeout.md`](v1_migration_closeout.md).

## 0. Assumptions

The commands assume:

- the repository is mounted at `/workspace/llm-stack/CacheRoute`;
- the model is at
  `/workspace/llm-stack/models/LLM-Research/Meta-Llama-3-70B-Instruct`;
- the served model name is `llama3-70b`;
- Redis, LMCache, vLLM, and CacheRoute use host networking and loopback
  addresses;
- each long-running process is started in a separate terminal;
- `core/config.py` has `USE_MOCK = False` and matching model paths.

A newly created image/container should first follow
[`env/docker/cu130/README.md`](../env/docker/cu130/README.md). An existing
compatible container does not need to rebuild the Docker image.

## 1. Update the repository and activate v1

```bash
cd /workspace/llm-stack/CacheRoute
git switch main
git pull --ff-only origin main

source env/docker/cu130/scripts/activate_v1.sh
```

Source the activation script in every terminal that starts LMCache, vLLM, KDN,
Proxy, Instance, or validation tools. Environment variables are inherited only
by processes started after activation.

Run the non-destructive environment check before starting services:

```bash
python3 env/docker/cu130/scripts/check_v1_environment.py
```

When Redis, LMCache, and vLLM are expected to be running, use the strict form:

```bash
python3 env/docker/cu130/scripts/check_v1_environment.py --require-running
```

## 2. Start or verify Redis

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

`redis-cli` is optional. The Python client check works in the v1 container:

```bash
python3 - <<'PY'
import redis
r = redis.Redis(host="127.0.0.1", port=6379, db=0)
print("PING:", r.ping())
print("DBSIZE:", r.dbsize())
PY
```

Do not use KDN `--flushdb` during normal registration. Do not clear a shared or
production Redis database.

## 3. Terminal 1: start LMCache MP

```bash
cd /workspace/llm-stack/CacheRoute
source env/docker/cu130/scripts/activate_v1.sh
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

The v1 startup deliberately unsets `LMCACHE_CONFIG_FILE` and does not use the
legacy `remote_url` YAML interface.

## 4. Terminal 2: start vLLM with LMCacheMPConnector

Start vLLM only after LMCache MP is listening on port `5555`:

```bash
cd /workspace/llm-stack/CacheRoute
source env/docker/cu130/scripts/activate_v1.sh
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export MODEL_DIR=/workspace/llm-stack/models/LLM-Research/Meta-Llama-3-70B-Instruct

bash env/docker/cu130/scripts/start_vllm_mp.sh
```

Wait for the model endpoint:

```bash
curl -sS http://127.0.0.1:8000/v1/models | python3 -m json.tool
```

The metrics endpoints are separate:

```text
vLLM:       http://127.0.0.1:8000/metrics
LMCache MP: http://127.0.0.1:8080/metrics
```

Check vLLM external-cache metrics:

```bash
curl -sS http://127.0.0.1:8000/metrics \
  | grep -E '^vllm:(external_prefix_cache_(queries|hits)|prompt_tokens_cached)'
```

Check LMCache MP state:

```bash
curl -sS http://127.0.0.1:8080/metrics \
  | grep -E '^lmcache_mp_(lookup|l1_|l2_)' \
  | head -n 100
```

Lookup counters may not exist until the first request.

## 5. Terminal 3: start the Scheduler

```bash
cd /workspace/llm-stack/CacheRoute/test
source ../env/docker/cu130/scripts/activate_v1.sh

python3 demo_scheduler.py \
  --cacheroute \
  --kdn-pending-overload-th 8 \
  --kdn-active-overload-th 4 \
  --kdn-queue-ms-overload-th 30 \
  --cacheroute-log-decision 1
```

The Scheduler service plane listens on `127.0.0.1:7001` and its control plane
listens on `127.0.0.1:7002`.

## 6. Terminal 4: start the KDN Server

```bash
cd /workspace/llm-stack/CacheRoute/test
source ../env/docker/cu130/scripts/activate_v1.sh
python3 demo_kdn.py
```

The KDN Server listens on `127.0.0.1:9101`. Normal v1 builds do not require a
manual `--match`.

## 7. Terminal 5: register knowledge and build KVCache

The standard non-interactive command is:

```bash
cd /workspace/llm-stack/CacheRoute
source env/docker/cu130/scripts/activate_v1.sh

DOC=/workspace/llm-stack/CacheRoute/data/CacheRoute_dataset/knowledge_document/668f6bd1ad2419d9dfbcda0b689311b8b6696c7ed772001bea7bd12573137b4a.txt

python3 kdn_server/kdn_register_cli.py \
  --build-kv-file "$DOC" \
  --api-url http://127.0.0.1:8000/v1/chat/completions \
  --model llama3-70b \
  --redis-host 127.0.0.1 \
  --redis-port 6379 \
  --redis-db 0
```

Do not add `--match` for the normal v1 path. Do not add `--flushdb` unless the
selected Redis DB is an isolated disposable test database.

A successful build reports `dumped_keys > 0`. Inspect it with:

```bash
python3 scripts/validate_v1_kdn_roundtrip.py inspect --document "$DOC"
```

The result verifies the document-derived KID, `run_meta.json`, manifest count,
dump count, and payload size.

## 8. Terminal 6: start the Proxy

```bash
cd /workspace/llm-stack/CacheRoute/test
source ../env/docker/cu130/scripts/activate_v1.sh

python3 demo_proxy.py \
  --strategy round_robin \
  --injection-strategy iws \
  --ready-release-policy text_bypass
```

The Proxy listens on `127.0.0.1:8001`, its control plane on
`127.0.0.1:8002`, and the browser UI is normally available at
`http://127.0.0.1:8202`.

## 9. Terminal 7: start the Instance

```bash
cd /workspace/llm-stack/CacheRoute/test
source ../env/docker/cu130/scripts/activate_v1.sh

python3 demo_instance.py \
  --host 127.0.0.1 \
  --port 9001 \
  --proxy-cp-url http://127.0.0.1:8002
```

For a minimal functional test without the resource agent, add
`--no-resource-monitor`.

Confirm control-plane registration:

```bash
curl -sS http://127.0.0.1:7001/debug/status | python3 -m json.tool
curl -sS 'http://127.0.0.1:8002/v1/instance/list?include_dead=true' \
  | python3 -m json.tool
```

## 10. Terminal 8: start the Client

```bash
cd /workspace/llm-stack/CacheRoute/test
source ../env/docker/cu130/scripts/activate_v1.sh
python3 demo_client.py --with-ui
```

Open `http://127.0.0.1:7071/ui/client`. For terminal-only operation, run
`python3 demo_client.py`.

## 11. Send an end-to-end CacheRoute request

Send requests through the Scheduler rather than directly to vLLM:

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

Inspect the most recent routing decision:

```bash
curl -sS http://127.0.0.1:7001/debug/strategy | python3 -m json.tool
```

Expected service path:

```text
Client -> Scheduler :7001 -> Proxy :8001 -> Instance :9001
       -> vLLM :8000 -> LMCache MP :5555 -> Redis RESP L2 :6379
```

## 12. Reproduce the KDN build/restore/consume validation

The validator is staged because LMCache and vLLM must be restarted after Redis
restore to clear L1/GPU state before proving an L2 load.

### Stage A: build or inspect

```bash
python3 scripts/validate_v1_kdn_roundtrip.py build --document "$DOC"
python3 scripts/validate_v1_kdn_roundtrip.py inspect --document "$DOC"
```

### Stage B: restore into an isolated Redis DB

Stop LMCache and vLLM before the destructive restore. The command refuses to
run `FLUSHDB` unless both confirmation flags are present:

```bash
python3 scripts/validate_v1_kdn_roundtrip.py inject \
  --document "$DOC" \
  --flush-redis \
  --yes
```

### Stage C: prove cache consumption

Restart LMCache MP and vLLM, preserving the restored Redis keys, then run:

```bash
python3 scripts/validate_v1_kdn_roundtrip.py consume --document "$DOC"
```

Acceptance conditions include:

```text
missing files/keys/size mismatches = 0
LMCache lookup requested tokens > 0
LMCache lookup hit tokens == requested tokens
L2 prefetch hit/load > 0
L2 prefetch failures == 0
vLLM external prefix-cache hits > 0
```

The completed migration run produced 96 physical Redis keys, restored
1,006,632,960 bytes, loaded all 96 keys from RESP L2, and hit 3072/3072
chunk-aligned tokens.

## Troubleshooting boundaries

- No keys during build: verify `CACHEROUTE_RUNTIME_PROFILE=v1`, Redis, the vLLM
  request, and LMCache logs. Reusing the same prompt while LMCache L1 still holds
  it may prevent a new L2 store; restart LMCache or use a new document.
- Redis keys exist but the request misses: compare model path/identity, tokenizer,
  chat template, tensor parallel layout, KV dtype, chunk size, hash algorithm,
  and exact token prefix.
- `vllm serve` cannot connect: start LMCache MP first and verify port `5555`.
- Old YAML settings remain active: source `activate_v1.sh`, then restart LMCache
  and vLLM.
- LMCache metrics appear empty: query port `8080`, not port `8000`, and drive at
  least one lookup.
- `lmcache_mp_l2_usage_bytes` is zero after direct injection: the injector
  bypasses LMCache store accounting; use lookup/hit/load counters instead.
- Profile changes do not appear: restart every affected process after activation.
