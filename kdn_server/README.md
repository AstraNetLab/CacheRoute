# KDN Server

## Background: What is KDN?

Knowledge Delivery Network (KDN) is a concept proposed in *Do Large Language Models Need a Content Delivery Network?* by Cheng et al. The key idea is to treat KV caches as a medium for reusable knowledge and to deliver them across LLM engines, compute resources, and storage resources, similar to how CDNs deliver web content.

CacheRoute follows this vision and implements a lightweight KDN Server for knowledge-intensive LLM serving. In CacheRoute, the KDN Server stores reusable external knowledge, tracks KVCache availability, and injects prepared KVCache blocks into the target LMCache backend when KVCache-based knowledge injection is selected.

> Reference: Y. Cheng, K. Du, J. Yao, and J. Jiang, “Do Large Language Models Need a Content Delivery Network?”, arXiv:2409.13761, 2024.

## Overview

In CacheRoute, the KDN Server plays two roles:

- **Knowledge metadata plane:** stores text knowledge blocks, embeddings, lengths, file paths, and KVCache readiness information.
- **KVCache injection plane:** builds, stores, queries, and injects reusable KVCache blocks for knowledge-intensive LLM requests.

This allows the Scheduler and Proxy to make knowledge-aware routing and compute-network-aware injection decisions.

---

## Directory Structure

```text
kdn_server/
├── KV_database/
│   └── <knowledge_id>/
│       ├── blocks/              # dumped KVCache blocks
│       ├── manifest.jsonl        # KVCache block metadata
│       └── run_meta.json         # build-time metadata
├── text_database/
│   ├── blocks/                   # registered text blocks
│   ├── tmp/                      # temporary files
│   └── index.sqlite3             # text knowledge index
├── __init__.py
├── kdn_api.py                    # KDN HTTP service
├── kdn_register_cli.py           # interactive KDN management CLI
├── kv_builder.py                 # KVCache construction
├── kv_injector.py                # KVCache injection into Redis / LMCache backend
├── text_db.py                    # text knowledge database
└── README.md
```
Each knowledge block is identified by a content-based hash ID. Text knowledge and KVCache blocks are stored separately, while the KDN metadata links them together.

---

## API Routes

The KDN Server exposes HTTP APIs for knowledge registration, query, deletion, and metadata synchronization.

```text
POST /knowledge/search/text       Search text knowledge blocks and metadata.
POST /knowledge/register_text     Register a new text knowledge block.
POST /knowledge/delete            Delete a knowledge block.
POST /knowledge/purge_all         Clear the KDN database.
POST /knowledge/snapshot          Export KDN metadata for Scheduler synchronization.
```

Typical metadata fields include:

```text
content
length
rel_path
embedding
embed_dim
kv_ready
kv_rel_dir
kv_dumped_keys
kv_updated_at
embedding_head
```
Example query:

```bash
curl -s http://127.0.0.1:9101/knowledge/search/text \
  -H "Content-Type: application/json" \
  -d '{
    "knowledge_ids": [
      "7a2b0b48a2d9b353c57f13c4bf943c9e3c8a6e2dc7cff2619507f39e0447d7fc"
    ],
    "need_fields": ["embedding", "length"]
  }' | head -c 300
```

---

## Quick Start

### 1. Start the KDN Server

From the CacheRoute root directory:

```bash
python3 kdn_server/kdn_api.py
```

By default, the KDN Server listens on port `9101`. The actual host and port can be configured in `core/config.py`.

### 2. Start the KDN CLI

Open another terminal and run:

```bash
python3 kdn_server/kdn_register_cli.py
```

The CLI provides an interactive interface for text registration, KVCache construction, knowledge query, deletion, database cleanup, and KDN pool status inspection.

<img width="600" height="340" alt="KDN CLI" src="https://github.com/user-attachments/assets/26de41b7-5f89-47dd-8024-8f2bd1cba141" />

---

## Text Knowledge Registration

KDN first registers external knowledge as text blocks. For each text block, KDN generates a hash-based knowledge ID, stores the text content, and records metadata such as length, file path, embedding, and embedding dimension.

You can directly paste a short text into the CLI, or register a file:

```text
:file /path/to/the/file
```

Example:

```text
:file /workspace/llm-stack/KDN_server/prompts/req1.txt
```

After registration, the CLI returns an `[ok]` status and shows the corresponding metadata.

<img src="../.assets/readme_kdn_server_cli.png" width="600" alt="KDN text registration">

---

## KVCache Construction

After text knowledge is registered, KDN can send the text block to the vLLM + LMCache engine to build reusable KVCache blocks.

Before running KVCache construction, make sure the following services are ready:

- vLLM + LMCache engine
- Redis backend used by LMCache
- KDN Server

A typical command is:

```bash
python3 kdn_build_kv.py \
  --txt /file/to/.txt \
  --kv-root /path/for/save/kv_cache \
  --api-url http://127.0.0.1:8000/v1/chat/completions \
  --model llama3-70b \
  --max-tokens 1 \
  --redis-host 127.0.0.1 \
  --redis-port 6379 \
  --flushdb
```

A single knowledge block may be split into multiple KVCache chunks. KDN stores the dumped KVCache blocks under a directory named by the corresponding knowledge ID.

```text
KV_database/
└── <knowledge_id>/
    ├── blocks/
    ├── manifest.jsonl
    └── run_meta.json
```

<img src="../.assets/readme_kdn_server_kvdump.png" width="600" alt="KDN KVCache dump">

---

## CLI Commands

The KDN CLI wraps the main KDN maintenance operations.

### Register text

```text
:file /workspace/llm-stack/KDN_server/prompts/req1.txt
```

You can also paste text directly into the CLI.

### Build KVCache for a registered knowledge ID

```text
:buildkv 7a2b0b48a2d9b353c57f13c4bf943c9e3c8a6e2dc7cff2619507f39e0447d7fc \
  --api-url http://127.0.0.1:8000/v1/chat/completions \
  --model llama3-70b \
  --max-tokens 1
```

### Register a file and build KVCache

This is the most common workflow. It registers the text file and builds the corresponding KVCache in one command.

```text
:buildkv_file /workspace/llm-stack/KDN_server/prompts/req2.txt \
  --api-url http://127.0.0.1:8000/v1/chat/completions \
  --model llama3-70b
```

You can add `--flushdb` when needed, but use it carefully because it clears the Redis cache.

<img src="../.assets/readme_kdn_server_cli_2.png" width="600" alt="KDN buildkv file">

### Query knowledge status

```text
:status 7a2b0b48a2d9b353c57f13c4bf943c9e3c8a6e2dc7cff2619507f39e0447d7fc
```

<img src="../.assets/readme_kdn_server_cli_status.png" width="600" alt="KDN status">

### Delete a knowledge block

```text
:delete 30f75ee46371ecb883e24fdf2917d9e0d853961faf01ef3052582d097f6c795d
```

<img src="../.assets/readme_kdn_server_cli_delete.png" width="600" alt="KDN delete">

### Clear the KDN database

```text
:purge
```

To keep KVCache files and only clear text metadata:

```text
:purge --no-kv
```

<img src="../.assets/readme_kdn_server_cli_purge.png" width="600" alt="KDN purge">

### View KDN pool status

```text
:pool
```

You can limit the number of displayed samples:

```text
:pool --sample-limit 5
```

<img width="600" height="260" alt="KDN pool status" src="https://github.com/user-attachments/assets/eadbd610-4424-4e5e-86ff-dd8dfb9fea2b" />

---

## KVCache Injection

KDN can inject prepared KVCache blocks into the Redis backend used by LMCache. This allows the target LLM instance to reuse the injected KVCache blocks during later inference.

A standalone injection command is:

```bash
python3 kv_injector.py \
  --kv-dir /path/save/kvcache \
  --redis-host 127.0.0.1 \
  --redis-port 6379
```

This command is mainly used for functional validation and debugging. In the full CacheRoute workflow, KVCache injection is triggered by the KDN matching and scheduling process.

---

## Network Path Debugging

In local experiments, the Instance control plane may pass `127.0.0.1` as the Redis host. In that case, KDN connects to Redis through the loopback interface. To test cross-machine or cross-NIC behavior, KDN supports host rewriting.

### Rewrite loopback Redis host

```bash
export KDN_REDIS_REWRITE_ENABLE=1
export KDN_REWRITE_LOOPBACK_TO=172.18.0.169
```

When the requested Redis host is `127.0.0.1`, `localhost`, or `::1`, KDN rewrites it to `172.18.0.169`.

### Force a Redis host

```bash
export KDN_REDIS_REWRITE_ENABLE=1
export KDN_FORCE_REDIS_HOST=172.18.0.169
```

With this setting, KDN always connects to the specified Redis host, regardless of the host passed by the upstream control plane.

KDN logs print both `request_host` and `resolved_host` to help verify whether traffic goes through the expected network path.

By default:

```bash
export KDN_REDIS_REWRITE_ENABLE=0
```

or leaving it unset disables host rewriting.

---

## Network Transfer Simulation

When `KDN_NETWORK_ENABLE=1`, KDN enables a simple network transfer simulator for KVCache injection.

The current simulator uses a single-link serial service model:

- only one knowledge transfer task is served at a time;
- later transfer tasks wait in a pending queue;
- acknowledgements are delayed according to the estimated network latency.

The default parameters can be configured through `core/config.py` with the `KDN_NETWORK_*` options. They can also be overridden by environment variables with the same names.

This simulator is useful for validating compute-network-aware injection decisions in CacheRoute.

---

## End-to-End Knowledge Injection Workflow

A complete external knowledge injection workflow contains the following steps.

### 1. Start the KDN Server and CLI

```bash
python3 test/demo_kdn.py
python3 kdn_server/kdn_register_cli.py
```

### 2. Start vLLM + LMCache + Redis

Follow the full deployment guide in the main `README.md`.

### 3. Register text and build KVCache

In the KDN CLI, run:

```text
:buildkv_file /workspace/llm-stack/CacheRoute/kdn_server/test1.txt \
  --api-url http://127.0.0.1:8000/v1/chat/completions \
  --model llama3-70b
```

<img width="600" height="107" alt="KDN buildkv example" src="https://github.com/user-attachments/assets/526aea05-18af-405d-bc0b-355f39c1a97e" />

### 4. Clear Redis and restart the model if needed

For a clean validation, restart the model and run `FLUSHDB` on the Redis backend.

### 5. Inject the prepared KVCache

```bash
python3 kv_injector.py \
  --kv-dir /workspace/llm-stack/CacheRoute/kdn_server/KV_database/a4da9fe548b2b2d66bb5cd1dae29f03a4c0c0eef88fe964757754cad878cc725 \
  --redis-host 127.0.0.1 \
  --redis-port 6379
```

<img width="600" height="138" alt="KVCache injection example" src="https://github.com/user-attachments/assets/372905dc-0201-4108-9fae-f916db5ae997" />

### 6. Verify KVCache reuse

Run the reuse test script:

```bash
python3 test_kv_injector_reuse.py
```

If the injection succeeds, the instance should reuse the injected KVCache blocks through LMCache.

<img width="600" height="50" alt="KVCache reuse test" src="https://github.com/user-attachments/assets/d02b5d2d-1950-4374-a9da-3483929900bc" />

---

## Batch Knowledge Registration

For larger experiments, KDN provides a batch registration script:

```text
kdn_server/util/batch_register_kdn.py
```

The script uses a manifest file to register multiple knowledge documents and optionally build their KVCache blocks.

Example:

```bash
python3 batch_register_kdn.py \
  --manifest knowledge_manifest_nq.json \
  --base-url http://127.0.0.1:9101 \
  --api-url http://127.0.0.1:8000/v1/chat/completions \
  --model llama3-70b \
  --redis-host 127.0.0.1 \
  --redis-port 6379 \
  --redis-db 0 \
  --count all \
  --flushdb
```

Main arguments:

| Argument | Description |
|---|---|
| `--manifest` | Path to the knowledge manifest JSON file. |
| `--base-url` | KDN Server URL. |
| `--api-url` | vLLM OpenAI-compatible API URL. |
| `--model` | Model name served by vLLM. |
| `--redis-host` | Redis host used by LMCache. |
| `--redis-port` | Redis port. |
| `--redis-db` | Redis database index. Default is `0`. |
| `--count` | Number of knowledge items to register. Use `all` for the full manifest. |
| `--flushdb` | Clear Redis before registration. Use carefully. |

The batch script is useful for preparing knowledge-intensive workloads used in CacheRoute experiments.

<img width="600" height="242" alt="Batch KDN registration" src="https://github.com/user-attachments/assets/2bbbca78-93f2-4b08-aab5-268e413580a9" />

---

## Notes

- KDN is currently an experimental component used to validate knowledge-oriented routing and compute-network-aware knowledge injection in CacheRoute.
- The standalone `kv_injector.py` path is mainly for debugging. In the full CacheRoute workflow, KVCache injection should be triggered by the scheduling and KDN matching process.
- Some paths and model names in the examples should be adjusted according to your local deployment.
- For full deployment with vLLM, LMCache, Redis, Scheduler, Proxy, and Instance, see the main `README.md`.
