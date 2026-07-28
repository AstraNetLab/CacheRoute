# CacheRoute v1 migration closeout

This document records the validated baseline for the modern CacheRoute serving
stack and defines the boundary between environment migration work and subsequent
feature development.

## Validated serving baseline

| Component | Validated value |
|---|---|
| Base image | CUDA 13.0 / Ubuntu 22.04 |
| Python | 3.12.x |
| PyTorch | 2.11.0+cu130 |
| vLLM | 0.25.1 |
| LMCache | 0.5.2 |
| LMCache mode | standalone MP server |
| vLLM connector | `LMCacheMPConnector` |
| L2 backend | Redis RESP, DB 0 |
| Tensor parallel size | 8 |
| LMCache chunk size | 256 tokens |
| Hash algorithm | `sha256_cbor` |
| Model | `Meta-Llama-3-70B-Instruct` served as `llama3-70b` |

The modern startup contract is:

```text
Redis RESP L2
  -> LMCache MP :5555 / HTTP :8080
  -> vLLM + LMCacheMPConnector :8000
  -> Scheduler -> KDN -> Proxy -> Instance -> Client
```

The legacy and modern startup interfaces must not be mixed:

- legacy uses `LMCACHE_CONFIG_FILE`, YAML `remote_url`, and historical vLLM
  offloading flags;
- v1 uses `lmcache server`, RESP L2, and `vllm serve --kv-transfer-config`.

## Runtime compatibility result

`CACHEROUTE_RUNTIME_PROFILE` provides three modes:

| Profile | Behavior |
|---|---|
| `legacy` | strict historical `vllm@*` Redis namespace |
| `v1` | modern model-scoped LMCache Redis keys |
| `auto` | accepts either supported key generation |

Normal v1 registration no longer requires a manual `--match`. The historical
CLI default `vllm@*` is treated as a compatibility sentinel in `v1` and `auto`
profiles, so the builder scans and validates the modern key layout automatically.
An explicit `--match` remains available for debugging and custom backends.

The 30-second build setting is a maximum first-key timeout, not a fixed sleep.
After keys appear, capture completes when the key set remains unchanged for the
configured quiet period.

## End-to-end KDN validation evidence

The closeout validation used:

```text
data/CacheRoute_dataset/knowledge_document/
668f6bd1ad2419d9dfbcda0b689311b8b6696c7ed772001bea7bd12573137b4a.txt
```

The document-derived KID matched the filename:

```text
668f6bd1ad2419d9dfbcda0b689311b8b6696c7ed772001bea7bd12573137b4a
```

### Build and local persistence

The v1 KDN builder produced:

```text
runtime_profile:  v1
key_formats:      [v1]
scan_match:       *
keys_before:      0
keys_after:       96
keys_new:         96
dumped_keys:      96
manifest records: 96
dump files:       96
local size:       approximately 961 MiB
capture elapsed:  8.931 seconds
```

The registration command did not include `--match` or `--flushdb`.

### Redis restore integrity

After Redis DB 0 was explicitly cleared, `kdn_server/kv_injector.py` restored
all saved blocks:

```text
injected:                 96
missing_files:            0
Redis keys:               96
missing_keys:             0
extra_keys:               0
size_mismatches:          0
expected_payload_bytes:   1,006,632,960
actual_payload_bytes:     1,006,632,960
sample SHA256 mismatches: 0
```

This proves byte-for-byte preservation of the original Redis key/value pairs.

### Actual LMCache consumption

LMCache and vLLM were restarted after restore so that LMCache L1 and the vLLM
GPU cache started empty. An exact builder-style request was sent with the
normalized document as the only `system` message.

vLLM reported:

```text
prompt tokens:                         3293
external prefix-cache queries:         3293
external prefix-cache hits:            3072
prompt tokens cached:                  3072
```

LMCache MP reported:

```text
lookup requested tokens:               3072
lookup hit tokens:                     3072
lookup hit rate:                       100%
L2 prefetch lookup requests:           1
L2 prefetch lookup objects:            96
L2 prefetch hit chunks:                96
L2 prefetch load completed chunks:     96
L2 prefetch failure chunks:            0
L1 write chunks:                       96
L1 read chunks:                        96
```

The physical-key count is consistent with the runtime topology:

```text
96 physical Redis keys / 8 TP ranks = 12 logical chunks
12 logical chunks * 256 tokens      = 3072 cached tokens
```

The remaining 221 prompt tokens were not a full 256-token chunk and were
recomputed by vLLM:

```text
3293 total prompt tokens - 3072 cached tokens = 221 recomputed tokens
```

This closes the previous validation gap: the KDN artifact was not only saved and
restored correctly; it was discovered in Redis, prefetched into LMCache L1, and
consumed by vLLM as external prefix cache.

## Metrics endpoints

The two metrics endpoints are distinct:

| Endpoint | Owner | Important metrics |
|---|---|---|
| `http://127.0.0.1:8000/metrics` | vLLM | `vllm:external_prefix_cache_queries_total`, `vllm:external_prefix_cache_hits_total`, `vllm:prompt_tokens_cached_total` |
| `http://127.0.0.1:8080/metrics` | LMCache MP | `lmcache_mp_lookup_requested_tokens_total`, `lmcache_mp_lookup_hit_tokens_total`, `lmcache_mp_l2_prefetch_hit_chunks_total`, `lmcache_mp_l2_prefetch_load_completed_chunks_total`, `lmcache_mp_l2_prefetch_failure_chunks_total` |

LMCache metrics may not exist until the first store or lookup event. A direct KDN
Redis injection also bypasses LMCache's own store accounting, so
`lmcache_mp_l2_usage_bytes` must not be used as proof that Redis is empty.

## Reproducible validation tools

Activate v1 in every terminal:

```bash
source env/docker/cu130/scripts/activate_v1.sh
```

Run the non-destructive environment check:

```bash
python3 env/docker/cu130/scripts/check_v1_environment.py --require-running
```

Use the staged KDN validator:

```bash
DOC=/workspace/llm-stack/CacheRoute/data/CacheRoute_dataset/knowledge_document/668f6bd1ad2419d9dfbcda0b689311b8b6696c7ed772001bea7bd12573137b4a.txt

python3 scripts/validate_v1_kdn_roundtrip.py build --document "$DOC"
python3 scripts/validate_v1_kdn_roundtrip.py inspect --document "$DOC"
```

The restore stage is destructive only when explicitly confirmed:

```bash
python3 scripts/validate_v1_kdn_roundtrip.py inject \
  --document "$DOC" \
  --flush-redis \
  --yes
```

After injection, restart LMCache and vLLM to clear L1/GPU state, then run:

```bash
python3 scripts/validate_v1_kdn_roundtrip.py consume --document "$DOC"
```

The validator deliberately does not combine injection and consumption into one
unattended command because the service restart between the two stages is part of
the correctness contract.

## Cache-identity compatibility requirements

A reusable artifact is valid only when producer and consumer agree on at least:

- model identity and actual model path used by LMCache keys;
- served model and tokenizer;
- chat template and exact token prefix;
- tensor-parallel size and worker/rank layout;
- model/KV dtype;
- LMCache chunk size;
- LMCache hash algorithm;
- connector generation and key serialization;
- Redis database semantics.

A byte-perfect Redis restore proves transport integrity but does not override an
identity mismatch. Cache consumption metrics remain the final acceptance test.

## Safety rules

- Do not use `--flushdb` during normal KDN registration.
- Do not run `FLUSHDB` against a shared or production Redis database.
- The round-trip validator requires both `--flush-redis` and `--yes` before it
  performs destructive cleanup.
- `redis-cli` is optional; the documented tools use the Python Redis client.
- The correct standalone injector is `kdn_server/kv_injector.py`.

## Migration definition of done

The following migration goals are complete:

- legacy environment and startup documentation remain available;
- isolated CUDA 13 / vLLM 0.25.1 / LMCache 0.5.2 image profile exists;
- LMCache MP and vLLM startup scripts exist;
- v1 profile activation is explicit and repeatable;
- KDN recognizes modern LMCache keys without manual `--match`;
- asynchronous writes are captured without a fixed 30-second delay;
- zero-key builds fail instead of becoming `kv_ready`;
- local dump/manifest integrity is verified;
- Redis restore is byte-for-byte verified;
- LMCache RESP L2 lookup/load is verified;
- vLLM external-prefix-cache consumption is verified;
- environment and round-trip checks are reproducible from repository scripts.

Future Scheduler, Proxy, Instance, predictor, and UI work can now use this v1
runtime as the modern development baseline without reopening the environment
migration unless the serving-stack versions or cache identity change.
