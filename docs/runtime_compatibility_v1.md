# CacheRoute v1 runtime compatibility

This branch introduces a compatibility layer for two serving generations:

| Profile | Intended serving stack | Redis KV key handling |
|---|---|---|
| `legacy` | vLLM 0.13.x + LMCache 0.3.11 | historical `vllm@*` namespace |
| `v1` | vLLM 0.25.1 + LMCache 0.5.2 | model-scoped LMCache keys |
| `auto` | default | discovers and validates either layout |

Set the profile with:

```bash
export CACHEROUTE_RUNTIME_PROFILE=auto   # default
# or: legacy / v1
```

The additive CUDA 13 image under [`env/docker/cu130`](../env/docker/cu130)
sets `CACHEROUTE_RUNTIME_PROFILE=v1` by default. The legacy image and root
requirements remain unchanged.

## KDN KV construction

Manual `--match` is no longer required in the normal CLI workflow. `auto` and
`v1` modes treat the historical implicit `vllm@*` argument as a compatibility
sentinel and scan for supported LMCache key layouts.

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

## Deployment profiles

The serving stack remains owned by its Docker image. CacheRoute application
dependencies must not upgrade CUDA-sensitive packages.

### Legacy profile

The existing environment remains the stable path for:

```text
CUDA 12.8 / PyTorch 2.9.x / vLLM 0.13.x / LMCache 0.3.11
```

Use:

```bash
export CACHEROUTE_RUNTIME_PROFILE=legacy
```

when strict historical Redis-key behavior is required.

### v1 profile

The isolated modern image is defined in [`env/docker/cu130`](../env/docker/cu130):

```text
CUDA 13.0 / Python 3.12 / PyTorch 2.11.0+cu130
vLLM 0.25.1 / LMCache 0.5.2
```

It uses `/opt/venv`, keeps the modern serving stack separate from Ubuntu system
packages, installs FFmpeg for TorchCodec, and preserves Rust/Cargo and Tkinter
for existing CacheRoute auxiliary components.

The v1 dependency files are additive. They do not modify:

- `env/docker/Dockerfile`,
- root `requirements.txt`,
- `pyproject.toml`, or
- legacy runtime behavior.

For reliable differential capture, use a dedicated Redis database or Redis
instance for KDN construction. `--flushdb` must not target an online shared DB.

## Validation boundary

The modern image has been validated for installation, imports, `pip check`, GPU
runtime availability, and startup of the CacheRoute Scheduler/KDN/Proxy/Instance
workflow.

The KDN raw Redis dump/restore path has also been verified byte-for-byte for the
observed LMCache 0.5.2 key/value layout. This proves storage integrity, but does
not yet prove that a request consumes the injected blocks through LMCache MP.
End-to-end validation must compare LMCache hit-token and remote-read metrics.

## Follow-up migration scope

Subsequent v1 changes should remain behind the compatibility layer where the
vLLM/LMCache interfaces differ, including:

- LMCache MP and vLLM connector startup configuration,
- Instance-side observability and metric collection,
- request metadata and prompt-prefix compatibility,
- injected-cache hit validation,
- dual-profile integration tests.

Avoid scattering version checks through Scheduler, Proxy, Instance, and KDN
code. Add profile-specific behavior to the compatibility layer or focused
adapters.
