# CacheRoute v1 runtime compatibility

This branch introduces a compatibility layer for two serving generations:

| Profile | Intended serving stack | Redis KV key handling |
|---|---|---|
| `legacy` | vLLM 0.13.x + LMCache 0.3.11 | historical `vllm@*` namespace |
| `v1` | vLLM 0.25.1 + LMCache 0.5.2 | model-scoped LMCache keys and MP interfaces |
| `auto` | startup migration discovery only | resolves to one explicit profile and then freezes |

Set the profile with:

```bash
export CACHEROUTE_RUNTIME_PROFILE=v1
# or: legacy / auto
```

## Development policy

- New features, state models, service interfaces, observability, and experiments target `v1` only.
- `legacy` remains runnable but is feature-frozen. It receives compatibility, security, availability, and critical defect fixes only.
- `auto` is not a third long-running execution mode. Startup must resolve it to `v1` or `legacy`, record the resolved profile, and keep that profile fixed for the process lifetime.
- A v1 request must never silently fall back to a Legacy write path.
- Version-specific logic belongs in `core/runtime_compat.py` or focused adapters, not scattered across Scheduler, Proxy, Instance, and KDN.

## Startup interfaces are versioned too

The serving commands are part of the runtime compatibility contract. The two stacks do not share the same primary LMCache/vLLM startup interface.

| Profile | LMCache process | vLLM connector path |
|---|---|---|
| `legacy` | YAML selected by `LMCACHE_CONFIG_FILE` | historical LMCache offloading arguments |
| `v1` | standalone `lmcache server` with MP L1/L2 | `vllm serve` with `LMCacheMPConnector` in `--kv-transfer-config` |

Do not mix the interfaces. In particular, the v1 path must unset the legacy `LMCACHE_CONFIG_FILE` and must not depend on `remote_url` or `--kv-offloading-backend lmcache`.

The complete validated commands and environment-variable overrides are in [`env/docker/cu130/README.md`](../env/docker/cu130/README.md). Existing containers can use the repository scripts directly:

```bash
export CACHEROUTE_RUNTIME_PROFILE=v1
bash env/docker/cu130/scripts/start_lmcache_mp.sh
# In another terminal after the MP port is listening:
bash env/docker/cu130/scripts/start_vllm_mp.sh
```

The v1 startup order is:

```text
LMCache L2 backend(s) -> LMCache MP -> vLLM -> CacheRoute components
```

## v1 architecture boundary

The v1 data hot path is:

```text
vLLM <-> LMCacheMPConnector <-> LMCache MP L1/L2
```

KDN is not another default KV data server in this path. KDN evolves as:

```text
Knowledge Control Plane
+ CacheRoute Cache Service Facade
+ LMCache Orchestration Gateway
```

The Gateway uses LMCache public MP HTTP, Coordinator, SDK, Metrics, and Event interfaces for observation and control. KDN keeps CacheRoute-specific knowledge, Artifact, policy, idempotency, audit, fallback, and normalized observation semantics.

The detailed architecture amendment is documented in:

- `doc/CacheRoute-v0.2.0-v1-lmcache-alignment.md`
- `doc/CacheRoute-v0.2.0-v1-lmcache-alignment-CN.md`

## KDN KV construction and Legacy compatibility

Current Redis scan/dump/restore support remains available for Legacy compatibility and migration diagnostics. Manual `--match` is no longer required in the normal CLI workflow. `auto` and `v1` may recognize the historical implicit `vllm@*` argument as a compatibility sentinel during migration tooling.

This does not make raw Redis capture the long-term v1 data architecture. New v1 features must prefer LMCache token lookup, object/tier observations, prefetch, pin, delete, Coordinator, metrics, and events through the LMCache Gateway.

An explicit `--match` remains authoritative for debugging or custom migration tools. Strict historical behavior requires:

```bash
export CACHEROUTE_RUNTIME_PROFILE=legacy
```

LMCache remote writes are asynchronous. Existing differential-capture tooling therefore retains polling, first-key timeout, and quiet-period stabilization. A capture that produces zero keys fails and removes partial output rather than marking `kv_ready`.

## Deployment profiles

### Legacy profile

```text
CUDA 12.8 / PyTorch 2.9.x / vLLM 0.13.x / LMCache 0.3.11
```

### v1 profile

```text
CUDA 13.0 / Python 3.12 / PyTorch 2.11.0+cu130
vLLM 0.25.1 / LMCache 0.5.2
```

The serving stack is owned by its Docker image. CacheRoute application dependencies must not upgrade CUDA-sensitive packages.

## Cache identity compatibility

Runtime-profile selection does not make incompatible KV blocks reusable. KDN construction and the target Instance must still agree on:

- model identity/path and model revision;
- tokenizer identity and configuration;
- tensor-parallel topology and worker layout;
- KV dtype and layout;
- LMCache chunk size and hash profile;
- serde profile;
- request tags or other key-affecting configuration;
- LMCache Endpoint, Adapter, and Tier semantics.

The validated v1 baseline currently uses chunk size `256` and hash algorithm `sha256_cbor` where the selected LMCache configuration exposes those values.

## Validation boundary

The modern image has been validated for dependency resolution, imports, `pip check`, GPU runtime availability, and startup of Scheduler/KDN/Proxy/Instance. Redis dump/restore has also been verified for the observed LMCache 0.5.2 layout.

End-to-end v1 acceptance must additionally use LMCache-native observations, including actual hit-token or remote-read metrics, rather than latency inference or Redis-key existence alone.

## Follow-up rules

Subsequent v1 changes should remain behind the compatibility and Gateway layers where vLLM/LMCache interfaces differ, including:

- Instance-side LMCache observability and metrics;
- token/artifact lookup;
- cache-object, tier, and adapter observations;
- warm prefetch, pin, clear, and task status;
- dual-profile integration tests;
- startup/configuration validation for each resolved runtime profile.

Avoid scattering version checks through the codebase. Add profile-specific behavior to the compatibility layer or focused adapters.
