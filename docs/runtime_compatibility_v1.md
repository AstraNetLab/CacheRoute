# CacheRoute v1 runtime compatibility

CacheRoute supports two serving generations through one compatibility layer:

| Profile | Intended serving stack | Redis KV key handling |
|---|---|---|
| `legacy` | vLLM 0.13.x + LMCache 0.3.11 | historical `vllm@*` namespace |
| `v1` | vLLM 0.25.1 + LMCache 0.5.2 | model-scoped LMCache keys |
| `auto` | default outside the dedicated v1 image | discovers and validates either layout |

Set the profile with:

```bash
export CACHEROUTE_RUNTIME_PROFILE=auto
# or: legacy / v1
```

For the modern stack, source the repository activation script instead of
repeating environment variables in every terminal:

```bash
source env/docker/cu130/scripts/activate_v1.sh
```

The additive CUDA 13 image under [`env/docker/cu130`](../env/docker/cu130) sets
`CACHEROUTE_RUNTIME_PROFILE=v1` by default. The legacy image and root
requirements remain unchanged.

## Startup interfaces are versioned

The serving commands are part of the runtime compatibility contract:

| Profile | LMCache process | vLLM connector path |
|---|---|---|
| `legacy` | YAML selected by `LMCACHE_CONFIG_FILE` | historical LMCache offloading arguments |
| `v1` | standalone `lmcache server` with RESP L2 | `vllm serve` with `LMCacheMPConnector` in `--kv-transfer-config` |

Do not mix the interfaces. The v1 path must not depend on `remote_url`,
`LMCACHE_CONFIG_FILE`, or `--kv-offloading-backend lmcache`.

The validated v1 startup order is:

```text
Redis RESP L2 -> LMCache MP :5555 -> vLLM :8000 -> CacheRoute components
```

Complete commands and overrides are documented in
[`env/docker/cu130/README.md`](../env/docker/cu130/README.md). Existing
compatible containers can use the merged `main` branch without rebuilding.

## KDN KV construction

Manual `--match` is no longer required in the normal CLI workflow. `auto` and
`v1` treat the historical implicit `vllm@*` value as a compatibility sentinel
and scan for supported LMCache key layouts. An explicit `--match` remains
authoritative for debugging or custom backends.

LMCache remote writes are asynchronous. KDN uses:

- polling interval: `0.2s` by default;
- maximum first-key timeout: `30s` by default;
- quiet period after the last key-set change: `1.5s` by default.

The 30-second value is an upper bound, not a fixed delay. A zero-key build fails,
removes its partial output, and is never marked `kv_ready`.

## Deployment profiles

### Legacy profile

The stable legacy path remains:

```text
CUDA 12.8 / PyTorch 2.9.x / vLLM 0.13.x / LMCache 0.3.11
```

Use `CACHEROUTE_RUNTIME_PROFILE=legacy` for strict historical Redis-key
behavior.

### v1 profile

The modern image is defined in [`env/docker/cu130`](../env/docker/cu130):

```text
CUDA 13.0 / Python 3.12 / PyTorch 2.11.0+cu130
vLLM 0.25.1 / LMCache 0.5.2
```

It uses `/opt/venv`, isolates the serving stack from Ubuntu system packages,
installs FFmpeg for TorchCodec, and preserves Rust/Cargo and Tkinter for
CacheRoute auxiliary components.

The v1 dependency files are additive. They do not modify the legacy Dockerfile,
root `requirements.txt`, `pyproject.toml`, or legacy runtime behavior.

## Cache identity compatibility

Runtime-profile selection does not make incompatible KV blocks reusable. KDN
construction and the consuming Instance must agree on:

- model identity/path and served model;
- tokenizer, chat template, and exact token prefix;
- tensor-parallel topology and worker layout;
- model/KV dtype;
- LMCache chunk size;
- LMCache hash algorithm;
- connector generation and key serialization;
- Redis endpoint/database semantics.

The validated v1 baseline uses TP=8, chunk size `256`, and hash algorithm
`sha256_cbor`.

## Completed validation

The environment migration has been validated beyond byte-level storage:

- modern LMCache keys were captured without manual `--match`;
- 96 physical key/value blocks were persisted locally;
- Redis restore reproduced 96 keys and 1,006,632,960 payload bytes with no
  missing, extra, size-mismatched, or sampled SHA256-mismatched entries;
- after LMCache/vLLM restart, LMCache found and loaded all 96 blocks from RESP
  L2;
- LMCache reported 3072 requested and 3072 hit tokens;
- vLLM reported 3072 externally cached prompt tokens;
- LMCache reported zero L2 prefetch failures.

The relationship between physical keys and cached tokens is:

```text
96 Redis keys / 8 TP ranks = 12 logical chunks
12 chunks * 256 tokens     = 3072 cached tokens
```

Detailed evidence and the reproducible staged workflow are in
[`v1_migration_closeout.md`](v1_migration_closeout.md).

## Metrics contract

Use the correct endpoint for each subsystem:

```text
vLLM metrics:       http://127.0.0.1:8000/metrics
LMCache MP metrics: http://127.0.0.1:8080/metrics
```

Important vLLM counters include:

```text
vllm:external_prefix_cache_queries_total
vllm:external_prefix_cache_hits_total
vllm:prompt_tokens_cached_total
```

Important LMCache MP counters include:

```text
lmcache_mp_lookup_requested_tokens_total
lmcache_mp_lookup_hit_tokens_total
lmcache_mp_l2_prefetch_hit_chunks_total
lmcache_mp_l2_prefetch_load_completed_chunks_total
lmcache_mp_l2_prefetch_failure_chunks_total
```

LMCache lookup metrics may not exist before the first request. Direct KDN Redis
injection bypasses LMCache store accounting, so `lmcache_mp_l2_usage_bytes` is
not a reliable indicator for injected data.

## Future compatibility work

Subsequent changes should continue to isolate version-specific behavior behind
`core/runtime_compat.py` or focused adapters rather than scattering version
checks through Scheduler, Proxy, Instance, and KDN.

Future feature development may extend Instance observability, request metadata,
cache placement, predictors, and UI behavior while using the validated v1
runtime as the modern baseline. Reopen environment migration only when the
serving-stack version or cache-identity contract changes.
