# Runtime flows

[Back to handbook](README.md). “Current” below means production/demo wiring is
present, not merely that a model exists.

## Client → Scheduler → Proxy → Instance → vLLM

| Boundary | Current types, IDs and entrypoint | Observable output | Failure/fallback and evidence |
|---|---|---|---|
| Client → Scheduler | OpenAI payload (`model`, chat `messages` or completion `prompt`, sampling/RAG/injection fields) to POST `/v1/chat/completions` or `/v1/completions` on `scheduler.scheduler:scheduler`; Scheduler assigns integer `Request_ID` | HTTP status, streamed content, client summaries | parsing/HTTP failures surface to client. [`client/client.py`](../../client/client.py), [`test_client_command_input.py`](../../test/test_client_command_input.py) |
| Scheduler construction/selection | [`Request`, `Prompt`, `Service`, `Task`](../../core/request.py); selected KDN address and Proxy ID/address/port from maintained pools | request-build and decision logs; `/debug/status`, `/debug/strategy`, knowledge peek | missing model/prompt or no routable KDN/Proxy fails before forwarding. [`scheduler/scheduler.py`](../../scheduler/scheduler.py); demo launcher [`demo_scheduler.py`](../../test/demo_scheduler.py) |
| Scheduler → Proxy | serialized `Request` dataclasses to matching Proxy POST endpoint | Scheduler forward timing/status; Proxy receive/route trace | transport/Proxy errors propagate; no canonical contract v1 envelope is wired here. [`proxy/proxy.py`](../../proxy/proxy.py) |
| Proxy queue → Instance | `ProxyTask`, root queue manager, chosen Instance ID/capability; POST matching Instance endpoint | queue/prepare/prediction/actual trace, task logs, control-plane resource views | no healthy Instance, queue/prepare, knowledge or forwarding failures recorded on task. [`proxy/queue/manager.py`](../../proxy/queue/manager.py), [`test_instance_capability_registration.py`](../../test/test_instance_capability_registration.py) |
| Instance → vLLM | normalized OpenAI body through `instance.instance_api:instance` to configured vLLM base URL | downstream body/SSE, Instance logs/capability and resource reports | downstream HTTP/stream failure propagates; mock behavior only when explicitly enabled. [`instance/instance_api.py`](../../instance/instance_api.py), [`test_instance_capability.py`](../../test/test_instance_capability.py) |

Known limitations: these root service dataclasses are Transitional rather than
versioned cross-process contracts; there is no unified `cacheroute` entrypoint or
migrated `cacheroute.services.*` implementation.

## Scheduler/KDN selection and knowledge lifecycle

The actual Current in-process owner of `KnowledgeTable`, `KnowledgeUnit`, kid
normalization/mapping, upsert/delete, FAISS construction and search is
[`store/knowledge_base.py`](../../store/knowledge_base.py). KDN persistence and
registration live under [`kdn_server`](../../kdn_server/); Scheduler metadata
synchronization and selection use [`scheduler/knowledge/kdn_sync.py`](../../scheduler/knowledge/kdn_sync.py)
and maintained KDN pools. A `kid` supplied to `KnowledgeTable.upsert_kid` is
trimmed/lowercased and mapped to an internal signed-64-bit FAISS ID; source does
not declare one universal public kid regex.

| Flow | Types/IDs/endpoints | Outputs/failures | Evidence/limitations |
|---|---|---|---|
| Register text | KDN POST `/knowledge/register_text`; KDN request record and kid | stored metadata, registration/status response | registration does not prove embedding/KV readiness. [`kdn_api.py`](../../kdn_server/kdn_api.py), KDN demos/tests under [`test/kdn`](../../test/kdn/) |
| Build/inject KV | POST `/knowledge/build_kv`, then `/knowledge/inject_ready_kv`; current Legacy Redis/KV database types | KV directory/key counts, ack/readiness, network timing | build/storage/network failures remain distinct; text fallback is Proxy-owned. [`kdn_api.py`](../../kdn_server/kdn_api.py) |
| Snapshot/search/status | POST `/knowledge/snapshot`, `/knowledge/search/text`, `/knowledge/pool_status`; kid lists and resource fields | `kv_ready`, metadata/resource snapshots and search hits | snapshots can be stale; Scheduler refresh can fail independently. [`kdn_sync.py`](../../scheduler/knowledge/kdn_sync.py) |
| Scheduler retrieval | `Service.knowledge_retriever`, `KnowledgeTable`, `KnowledgeUnit`; selected `Knowledge_List` and length | selected kid list and retrieval log | empty/weak/no embedding results yield no knowledge. [`core/request.py`](../../core/request.py), [`store/knowledge_base.py`](../../store/knowledge_base.py) |

[`test/test_kb_kid.py`](../../test/test_kb_kid.py) is a manual `main()` smoke/demo,
not a collected pytest proof. Canonical `KnowledgeDescriptor` and v1 requests
are Current model APIs, but their definitions are not evidence that root
registration handlers use them end-to-end.

## Text, KVCache and hybrid compatibility paths

`Request.build_request` normalizes missing/invalid injection to `kvcache`, while
the perf client defaults to text. `hybrid` exists in workload tooling and is
resolved by the configured KV:text ratio into an actual `text` or `kvcache`
request; it is not forwarded as a third Instance primitive.

| Path | Current types/IDs/entrypoints | Outputs and fallback | Evidence/limitations |
|---|---|---|---|
| Text | `Request.Service.Injection_type="text"`, `Knowledge_List`, Proxy queue body injection, same inference endpoints | `text_actual_path`, context-build/fetch timing, recomputed prefill | missing knowledge can proceed without injected context; no cache reuse. [`proxy/queue/knowledge.py`](../../proxy/queue/knowledge.py), [`perf_client.py`](../../client/perf_client.py) |
| KVCache | injection `kvcache`, kid readiness, KDN inject-ready endpoint and Instance `/v1/kv/inject_ready` | `kv_ack`, ready/text-only/miss kids, `kvcache_actual_path`, transfer/load timing | unavailable KV or injection failure explicitly falls back to text (`no_kv_ready_fallback_text` or `kv_inject_failed_fallback_text`). [`proxy/queue/manager.py`](../../proxy/queue/manager.py), [`test_injector_reuse.py`](../../test/test_injector_reuse.py), [`test_kv_injector_reuse.py`](../../test/test_kv_injector_reuse.py) |
| Hybrid workload | perf request index and `--hybrid-pattern` | per-request actual injection printed in summaries | client-side only; no production policy contract. [`perf_client.py`](../../client/perf_client.py) |

## Logical cache operations and Instance capabilities

`CacheArtifact`, `CacheReplicaObservation`, `CacheOperationTask`, and
`QueueWork` are Current dependency-light models with `artifact_`, `endpoint_`,
`cacheop_`, and `queuework_` IDs described in the [API catalog](public-api-and-data-models.md).
They validate logical identity/provenance/lifecycle but are **not** production
Cache Service wiring and perform no LMCache/Redis work.

Instance capability construction is Current in
[`instance/capability_builder.py`](../../instance/capability_builder.py); the
Instance registers its capability with the Proxy control plane, which exposes
Instance list/resource/load endpoints. Missing package metadata/capability or
registration/heartbeat failures are reported at this boundary. Focused proof:
[`test_instance_capability.py`](../../test/test_instance_capability.py) and
[`test_instance_capability_registration.py`](../../test/test_instance_capability_registration.py).
Canonical runtime connector discovery under `cacheroute.integrations.vllm` is
Target / Accepted and unimplemented.

## Current metadata observability and PR #179

Production currently emits component logs, unversioned per-task `trace`
dictionaries, the SSE `cacheroute_meta` event (`trace`, `kv_ack`,
`kv_ready_kids`, `text_only_kids`, `miss_kids`, `error`), client timing summaries,
and debug/resource endpoints. Missing trace keys cause client warnings rather
than contract validation. See [`proxy/proxy.py`](../../proxy/proxy.py) and
[`client/perf_client.py`](../../client/perf_client.py).

PR #179 is still **In review** on this baseline. It proposes observability v1
contracts, clocks, a process-local collector, and Legacy projection. It does
**not** implement production instrumentation or cross-process propagation.
`cacheroute.observability` is Current only as an empty namespace; no proposed v1
model should be described as wired behavior.

Legacy runtime/Redis compatibility remains explicit. A canonical Legacy cache
projection, where used directly, is read-only, low-confidence and generation
zero; defining that projection does not wire it into production. Backend and
network failures must not be reported as successful observations or cache
operations. See [compatibility and migrations](compatibility-and-migrations.md).
