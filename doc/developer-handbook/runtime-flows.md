# Runtime flows

[Back to handbook](README.md). These are implementation flows, not merely model
availability. Component details remain in their linked READMEs.

## Client → Scheduler → Proxy → Instance → vLLM

The Client builds an OpenAI-compatible request (`client/client.py` and
`client/perf_client.py`) and sends chat/completion work to the Scheduler
([`scheduler/scheduler.py`](../../scheduler/scheduler.py)). The Scheduler parses
`core.request.Request`, selects maintained Proxy/KDN pool resources, and forwards
to the Proxy. The Proxy ([`proxy/proxy.py`](../../proxy/proxy.py)) selects an
Instance, queues/prepares knowledge work, and the Instance
([`instance/instance_api.py`](../../instance/instance_api.py)) forwards to vLLM.
Streaming responses carry SSE data and timing metadata consumed by the clients.
Observable boundaries include HTTP status, task-level logs, trace dictionaries,
resource endpoints, and client summaries. Network, registration, missing
resources, injection, and downstream vLLM failures are distinct boundaries.
See [Client](../../client/README.md), [Scheduler](../../scheduler/README.md),
[Proxy](../../proxy/README.md), and [Instance](../../instance/README.md).

Focused evidence: [`test_client_command_input.py`](../../test/test_client_command_input.py),
[`test_instance_capability_registration.py`](../../test/test_instance_capability_registration.py),
and transitional launchers in [`test/README.md`](../../test/README.md).

## Scheduler and KDN; registration and lookup

KDN registration is handled by [`kdn_server/kdn_api.py`](../../kdn_server/kdn_api.py)
and its text/KV databases. Knowledge uses the existing `kid` convention owned by
[`core/kb.py`](../../core/request.py); the Scheduler synchronizes KDN state in
[`scheduler/knowledge/kdn_sync.py`](../../scheduler/knowledge/kdn_sync.py) and
selects from maintained pools. Registration does not imply every derived KV or
embedding state is ready. Status, `kv_ready`, directory/key counts, and KDN
resource responses are operational observations. See the
[KDN guide](../../kdn_server/README.md) and [`test_kb_kid.py`](../../test/test_kb_kid.py).

Canonical v1 knowledge/cache contract models are **Current**, but their presence
alone does not mean every root service path uses a new facade implementation.

## Injection paths

`Injection_type` remains the compatibility wire spelling. Current request paths
support `text` and `kvcache`; performance tooling accepts `hybrid` and resolves a
ratio pattern into per-request `text`/`kvcache` work before sending. Text work
adds retrieved context for recomputation. KVCache work prepares/restores the
knowledge cache and can fall back to text when cache readiness or injection
fails; trace values record the actual path. The current Proxy queue logic is in
[`proxy/queue/manager.py`](../../proxy/queue/manager.py), knowledge body shaping
in [`proxy/queue/knowledge.py`](../../proxy/queue/knowledge.py), and ratio parsing
in [`client/perf_client.py`](../../client/perf_client.py). “Hybrid” is not a
third Instance injection primitive.

## Logical cache operations and capability registration

`CacheArtifact`, `CacheReplicaObservation`, and `CacheOperationTask` describe
logical state and validated transitions ([cache models](../../src/cacheroute/cache/models.py)).
They do not themselves execute LMCache or Redis work. Root KDN gateways retain
Legacy physical operations. Instance capability construction and Proxy
registration are current operational behavior in [`instance/instance_api.py`](../../instance/instance_api.py)
and [`proxy/proxy.py`](../../proxy/proxy.py), proven by
[`test_instance_capability.py`](../../test/test_instance_capability.py) and
[`test_instance_capability_registration.py`](../../test/test_instance_capability_registration.py).

## Observability and Legacy boundaries

Current observability consists of component logs, timing/trace dictionaries,
SSE metadata, client summaries, resource/debug endpoints, and optional UIs. The
canonical `cacheroute.observability` namespace exports nothing. Cross-process
observability v1 and propagation in PR #179 are **In review**, not Current.
Fields labelled predicted/desired/observed/measured/actual/inferred must retain
the semantics in the [glossary](glossary.md).

Legacy Runtime Profile and Redis key layouts remain explicit adapters. Canonical
read-only Legacy projections use low confidence and unknown endpoint generation
zero; they do not create authoritative LMCache state. Failures may choose an
explicit text fallback but must not silently claim cache success. See the
[compatibility map](compatibility-and-migrations.md).
