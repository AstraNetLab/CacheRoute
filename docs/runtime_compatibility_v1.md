# CacheRoute v1 runtime compatibility

This branch introduces a compatibility layer for two serving generations:

| Profile | Intended serving stack | Redis KV key handling |
|---|---|---|
| `legacy` | vLLM 0.13.x + LMCache 0.3.11 | historical `vllm@*` namespace |
| `v1` | vLLM 0.25.x + LMCache 0.5.2 | model-scoped LMCache keys |
| `auto` | default | discovers and validates either layout |

Set the profile with:

```bash
export CACHEROUTE_RUNTIME_PROFILE=auto   # default
# or: legacy / v1
```

## KDN KV construction

Manual `--match` is no longer required in the normal CLI workflow. `auto`
mode treats the historical implicit `vllm@*` argument as a compatibility
sentinel and scans for supported LMCache key layouts.

An explicit `--match` remains authoritative for debugging or custom backends.
For strict legacy behavior, set `CACHEROUTE_RUNTIME_PROFILE=legacy`.

LMCache remote writes are asynchronous. KDN therefore uses:

- a polling interval (default `0.2s`),
- a maximum first-key timeout (default `30s`), and
- a quiet period after the last key-set change (default `1.5s`).

The 30-second value is an upper bound, not a fixed delay. A normal build exits
as soon as keys appear and remain unchanged for the quiet period.

A build that captures zero keys now fails and removes its partial output
directory. It is never marked `kv_ready`.

## Deployment policy

Keep the serving stack (CUDA, PyTorch, vLLM, and LMCache) owned by its Docker
image. CacheRoute application dependencies should not upgrade those packages.
The existing legacy image remains supported. A separate v1 image should pin the
new serving stack and reuse the same CacheRoute branch/profile interface.

For reliable differential capture, use a dedicated Redis database or Redis
instance for KDN construction. `--flushdb` must not target an online shared DB.

## Follow-up migration scope

Subsequent v1 changes should remain behind the compatibility layer where the
vLLM/LMCache interfaces differ, including connector configuration, metrics,
request metadata, and cache-hit validation. Avoid scattering version checks
through Scheduler, Proxy, Instance, and KDN code.
