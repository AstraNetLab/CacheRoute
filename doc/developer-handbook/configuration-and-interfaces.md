# Configuration and interfaces

[Back to handbook](README.md). This chapter catalogs developer-facing surfaces;
[`core/config.py`](../../core/config.py) and owning source remain exact truth.
Do not interpret reserved constants as active interfaces.

## Profiles and request switches

| Item | Type / default / values | Scope and effect | Evidence |
|---|---|---|---|
| `CACHEROUTE_RUNTIME_PROFILE` | string; default `auto`; canonical values `auto`, `legacy`, `v1`, `test/mock`; aliases accepted | Startup compatibility selection. `test/mock` forbids real Redis selection. | [`compat/runtime.py`](../../src/cacheroute/compat/runtime.py), [`test_runtime_compat.py`](../../test/test_runtime_compat.py) |
| `RuntimeProfile` | enum `v1`, `legacy`, `test/mock`, `auto` | `auto` is startup-only and rejected in persisted models/contracts. | [`profiles.py`](../../src/cacheroute/runtime/profiles.py) |
| `RAG` | request boolean; compatibility request model default is source-owned | Enables knowledge use. | [`core/request.py`](../../core/request.py) |
| `Injection_type` | request string; active modes `text`, `kvcache`; perf choice also `hybrid` | Selects recomputation/cache path. Missing-path defaults differ by caller, so inspect the target model rather than imposing one global default. | [`core/request.py`](../../core/request.py), [`perf_client.py`](../../client/perf_client.py), [`queue/manager.py`](../../proxy/queue/manager.py) |
| `--hybrid-pattern` | `KV:text`, default `2:1`, both positive | Perf client expands hybrid requests deterministically. | [`perf_client.py`](../../client/perf_client.py) |

## Service environment

| Owner | Variables / defaults | Runtime effect / validation |
|---|---|---|
| Scheduler | `SCHEDULER_MODEL_PATH` → configured model; `SCHEDULER_EMBEDDING_MODEL` → configured embedding model; `SCHEDULER_KDN_REFRESH_INTERVAL_S`; CLI `SCHEDULER_BASE_URL`, `SCHEDULER_CP_URL` | Model/embedding selection, KDN refresh, CLI control addresses. See [`scheduler.py`](../../scheduler/scheduler.py), [`kdn_sync.py`](../../scheduler/knowledge/kdn_sync.py), [`scheduler_cli.py`](../../scheduler/scheduler_cli.py). |
| Proxy CLI | `PROXY_CP_URL=http://127.0.0.1:8002`, `SCHEDULER_CP_URL=http://127.0.0.1:7002`, `PROXY_ID=""`; `--timeout=5.0` | Control-plane inspection/commands. See [`proxy_cli.py`](../../proxy/proxy_cli.py). |
| KDN | `KDN_TEXT_DB_DIR`, `KDN_KV_DB_DIR`, `KDN_EMBEDDING_MODEL`, `KDN_ID`, advertise host/port, Scheduler CP URL; Redis rewrite and network-simulation switches | Storage roots, identity/registration, embedding, address rewriting, and simulated transfer cost. Rewrite defaults disabled; network defaults are defined in config. See [`kdn_api.py`](../../kdn_server/kdn_api.py) and [`core/config.py`](../../core/config.py). |

## HTTP, debug, and UI interfaces

The OpenAI-compatible chat/completion endpoints and control-plane ports are
listed with launch commands in the component READMEs; use those documents rather
than assuming every `DEFAULT_*` constant is live. KDN knowledge registration,
status, build, and injection interfaces are detailed in the
[KDN README](../../kdn_server/README.md). Scheduler/Proxy/Instance resource and
registration interfaces are detailed in their respective READMEs.

Current browser interfaces include `/ui/client` plus parse/validate/send APIs in
[`UI/client_ui/app.py`](../../UI/client_ui/app.py); Proxy UI health, status,
instances, resources, topology, loads, and scheduler-proxy APIs in
[`UI/proxy_ui/proxy_ui_server.py`](../../UI/proxy_ui/proxy_ui_server.py); and TTFT
predictor `/`, `/predict`, `/report_prefill` in
[`prefill_prediction_server.py`](../../instance/TTFT_predictor/prefill_prediction_server.py).
These UI/predictor endpoints are operational, not canonical library API.

## Wire responses and SSE metadata

Request and response models are owned by [`core/request.py`](../../core/request.py)
and canonical v1 contracts by [`cacheroute.contracts.v1`](public-api-and-data-models.md).
Streaming consumers parse SSE in the clients and preserve server timing/trace
metadata. The perf client reports requested/actual injection mode, actual text
or KV path, queue/wait/knowledge/network/compute timings when supplied, and
warnings for incomplete traces. A field's presence in a trace dictionary does
not make it a versioned cross-process contract.

## Packaging interface

Python requires `>=3.10`. [`pyproject.toml`](../../pyproject.toml) uses an
explicit `packages` list and package-data map; automatic discovery is disabled.
Documentation, tests, environment files, scripts, and logs remain outside wheel
top-level packages. No console-script entry point is currently declared.
