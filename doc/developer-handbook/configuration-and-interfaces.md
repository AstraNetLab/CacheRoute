# Configuration and interfaces

[Back to handbook](README.md). These tables centralize Current developer-facing
surfaces; linked source remains exact authority. Defaults marked “caller” differ
intentionally. Reserved constants and function-local implementation constants
are omitted.

## Runtime profiles and injection modes

| Item | Owner/source | Type; default; allowed values | Scope/effect | Compatibility/validation |
|---|---|---|---|---|
| `CACHEROUTE_RUNTIME_PROFILE` | [`compat/runtime.py`](../../src/cacheroute/compat/runtime.py) | string; `auto`; `auto`, `legacy`, `v1`, `test/mock` plus aliases | startup/key-layout compatibility | `old`/`v0`→Legacy; `modern`/`new`/`current`→v1; `mock`/`test`→test/mock; invalid fails; test/mock cannot access real Redis. [`test_runtime_compat.py`](../../test/test_runtime_compat.py) |
| `Injection_type` | [`core/request.py`](../../core/request.py) | string; `Request.build_request` default `kvcache`; canonical sent values `kvcache`, `text` | Proxy knowledge path | missing/empty/invalid→`kvcache`; `kv`, `kv_cache`, `kv-cache`→`kvcache`; `prompt`→`text`. |
| Perf `--injection-type` | [`client/perf_client.py`](../../client/perf_client.py) | choice; default `text`; `text`, `kvcache`, `hybrid` | workload generation | `hybrid` is expanded client-side using `--hybrid-pattern` (`2:1` default, positive KV:text integers); it is not an Instance primitive. |

## Environment variables

| Owner | Variable(s) | Type/default | Scope and runtime effect | Compatibility / evidence |
|---|---|---|---|---|
| Scheduler | `SCHEDULER_MODEL_PATH` | path; `DEFAULT_MODEL` | tokenizer/model used to build requests | [`scheduler.py`](../../scheduler/scheduler.py), [`core/config.py`](../../core/config.py) |
| Scheduler | `SCHEDULER_EMBEDDING_MODEL` | string/path; `DEFAULT_EMBED_MODEL` | retrieval embedding engine | [`scheduler.py`](../../scheduler/scheduler.py) |
| Scheduler | `SCHEDULER_KDN_REFRESH_INTERVAL_S` | integer seconds; 30 | KDN metadata refresh cadence | [`kdn_sync.py`](../../scheduler/knowledge/kdn_sync.py) |
| Scheduler CLI/demo | `SCHEDULER_BASE_URL`, `SCHEDULER_CP_URL` | URLs; `http://127.0.0.1:7001`, `http://127.0.0.1:7002` | data/control targets | [`scheduler_cli.py`](../../scheduler/scheduler_cli.py), [`core/config.py`](../../core/config.py) |
| Proxy | `PROXY_INSTANCE_STRATEGY`, `PROXY_INJECTION_STRATEGY` | strings; caller/config strategy; injection `default` or `iws` | Instance selection and dynamic injection strategy | Demo validates injection choice. [`demo_proxy.py`](../../test/demo_proxy.py) |
| Proxy | `PROXY_CP_URL`, `SCHEDULER_CP_URL`, `PROXY_ID` | URL/URL/string; `8002`, `7002`, empty | CLI/control registration targets | [`proxy_cli.py`](../../proxy/proxy_cli.py) |
| Proxy UI | `PROXY_UI_LISTEN`, `PROXY_UI_URL` | address/URL; `127.0.0.1:8202`, derived URL | optional UI binding/display address | CLI flags override. [`demo_proxy.py`](../../test/demo_proxy.py) |
| Proxy binding/advertisement | `PROXY_DP_HOST`, `PROXY_DP_PORT`, `PROXY_CP_HOST`, `PROXY_CP_PORT`, `PROXY_ADVERTISE_HOST`, `PROXY_ADVERTISE_PORT` | host/int; `127.0.0.1`, 8001, `127.0.0.1`, 8002, data host/port | binds data/control apps and advertises the Scheduler endpoint | demo host/port sets both data bind and advertisement; control bind reads its own pair. [`proxy.py`](../../proxy/proxy.py), [`demo_proxy.py`](../../test/demo_proxy.py) |
| Proxy registration/heartbeat/capacity | `SCHEDULER_CP_URL`, `PROXY_ID`, `PROXY_HEARTBEAT_S`, `PROXY_MAX_CAPACITY`, `PROXY_INSTANCE_TTL_S` | URL/string/float/int/int; Scheduler 7002, `hp_<advertise-host>:<port>`, 5, 8, 30 | Scheduler registration/heartbeat identity; advertised capacity; Instance liveness TTL | registration response may override heartbeat interval. [`proxy.py`](../../proxy/proxy.py), [`p_control_plane.py`](../../proxy/resource/p_control_plane.py) |
| Proxy pool/cache description | `PROXY_INSTANCE_COUNT`, `PROXY_KV_MEM_PER_INSTANCE_GB`, `PROXY_KV_CACHE_UPDATE_POLICY`, `PROXY_KDN_LINKS_JSON` | int/float/string/JSON; 1, 128, `lru`, empty | reported pool capacity/topology and cache policy metadata | invalid topology JSON falls back through owning parser/log path. [`proxy.py`](../../proxy/proxy.py), [`core/config.py`](../../core/config.py) |
| Proxy queue concurrency/release | `PREPARE_CONCURRENCY`, `READY_CONCURRENCY`, `PROXY_READY_RELEASE_POLICY`, `PROXY_TEXT_BYPASS_MAX_PER_FLUSH` | int/int/choice/int; 8, 8, `ordered`, 1 | per-Instance preparation/ready workers and optional text bypass | invalid release policy logs and falls back to `ordered`; bypass maximum is clamped to at least 1. [`manager.py`](../../proxy/queue/manager.py) |
| Proxy IWS | `PROXY_INJECTION_STRATEGY`, `IWS_KDN_QUEUE_PENALTY_ALPHA`, `IWS_DECISION_MARGIN_MS` | choice/float/int; `default`, 0.5, 100 | enables `iws` and adjusts KDN queue penalty/decision margin | demo accepts only `default|iws`; numeric values are parsed at import. [`proxy.py`](../../proxy/proxy.py), [`demo_proxy.py`](../../test/demo_proxy.py) |
| Instance | `PROXY_CP_URL`, `INSTANCE_TOPOLOGY_KDN_TARGETS` | URL/list; `http://127.0.0.1:8002`, empty | registration/resource report and KDN link discovery | [`demo_instance.py`](../../test/demo_instance.py), [`core/config.py`](../../core/config.py) |
| Instance registration/advertisement | `INSTANCE_ADVERTISE_HOST`, `INSTANCE_ADVERTISE_PORT`, `INSTANCE_PORT`, `INSTANCE_ID`, `INSTANCE_CP_HOST`, `INSTANCE_CP_PORT` | host/int/int/string/host/int; `127.0.0.1`, Instance port 9001, 9001, `hp_<advertise-host>:<port>`, `127.0.0.1`, 9002 | advertises/registers Instance identity and binds its control plane | demo explicitly sets advertise host/port and defaults ID before app import. [`instance_api.py`](../../instance/instance_api.py), [`demo_instance.py`](../../test/demo_instance.py) |
| Instance capability/topology | `INSTANCE_MODEL_ID`, `INSTANCE_TOKENIZER_ID`, `INSTANCE_DEFAULT_LINK_BW_MBPS` | optional strings/float; configured model, model ID, 1000 | capability identity and fallback KDN link bandwidth | missing optional package/model information becomes explicit capability uncertainty. [`capability_builder.py`](../../instance/capability_builder.py), [`instance_api.py`](../../instance/instance_api.py) |
| Instance monitor | `INSTANCE_RESOURCE_MONITOR_ENABLE`, `INSTANCE_RESOURCE_AGENT_LISTEN`, `INSTANCE_RESOURCE_AGENT_URL`, `INSTANCE_RESOURCE_AGENT_SAMPLE_INTERVAL_MS`, `INSTANCE_RESOURCE_AGENT_START_TIMEOUT_S`, `INSTANCE_RESOURCE_REPORT_HZ`, `INSTANCE_RESOURCE_REPORT_TIMEOUT_S` | bool/address/URL/int/float; true, `127.0.0.1:9201`, corresponding URL, 1000, 60, 1, 2 | resource-agent lifecycle and Proxy snapshots | enable/disable CLI pairs override; interval flag can override Hz. [`demo_instance.py`](../../test/demo_instance.py) |
| Instance UI | `INSTANCE_UI_LISTEN`, `INSTANCE_UI_START_TIMEOUT_S`, config `INSTANCE_UI_ENABLE`/`INSTANCE_UI_OPEN_BROWSER` | address/seconds/bools; `0.0.0.0:9202`, 5, false/false | optional dashboard lifecycle | explicit UI flags override. [`demo_instance.py`](../../test/demo_instance.py) |
| KDN storage/model | `KDN_TEXT_DB_DIR`, `KDN_KV_DB_DIR`, `KDN_EMBEDDING_MODEL` | paths/string; component/config fallbacks | database roots and embedding engine | [`kdn_api.py`](../../kdn_server/kdn_api.py) |
| KDN identity/advertisement <!-- kdn-advertise-registration --> | `KDN_ID`, `KDN_ADVERTISE_HOST`, `KDN_ADVERTISE_PORT`, `SCHEDULER_CP_URL` | string/host/int/URL; generated time-based ID, empty/empty, optional Scheduler | registration and advertised endpoint | `kdn_api.py` does not detect advertisement values: missing Scheduler URL or either advertise host/port skips registration. `demo_kdn.py` explicitly supplies configured host/port defaults. Generated ID has no stable public regex. [`kdn_api.py`](../../kdn_server/kdn_api.py), [`demo_kdn.py`](../../test/demo_kdn.py) |
| KDN Redis rewriting | `KDN_REDIS_REWRITE_ENABLE`, `KDN_REWRITE_LOOPBACK_TO`, `KDN_FORCE_REDIS_HOST` | bool/host/host; false/empty/empty | optional address rewriting | disabled preserves original addresses. [`kdn_api.py`](../../kdn_server/kdn_api.py) |
| KDN network simulation <!-- kdn-network-efficiency --> | `KDN_NETWORK_ENABLE`, `KDN_NETWORK_BW_MB_S`, `KDN_NETWORK_BATCH_WINDOW_MS`, `KDN_NETWORK_FIXED_LATENCY_MS`, `KDN_NETWORK_EFFICIENCY` | bool/floats; false, 125, 10, 10, 0.8 | simulated KV transfer scheduling/delay | the demo accepts a float without range rejection; `NetworkSimulator` clamps runtime efficiency to `[0.01, 1.0]`. [`kdn_api.py`](../../kdn_server/kdn_api.py), [`demo_kdn.py`](../../test/demo_kdn.py) |

## Service hosts and ports

| Service/interface | Current default | Owner/source | Effect/notes |
|---|---|---|---|
| Scheduler data plane | `127.0.0.1:7001` | [`core/config.py`](../../core/config.py) | public OpenAI-compatible entry. |
| Scheduler control plane | `127.0.0.1:7002` | [`core/config.py`](../../core/config.py) | Proxy/KDN registration and heartbeats. |
| Proxy data/control | `127.0.0.1:8001` / `127.0.0.1:8002` | [`core/config.py`](../../core/config.py) | forwarding and Instance/resource control. |
| Instance data/control | `127.0.0.1:9001` / `127.0.0.1:9002` | [`core/config.py`](../../core/config.py) | inference forwarding / KV readiness control. |
| KDN | `127.0.0.1:9101` | [`core/config.py`](../../core/config.py) | knowledge and topology APIs. |
| downstream vLLM | `http://127.0.0.1:8000` | [`core/config.py`](../../core/config.py) | OpenAI-compatible engine target. |
| Redis | `127.0.0.1:6379`, DB 0, no password | [`core/config.py`](../../core/config.py) | Legacy KV injection/reuse storage. |
| Resource Agent / Instance dashboard | `127.0.0.1:9201` / `0.0.0.0:9202` | [`core/config.py`](../../core/config.py) | optional monitoring/UI. |
| Proxy UI | `127.0.0.1:8202` | [`demo_proxy.py`](../../test/demo_proxy.py) | enabled by demo default; not a canonical service API. |

## CLI flags

| CLI | Flags, types and defaults | Runtime effect / validation |
|---|---|---|
| Scheduler demo | `--strategy=round_robin`; `--cacheroute`; KDN pending/active/queue thresholds `0`; proxy load delta `0.1`; decision logging `0|1` default 1 | selects routing policy and experiment thresholds. [`demo_scheduler.py`](../../test/demo_scheduler.py) |
| Scheduler CLI | `--base-url=$SCHEDULER_BASE_URL`; `--cp-url=$SCHEDULER_CP_URL` or empty | REPL data/control targets. [`scheduler_cli.py`](../../scheduler/scheduler_cli.py) |
| Proxy demo | `--host/--port` config defaults; `--strategy`; `--kdn-links-json=""`; `--injection-strategy=default|iws`; `--ready-release-policy=ordered|text_bypass`; `--proxy-ui/--no-proxy-ui` (enabled); UI listen/URL | launches Proxy and optional UI; validates choices. [`demo_proxy.py`](../../test/demo_proxy.py) |
| Proxy CLI | CP URL `8002`; Scheduler CP URL `7002`; empty proxy ID; output format choice; `--timeout=5.0` | inspection/control only. [`proxy_cli.py`](../../proxy/proxy_cli.py) |
| Instance demo | `--host/--port`; `--kdn-targets`; monitor/agent/report enable-disable pairs; agent address/URL/sample/start timeout; report Hz/interval/timeout; Proxy CP URL; UI enable-disable/listen/browser/start timeout | launches Instance, optional agent/report/UI. Environment/config supplies documented defaults. [`demo_instance.py`](../../test/demo_instance.py) |
| KDN demo | `--host=127.0.0.1`, `--port=9101`, `--network` false, bandwidth 125 MB/s, window 10 ms, fixed latency 10 ms, efficiency 0.8 | launches KDN and optional network simulation. [`demo_kdn.py`](../../test/demo_kdn.py) |
| Perf client | required mode `concurrent|rps`, base URL, workload file, request count, model; optional concurrency/RPS, duplicate, seed, path `/v1/chat/completions`, stream/RAG `"true"`, injection `text`, hybrid `2:1`, max tokens 1, temperature 0.8, top-p 1.0, knowledge IDs, trace/GPU switches | reproducible load generation; validates mode/choices/pattern. [`perf_client.py`](../../client/perf_client.py) |

## HTTP and debug endpoints

| Owner | Method/path | Request/response purpose | Validation/evidence |
|---|---|---|---|
| Scheduler data | POST `/v1/chat/completions`, `/v1/completions` | OpenAI-compatible payload → Proxy stream/non-stream response | [`scheduler.py`](../../scheduler/scheduler.py), [`test_client_command_input.py`](../../test/test_client_command_input.py) |
| Scheduler debug/admin | GET `/debug/status`, GET `/debug/strategy`, POST `/debug/knowledge/peek`, POST `/admin/refresh_knowledge` | pools/status, policy, selected kid metadata, manual refresh | [`scheduler.py`](../../scheduler/scheduler.py) |
| Scheduler control | GET `/healthz`; POST `/v1/proxy/register`, `/v1/proxy/heartbeat`, `/v1/proxy/unregister`; GET `/v1/proxy/list`; POST `/v1/kdn/register`, `/v1/kdn/heartbeat`, `/v1/kdn/unregister`; GET `/v1/kdn/list`, `/debug/proxy_pool_resources` | resource lifecycle/pool visibility | [`control_plane.py`](../../scheduler/resource/control_plane.py), [`test_contract_service_migration.py`](../../test/test_contract_service_migration.py) |
| Proxy data | POST `/v1/chat/completions`, `/v1/completions` | `Request` dataclass payload → Instance result plus metadata | [`proxy.py`](../../proxy/proxy.py) |
| Proxy control | GET `/healthz`, `/debug/status`, `/debug/pool_resource`, `/debug/pool_resource_sources`, `/debug/instance_resources`, `/debug/instance_loads`; POST `/v1/instance/register`, `/v1/instance/heartbeat`, `/v1/instance/resource_snapshot`, `/v1/instance/unregister`; GET `/v1/instance/list`; POST `/v1/topology/report`; GET `/v1/topology/kdn_links` | Instance/resource/topology lifecycle | [`p_control_plane.py`](../../proxy/resource/p_control_plane.py), [`test_instance_capability_registration.py`](../../test/test_instance_capability_registration.py) |
| Instance data/control | POST `/v1/chat/completions`, `/v1/completions`; GET `/healthz`; POST `/v1/kv/inject_ready` | vLLM forwarding and KV-ready signal | [`instance_api.py`](../../instance/instance_api.py), [`control_plane.py`](../../instance/control_plane.py), [`test_injector_reuse.py`](../../test/test_injector_reuse.py) |
| KDN | POST `/v1/topology/hello`, GET `/v1/topology/ping`; POST `/knowledge/snapshot`, `/knowledge/register_text`, `/knowledge/build_kv`, `/knowledge/search/text`, `/knowledge/delete`, `/knowledge/purge_all`, `/knowledge/inject_ready_kv`, `/knowledge/pool_status` | topology, registration/search/lifecycle/injection/status | [`kdn_api.py`](../../kdn_server/kdn_api.py), [`test/kdn`](../../test/kdn/) |
| Client UI | GET `/ui/client`; POST `/ui/api/parse_curl`, `/ui/api/validate`, `/ui/api/send` | browser client and validation/relay | [`UI/client_ui/app.py`](../../UI/client_ui/app.py) |
| Proxy UI | GET `/`, `/api/config`, `/api/proxy/healthz`, `/api/proxy/status`, `/api/proxy/instances`, `/api/proxy/resources`, `/api/proxy/topology`, `/api/proxy/loads`, `/api/scheduler/proxy` | browser aggregation of control/debug APIs | [`proxy_ui_server.py`](../../UI/proxy_ui/proxy_ui_server.py) |
| TTFT predictor | GET `/`; POST `/predict`, `/report_prefill` | health, prediction, measured-prefill update | [`prefill_prediction_server.py`](../../instance/TTFT_predictor/prefill_prediction_server.py) |

## Request fields

`Request.build_request` is the Scheduler's Current normalization point
([`core/request.py`](../../core/request.py)).

| Input/model field | Type | Current default/validation | Runtime effect / caller differences |
|---|---|---|---|
| `model` | string | required/non-empty | tokenizer/downstream model. |
| `messages` / `prompt` / Legacy `user_prompt` | list / string-or-list / string | one parseable non-empty user prompt required; last user message wins; first completion-list element used | determines `Prompt.user_prompt` and endpoint type. |
| `max_tokens` | integer | **1000** when absent or falsey | `Prompt.max_tokens`; perf caller default is **1**, KDN KV builder default is **1**. |
| `stream` | bool-like | `parse_stream_flag(None)` (false) | streaming behavior; perf caller sends `"true"` by default. |
| `RAG` | bool-like | `parse_stream_flag(None)` (false) | `Service.Enable_know_injection`; perf caller sends `"true"` by default. |
| `Injection_type` | string | `kvcache`; aliases normalized as above | `Service.Injection_type`; perf caller default is text and expands hybrid. |
| `temperature` | number | 1.0; conversion failure or value <=0 →1.0 | sampling; perf caller default 0.8. |
| `top_p` | number | 1.0; conversion failure or outside `(0,1]` →1.0 | sampling; perf caller default 1.0. |
| `Request_type` | string | `request` | compatibility task kind. |
| derived `Prompt` | dataclass | model, user prompt, estimated token length, batch size 1, normalized sampling/stream fields | Scheduler-to-Proxy serialization. |
| derived `Service` | dataclass | RAG/injection above; compression true/0.3; security false; configured knowledge top-k; empty list/length 0; user-address SLO mapping | strategy and knowledge execution metadata. |
| derived `Task` / `Request_ID` | dataclass / integer | selected KDN/Proxy/Instance fields; Scheduler-assigned integer | routing and traceability; no source-defined universal regex. |

OpenAI-compatible response bodies are forwarded from vLLM for streaming or
non-streaming paths. CacheRoute adds metadata rather than redefining the engine's
complete response schema.

## SSE metadata

| Event/field | Type/default | Owner/effect | Compatibility/evidence |
|---|---|---|---|
| event `cacheroute_meta` | SSE event before delayed `[DONE]` | Proxy emits task summary after downstream chunks | [`proxy.py`](../../proxy/proxy.py), clients tolerate ordinary `data:` chunks. |
| `trace` | object/dict | timestamps, prediction/actual path and cost fields | unversioned operational metadata, not canonical observability v1. [`perf_client.py`](../../client/perf_client.py) |
| `kv_ack` | object/value | KV injection acknowledgement | may be absent/empty on text or failed paths. |
| `kv_ready_kids`, `text_only_kids`, `miss_kids` | lists | per-task knowledge resolution result | kid format remains current KnowledgeTable/KDN-owned, not inferred here. |
| `error` <!-- cacheroute-meta-error --> | nullable unversioned operational string | task-level failure detail that may expose implementation detail | not a safe/versioned payload and not `ContractErrorDetail`. |
| common emitted trace fields <!-- cacheroute-meta-no-request-id --> | numbers/strings when produced | `injection_mode`, predicted/actual timing, queue/prepare/forward/first-token markers, `text_actual_path`, `kvcache_actual_path` | `ProxyTask.request_id` exists internally but `build_cacheroute_meta` does not currently emit `request_id`; clients calculate metrics only when keys exist and report missing/order warnings. [`task.py`](../../proxy/queue/task.py), [`proxy.py`](../../proxy/proxy.py), [`client.py`](../../client/client.py), [`perf_client.py`](../../client/perf_client.py) |

## Feature switches and packaging/runtime options

| Surface | Default/allowed | Effect / evidence |
|---|---|---|
| Scheduler strategy/thresholds | round robin; CacheRoute thresholds mostly 0 (disabled), decision log 1 | experiment routing/observability. [`core/config.py`](../../core/config.py) |
| Proxy ready release | launcher choice `ordered|text_bypass` | queue release experiment; not canonical routing API. |
| Mock Instance | `USE_MOCK=False` | local response substitution. [`core/config.py`](../../core/config.py) |
| Resource monitor/UI/network simulation/Redis rewrite | documented above; backward-compatible disabled/enabled defaults | optional experiment/runtime features. |
| Python/package | Python `>=3.10`; explicit setuptools `packages`; no automatic discovery; declared package data | builds transitional wheel; docs/tests/env/scripts/log excluded. [`pyproject.toml`](../../pyproject.toml), [`test_wheel_install.py`](../../test/test_wheel_install.py) |
| Network validation | pytest marker `network`; opt-in `CACHEROUTE_RUN_NETWORK_TESTS=1` | dependency-install test; `-m "not network"` deselects it. |

Detailed operational authorities remain the [Scheduler](../../scheduler/README.md),
[Proxy](../../proxy/README.md), [Instance](../../instance/README.md),
[KDN](../../kdn_server/README.md), [Client](../../client/README.md), and
[environment](../../env/README.md) guides.
