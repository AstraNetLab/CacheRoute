# Issue #141 research: unified v1 LMCache observability

Status: design proposal only<br>
Baseline audited: `ad087d1` (current `main` lineage, including merged PR #154)<br>
Lifecycle: temporary design record for Issue #141. Remove this file after the Issue is completed and its stable content has been moved into maintained package and component documentation.

Non-goals: production instrumentation, Gateway I/O, routing/queue changes, or a tracing backend.

## 1. Executive decision record

1. Put the dependency-light contracts in **`cacheroute_observability/`**. Scheduler,
   Proxy, KDN, Gateway, and Instance can import this standalone package without
   loading `core` or another component; placing it under `kdn_server` would invert
   dependencies for Scheduler/Proxy/Instance.
2. Make an exported trace an immutable, versioned snapshot. Build it by appending
   immutable stages/measurements to a process-local collector; never mutate a
   measurement from `predicted` into `actual`.
3. Use UTC timestamps for correlation and per-process monotonic nanoseconds for
   durations. Never subtract monotonic readings produced by different processes.
4. Propagate a small internal trace envelope alongside the current serialized
   `Request`, stripping it before the OpenAI/vLLM body. During migration, retain
   `Request_ID`, `scheduler-request-id`, the free-form `ProxyTask.trace`, and
   `cacheroute_meta` unchanged.
5. Treat Prometheus before/after deltas as endpoint aggregates. Only an isolated,
   single-request validation run may label them `inferred`; concurrent deltas are
   never request-correlated actuals.

## 2. Current path and identity inventory

```text
client payload
  -> Scheduler allocates cyclic integer Request_ID (1..65535)
     -> serialized core.request.Request + scheduler-request-id HTTP header
        -> Proxy restores Request_ID; ProxyTask.request_id duplicates it
           -> OpenAI-style instance_body (identity is dropped)
              -> Instance forwards the body unchanged (identity remains absent)
                 -> vLLM/LMCache

Proxy prepare path
  -> KDN text lookup (no trace/correlation envelope)
  -> Instance /v1/kv/inject_ready {request_id, ...}
     -> KDN /knowledge/inject_ready_kv {request_id, ...}

Versioned KDN/Gateway contracts (currently separate from serving path)
  -> string request_id (default req_<uuid>) + optional correlation_id
  -> runtime_profile + created_at
  -> targeted calls add compatibility_profile_id, endpoint_id, generation
  -> Gateway responses preserve those fields
```

### Existing correlation fields

| Field | Location/semantics | Finding |
|---|---|---|
| `Request.Request_ID` | Scheduler-assigned cyclic `int` | Not globally unique; reuse after 65,535 and across Scheduler processes/restarts. |
| `ProxyTask.request_id` | Optional `int`, copied from `Request_ID` | Useful local alias, but annotation conflicts with KDN v1 string IDs. |
| `scheduler-request-id` | Scheduler-to-Proxy HTTP header | Redundant with payload; not forwarded beyond Proxy. |
| KDN v1 `request_id` | `VersionedMessage`, non-empty string, defaults `req_<uuid>` | Strong message identity, but the production serving path does not use these contracts yet. |
| KDN v1 `correlation_id` | Optional string | Correct place to retain an end-to-end correlation, but currently absent from `core.Request`. |
| Cache operation `task_id` | `cacheop_<uuid>` | Operation identity, not a request identity. |
| `idempotency_key` | Cache operation and queue work | Logical deduplication identity; must not be overloaded as trace correlation. |
| artifact/observation/endpoint/work IDs | Canonical or UUID-backed domain IDs | Resource identity only. |

`TraceContext` should therefore carry both an opaque globally unique `request_id`
and a `correlation_id`; the legacy Scheduler integer belongs in
`legacy_request_id`. A generated trace ID must not replace either.

### Current `cacheroute_meta`

Both streaming and non-streaming Proxy responses expose exactly: `request_id`,
the entire mutable `trace` dictionary, `kv_ack`, `kv_ready_kids`,
`text_only_kids`, `miss_kids`, and `error`. Streaming inserts an
`event: cacheroute_meta` immediately before `[DONE]`; completions add
`_cacheroute_meta` to parsed JSON (or the raw-response wrapper). This behavior is
a compatibility contract for the rollout.

## 3. Complete `ProxyTask.trace` audit and classification

Kinds below mean: **P** predicted, **O** observed snapshot/event, **A** actual
duration measured at the named boundary, **I** inferred/derived, **L**
legacy-projected compatibility, and **X** ambiguous or incorrectly named.
All `*_ms` timestamps are wall-clock epoch milliseconds today unless explicitly
described as durations.

### Wall-clock event markers

| Keys | Kind | Meaning / issue |
|---|---|---|
| `proxy_recv_ms`, `route_select_start_ms`, `route_select_end_ms` | O | Proxy receipt and local selection events. |
| `proxy_enqueue_ms`, `prepare_queue_enqueue_ms`, `prepare_dequeue_ms`, `prepare_start_ms` | O | Prepare queue lifecycle; first two currently receive the same reading. |
| `kdn_fetch_start_ms`, `kdn_fetch_end_ms` | O | Proxy-observed KDN fetch boundary. |
| `text_prefill_build_start_ms`, `text_prefill_build_end_ms`, `prompt_injected_ms` | O | Local body construction/injection markers; “prefill” is a misnomer because no vLLM prefill occurs here. |
| `kdn_link_wait_start_ms`, `kdn_link_wait_end_ms` | X | Wall-clock reservation model points, not necessarily observed wait start/end; `end` can be a predicted future time. |
| `kv_inject_queue_enqueue_ms`, `kv_inject_reserved_start_ms` | X | Queue marker plus predicted reservation time; names do not disclose differing value kinds. |
| `kv_inject_start_ms`, `kv_inject_end_ms`, `kv_ack_start_ms`, `kv_ack_end_ms` | O | Proxy/Instance-control-call boundary; injection completion is inferred from the acknowledgement, not LMCache consumption. |
| `prepare_self_done_ms`, `ready_enqueue_ms`, `ready_dequeue_ms` | O | Prepare completion/buffer release/ready dequeue. |
| `forward_wait_start_ms`, `forward_wait_end_ms`, `forward_start_ms`, `forward_end_ms` | O | Dispatch wait and Proxy-to-Instance response boundary. |
| `first_token_ms` | X | First non-empty downstream chunk, which may be SSE metadata rather than a decoded token. |
| `decode_start_ms`, `decode_end_ms` | X | Locally inferred state transition and forward end; neither directly measures vLLM decode. |
| `prepare_error_ms`, `ready_failed_before_forward_ms`, `stream_exception_ms` | O | Failure event timestamps. |
| `pred_forward_start_ts_ms`, `pred_first_token_ts_ms`, `pred_forward_end_ts_ms`, `pred_worker_free_ts_ms` | P | Predicted epoch times. They must remain predictions even after recomputation. |
| `kdn_link_free_before`, `kdn_link_free_after` | X | Predicted/shared model wall-clock values; units are hidden and “free” is not an observation of the remote link. |

### Durations, counts, decisions, and outcomes

| Keys | Kind | Meaning / issue |
|---|---|---|
| `predict_text_prefill_ms`, `predict_redis_kv_load_ms`, `predict_residual_prefill_ms` | P | Model estimates, not runtime measurements. |
| `predict_prepare_initial_ms`, `predict_prepare_queue_wait_ms`, `predict_kv_transfer_ms`, `predict_prepare_prefix_ms`, `predict_kv_prepare_service_ms`, `predict_prepare_model_ms`, `predict_prepare_corrected_ms` | P | Evolving prepare estimates. “corrected” is derived after completion and is no longer a prediction. |
| `predict_know_prepare_ms`, `predict_prepare_ms` | **X** | Initially predicted, then overwritten with wall-clock-derived actual prepare duration at ready release/success. This is the clearest kind violation. |
| `predict_queue_wait_ms`, `predict_compute_ms`, `predict_prefill_service_ms`, `predict_vllm_internal_ms`, `predict_decode_ms`, `predict_cold_start_extra_ms`, `predict_total_ms`, `predict_wait_ms` | P | Reservation/model outputs; `predict_wait_ms` is a legacy alias for knowledge preparation, not queue wait. |
| `predict_error_ms` | I | Signed residual `actual_total_ms - predict_total_ms`, not a prediction. |
| `actual_prepare_ms`, `actual_prepare_total_ms`, `prepare_buffer_wait_ms` | A | Wall-clock-derived local/control-call durations; susceptible to wall-clock adjustment. “prepare” has call-only and end-to-end meanings. |
| `actual_total_ms`, `actual_know_prepare_ms`, `actual_ready_queue_ms`, `actual_vllm_internal_ms` | A | Wall-clock-derived Proxy-observed durations to first non-empty chunk. `actual_vllm_internal_ms` includes network, Instance, vLLM queue, and prefill. |
| `actual_compute_ms` | L | Alias of `actual_vllm_internal_ms`; it is not compute-only. |
| `prepare_seq`, `ready_release_seq`, `ready_worker_idx`, `prepared_buffer_size`, `recompute_generation` (task field) | O | Local ordering/state observations. `recompute_generation` is not exported in `trace`. |
| `ready_release_blocked_seq` | O | Optional observed sequence; dictionary annotation does not allow `None`. |
| `ready_release_bypass`, `kv_link_reserved`, `ttft_observable` | O | Integer booleans. Typed v1 should serialize booleans. |
| `predict_length_tokens`, `predict_bs`, `predict_total_tokens`, `predict_reused_tokens`, `predict_residual_tokens` | P | Inputs/outputs of the model; token reuse is predicted rather than observed. |
| `predict_kv_bandwidth_mbps` | P/I | Link-snapshot/env/default input used by prediction; provenance determines whether observed or inferred. |
| `predict_kv_bandwidth_source` | P | Provenance string; violates `Dict[str, int]`. |
| `predict_stage` | P | Free-form reservation phase (`prefill`/`decode`), not an observed execution stage. |
| `injection_mode` | O | Chosen request mode, not proof that KV was used. |
| `text_actual_path` | X | Free-form outcome (`text_inject`, `no_rag_or_empty_knowledge`). |
| `kvcache_actual_path` | X | Free-form outcome (`kv_inject`, `kv_inject_failed_fallback_text`, `no_kv_ready_fallback_text`). It combines attempted path, failure, and fallback. |
| `ready_release_policy` | O | Policy label, violates `Dict[str, int]`; contextual attribute rather than measurement. |
| `prepare_failed_injection_mode` | O | Mode at failure, violates dictionary annotation. |
| `first_token_missing_reason` | X | Free-form outcome string, violates dictionary annotation. |

The declared `trace: Dict[str, int]` is incorrect: current values include floats
(`predict_kv_bandwidth_mbps`), strings, `None`, and integer booleans. `mark()`
also forces arbitrary values to `int`, although most call sites bypass it.

### Separately stored ProxyTask prediction/state fields

`predict_stage`, `pred_slot_idx`, `pred_slot_ready_ts_ms`,
`pred_forward_start_ts_ms`, `pred_prefill_start_ts_ms`,
`pred_first_token_ts_ms`, `pred_decode_ms`, `pred_forward_end_ts_ms`,
`pred_worker_free_ts_ms`, and `pred_service_ms` are prediction state outside the
dictionary. `reservation_seq` and `recompute_generation` order reservation
updates; `has_started_forward` and `has_seen_first_token` are observed local
booleans. Several values are copied into `trace`, producing two mutable sources
of truth. `created_at` is a wall-clock float and is not currently exported.

### Knowledge, injection, failure, and completion markers outside `trace`

* `kv_ready_kids`, `text_only_kids`, and `miss_kids` are KDN-result
  classifications, not proof of cache consumption.
* `kv_ready_meta` holds untyped KDN metadata and is not in `cacheroute_meta`.
* `kv_ack` exposes the Instance/KDN acknowledgement, including current
  `payload_bytes`, `network_queue_ms`, `network_transfer_ms`, and
  `network_total_ms` when supplied. Their producer clock/boundary is not encoded.
* `error` is a free-form `prepare_failed: ...`, `ready_failed: ...`, or
  `stream_wrap_failed: ...` string. Exceptions can leak implementation detail.
* There is no direct vLLM prefill-start/end, decoded-token event, LMCache
  load-start/end, or server completion event. Proxy `forward_end_ms` is response
  consumption completion; non-streaming `first_token_ms` is only first body
  chunk and explicitly sets `ttft_observable=0`.

## 4. Other current metrics and attribution

Proxy metrics are predictors rather than per-request telemetry:
`queue_predictor`/TTFT regressors estimate prefill time,
`decode_tpot_predictor` estimates decode service, and the Redis regressor
estimates pull time. Queue snapshots report aggregate instantaneous queue/active
counts plus reservation-derived backlog. Instance registration reports a frozen
capability object (model/tokenizer/adapters/KV layout/parallelism and detected
vLLM/LMCache versions), while heartbeats usually send only its fingerprint.
Topology reporting contains endpoint-level measured/inferred latency and link
bandwidth. None is a request-correlated execution measurement.

### Validator metric-attribution table

The validator sums every Prometheus series with each metric name, losing label
dimensions, then subtracts before from after. Classification assumes the current
unlabelled request path.

| Metric | Request actual | Endpoint aggregate | Isolated-test inference | Concurrent attribution |
|---|---:|---:|---:|---:|
| `vllm:external_prefix_cache_queries_total` | No | Yes | Yes: query occurred | Unsupported |
| `vllm:external_prefix_cache_hits_total` | No | Yes | Yes: some external hit occurred | Unsupported |
| `vllm:prompt_tokens_cached_total` | No | Yes | Yes: cached-token delta | Unsupported |
| `vllm:prompt_tokens_total` | No | Yes | Yes: prompt-token delta | Unsupported |
| `lmcache_mp_lookup_requested_tokens_total` | No | Yes | Yes: requested tokens | Unsupported |
| `lmcache_mp_lookup_hit_tokens_total` | No | Yes | Yes: hit tokens/rate | Unsupported |
| `lmcache_mp_l2_prefetch_lookup_requests_total` | No | Yes | Yes | Unsupported |
| `lmcache_mp_l2_prefetch_lookup_objects_chunks_total` | No | Yes | Yes | Unsupported |
| `lmcache_mp_l2_prefetch_hit_chunks_total` | No | Yes | Yes | Unsupported |
| `lmcache_mp_l2_prefetch_load_submitted_requests_total` | No | Yes | Yes | Unsupported |
| `lmcache_mp_l2_prefetch_load_submitted_objects_chunks_total` | No | Yes | Yes | Unsupported |
| `lmcache_mp_l2_prefetch_load_completed_chunks_total` | No | Yes | Yes | Unsupported |
| `lmcache_mp_l2_load_completed_requests_total` | No | Yes | Yes | Unsupported |
| `lmcache_mp_l2_prefetch_failure_chunks_total` | No | Yes | Yes: absence/presence of failures | Unsupported |
| `lmcache_mp_l1_read_chunks_total` | No | Yes | Yes | Unsupported |
| `lmcache_mp_l1_write_chunks_total` | No | Yes | Yes | Unsupported |

Even in an isolated test, record `value_kind=inferred`, the before/after scrape
times, endpoint, full label set (if retained), and the exclusivity assumption.
Counter reset, delayed emission, background work, and scrape races can invalidate
the inference. Future public LMCache events or request-labelled metrics can be
ingested through a small optional observer adapter and emitted as `observed` or
`actual` only when the upstream event specifies the request/operation identity
and measurement boundary. The core schema must not import or depend on a private
LMCache API.

## 5. Where context is lost

1. Client-to-Scheduler has no canonical correlation ID or trace controls.
2. The Scheduler integer ID is cyclic and process-local; it has no boot/session
   namespace.
3. Proxy reconstructs `Request` but does not receive a typed trace context;
   route-selection time begins only at Proxy receipt.
4. `build_body_for_instance()` intentionally produces an OpenAI body and drops
   `Request_ID`; Proxy-to-Instance forwarding sends no trace headers.
5. Instance forwards the same body to vLLM, so it cannot correlate vLLM/LMCache
   observation with the Scheduler request.
6. Text lookup calls do not propagate identity. KV injection propagates only the
   legacy integer `request_id`, with no operation/trace/correlation ID.
7. Gateway v1 contracts have good request/correlation/target provenance but are
   not connected to the production serving path.
8. Streaming byte forwarding identifies the first non-empty chunk, not the first
   decoded token, and does not parse upstream IDs/events.
9. `cacheroute_meta` is assembled only at Proxy response export; stages from
   Scheduler, KDN, Instance, vLLM, and LMCache cannot currently join it.

## 6. Package-boundary evaluation

| Candidate | Benefits | Problems | Decision |
|---|---|---|---|
| `kdn_server/observability/` | Close to #139/#140 types | Forces Proxy, Scheduler, Instance, and `core` to depend on a server package; likely dependency inversion and future import cycles. | Reject. |
| `cacheroute_observability/` | Standalone dependency-light boundary; simple imports; same repository/version | Must enforce that it imports only the standard library and Pydantic. | **Implemented.** |
| separately released distribution | Strong release isolation | Independent packaging/versioning overhead is unnecessary in Phase 1. | Revisit only if contracts need an independent release cycle. |

`cacheroute_observability/` imports only Python stdlib and Pydantic. It defines
trace-only enums and uses validated opaque resource IDs instead of importing or
duplicating #139 domain payloads, #140 contracts, or Gateway implementations. It
must never import FastAPI, Redis, vLLM, LMCache, GPU libraries, `httpx`, network
clients, application components, configuration, or forwarding modules.

## 7. Stable v1 schemas

All models use Pydantic `ConfigDict(frozen=True, extra="forbid")`, stable
`schema_version="cacheroute.trace.v1"`, JSON-mode ISO-8601 UTC timestamps, enum
wire values, arrays (not sets), and deterministic ordering. Export returns a new
frozen snapshot; collection is append-only and process-local. Unknown future
enum values require a version change rather than silently accepting route names.

### `TraceContext`

Required: `trace_id` (`trace_<32 lowercase hex>`), opaque non-empty `request_id`,
opaque non-empty `correlation_id`, `sampled: bool`, and `created_at` UTC. Optional:
`parent_trace_id`, `legacy_request_id: int`, and `expires_at` UTC. `request_id`
identifies one end-user generation request; `correlation_id` groups retries or
related requests; `trace_id` identifies one exported timeline. Validate expiry
after creation. Context contains no prompt, token content, credentials, Redis
keys, physical KV bytes/pointers/paths, or arbitrary baggage.

### `TraceStageName`

Stable values, ordered by a separate integer rank (not enum declaration order):

```text
runtime_profile_resolution
knowledge_lookup
semantic_resolution
artifact_compatibility
capability_snapshot_discovery
token_lookup
artifact_lookup
cache_observation
cache_operation_queue
cache_prefetch_execution
cache_pin_execution
cache_unpin_execution
cache_clear_execution
cache_rebuild_execution
gateway_request
gateway_async_operation
tier_adapter_observation
instance_lmcache_load
proxy_prepare_queue
proxy_ready_queue
vllm_prefill
first_token
decode
completion
fallback
legacy_scan
legacy_dump
legacy_restore
legacy_inject
```

Queue operation is generic and carries `operation` from existing
`CacheOperationType`; execution stages are explicit because they have materially
different safety/latency semantics. Do not add `/route` strings, Python method
names, Redis calls, or LMCache private event names as stage values.

### `TraceValueKind`

Stable values: `predicted`, `observed`, `actual`, `inferred`,
`legacy_projected`. “Ambiguous” is an audit classification, not a valid new
measurement kind; adapters must choose a truthful kind or omit the measurement.

### `TraceStageOutcome`

Stable values: `pending`, `running`, `succeeded`, `failed`, `cancelled`,
`unsupported`, `stale`, `partial`, `skipped`, `fallback`. Map #140 outcomes
directly: `success -> succeeded`, all identical values remain identical,
`incompatible` is represented as `failed` with `outcome_code="incompatible"`,
`text_fallback -> fallback`, and `idempotency_conflict -> failed`. Maintainer
approval is needed on whether to add `incompatible` and `idempotency_conflict`
directly instead of keeping the #140 code alongside the stage outcome.

### `TraceProvenance`

Required: `source_component` (`client|scheduler|proxy|kdn|gateway|instance|vllm|lmcache|legacy_adapter|test`),
`runtime_profile`, and `captured_at` UTC. Optional: `source_endpoint` (logical
endpoint/route label, never credentials or URL query), `endpoint_id`,
`endpoint_generation`, `gateway_profile`, `compatibility_profile_id`,
`observation_source`, `profile_id`, `adapter`, `tier`, `source_version`,
`fresh_until`, and `legacy: bool`. Targeted Gateway observations require endpoint
ID and generation together; non-Legacy generation is positive, Legacy unknown is
zero. Freshness follows #139 observation semantics and cannot precede capture.

### `TraceMeasurement`

Required: `name` (a versioned allow-listed measurement name), `kind`, one and
only one of `duration_ns`, `count`, `bytes`, `tokens`, `ratio`, `boolean`,
`timestamp`, or safe scalar `value`, plus `provenance`. Optional: `unit` only for
generic scalar values, `uncertainty`, `sample_count`, `observed_at`, `expires_at`,
and `legacy_name`. Duration unit is structurally fixed to nanoseconds and must be
non-negative. Ratios are finite and `[0,1]`; counts/bytes/tokens are non-negative.
Predicted and actual values are separate objects and may share a semantic name.
Generic values reject mappings/lists to prevent arbitrary payload smuggling.

### `TraceStage`

Required: `stage_id` (`stage_<32 hex>`), `name`, `sequence` (non-negative,
process-assigned append sequence), `outcome`, `provenance`, and tuple
`measurements`. Optional: UTC `started_at`/`ended_at`, `duration_ns`,
`operation_id`, `artifact_id`, safe `outcome_code`, safe `error_code`, sanitized
`error_message`, `retryable`, `fallback_eligible`, `fallback_stage_id`,
`parent_stage_id`, `partial_reason`, and `legacy`. Start/end are correlation
markers only. If both exist, order them by UTC but do not derive the duration from
them. Duration is local monotonic elapsed time. A terminal stage is immutable;
an in-progress collector state is not exported as the same object.

### `RequestTrace`

Required: `context`, ordered tuple `stages`, `exported_at` UTC, `complete: bool`,
and schema version. Optional: `source_components`, sanitized top-level
`error_code`, `legacy_trace` (JSON-safe copy of current dictionary), and
`legacy_cacheroute_meta` during migration. Canonical ordering is
`(stage-rank, started_at-or-max, source_component, sequence, stage_id)`; sequence
breaks ties but does not imply cross-process causality. JSON uses enum strings,
UTC `Z` timestamps, integer nanoseconds, and stable tuple-to-array conversion.

### `CacheOperationTrace`

Required: existing `CacheOperationTask.task_id` as `operation_id`, operation
type, `trace_id`, ordered stages, current existing task state, and provenance.
Optional: artifact/endpoint IDs and generation, idempotency key hash (never the
raw secret-like key), created/updated/expiry UTC timestamps, sanitized error and
fallback fields, and legacy projection. It references rather than duplicates
`CacheArtifact`, `CacheReplicaObservation`, `LMCacheEndpoint`, or
`CacheOperationTask`.

### `OperationWaiterLink`

Required: `operation_id`, request `trace_id`, request/correlation IDs,
`attached_at`, monotonically allocated `attach_sequence`, and state
`waiting|completed|cancelled|detached|expired`. Optional: `detached_at`, safe
reason, and operation outcome observed at attachment. This is a correlation
record, not scheduler state and cannot influence dispatch.

### Secret and physical-KV rejection

All models use `extra="forbid"` plus recursive validators rejecting case-folded
field names such as `password`, `secret`, `authorization`, `cookie`, `token_value`,
`redis_key`, `kv_bytes`, `physical_kv`, `tensor`, `pointer`, `device_address`, and
absolute/file paths. `tokens` means a numeric count only. Prompts, generated
content, raw exceptions, HTTP bodies/headers, Redis keys, manifests, physical KV
locations, and credentials are never valid trace values. Legacy projection
allow-lists known scalar keys rather than embedding the whole acknowledgement.

## 8. Clock design

Inject a `TraceClock` with `utc_now()` and `monotonic_ns()`; production uses
timezone-aware `datetime.now(timezone.utc)` and `time.perf_counter_ns()`.
Tests use a deterministic fake. On local stage start, store both readings in the
mutable collector. On finish, calculate `duration_ns = end_mono - start_mono`,
reject negatives, and export UTC start/end plus the local duration. Never export
monotonic readings, compare them across processes, or derive durations by
subtracting epoch milliseconds.

A stage spanning Proxy and Instance is represented as either (a) two linked
local stages with independently measured durations, or (b) one parent stage with
UTC correlation markers and child stages. Its end-to-end duration is measured by
one process that owns both send and response receipt (for example, Proxy Gateway
request duration). Remote work has its own Instance duration. Network/clock
offset must not be inferred as the difference between unrelated monotonic clocks.

## 9. Compatibility-first propagation

| Mechanism | Use | Decision |
|---|---|---|
| Add fields directly to current Request | Easy serialization, but changes a widely used dataclass/wire body | Do not use in Phase 1/2. |
| Dedicated internal envelope | Separates routing body and trace context; explicit filtering | Primary mechanism from Phase 3. |
| HTTP headers | Works at hops and avoids OpenAI JSON pollution; intermediaries may strip them | Mirror only allow-listed context IDs per internal hop. |
| Process-local collector reference | Efficient within one process, impossible across processes | Use only behind adapters; never serialize references. |

Recommended envelope:

```json
{
  "request": {"Request_ID": 42, "Prompt": {}, "Service": {}, "Task": {}},
  "_cacheroute_internal": {
    "trace_context": {
      "schema_version": "cacheroute.trace-context.v1",
      "trace_id": "trace_...",
      "request_id": "req_...",
      "correlation_id": "corr_...",
      "legacy_request_id": 42,
      "sampled": true
    }
  }
}
```

Proxy accepts both bare legacy Request and envelope. It strips the internal
section before constructing `instance_body`, then sends only allow-listed
`x-cacheroute-trace-id`, `x-cacheroute-request-id`, and
`x-cacheroute-correlation-id` to Instance. Instance strips these before vLLM
unless a public adapter explicitly supports correlation. KDN/Gateway versioned
calls place IDs in their existing request fields; headers are hop diagnostics,
not competing identity. Streaming merges immutable snapshots at the final meta
event; non-streaming does so in `_cacheroute_meta`. Existing meta fields and
dictionary remain unchanged while an optional `request_trace_v1` is added.

If tracing is disabled, no collector/stages are allocated and propagation may be
limited to existing IDs. If not sampled, propagate context IDs with
`sampled=false` for correlation but collect/export no detailed measurements.
Sampling is decided once at ingress using a deterministic policy and never
changed downstream. Any trace validation/export error is swallowed at the
observability boundary with a rate-limited diagnostic; it must never change
routing, forwarding, fallback, reuse, queue ordering, or responses.

## 10. Shared-operation correlation

Maintain a bounded `operation_id -> ordered waiter links` registry in the KDN or
Gateway orchestration layer, separate from `CacheOperationTask` and scheduling.

* **Attach:** idempotent on `(operation_id, trace_id)`. Duplicate legacy request
  IDs are allowed because trace ID is authoritative. Return the existing link on
  retry; allocate a stable sequence only once.
* **Detach/cancel:** request cancellation transitions only its link; it does not
  cancel shared work unless the existing operation owner independently decides
  to do so. No scheduling-policy change is implied.
* **Completion races:** retain terminal operation summaries until TTL. A waiter
  registering after completion receives a completed link and the same immutable
  summary. Completion snapshots the then-current waiters; later links remain
  deterministically ordered after them.
* **Expiry:** terminal task/link TTL is explicit. Active-task entries have a
  maximum lifetime and emit `expired`; purge uses injected UTC/monotonic clocks.
* **Bounded memory:** configure maximum operations, waiters per operation, and
  terminal TTL; evict expired terminal records first. If capacity remains full,
  omit correlation with a diagnostic rather than affecting the operation.
* **Idempotency:** the existing operation idempotency key controls operation
  deduplication; waiter idempotency is the pair above. Never use request ID alone.
* **Ordering:** export links by `(attach_sequence, trace_id)` and operation stages
  by the trace canonical order, never hash/set iteration order.

## 11. Migration map (no silent renames)

| Current representation | v1 projection |
|---|---|
| `Request_ID` / `ProxyTask.request_id` | `TraceContext.legacy_request_id`; generate opaque request/trace IDs. |
| `*_start_ms`, `*_end_ms` | UTC `started_at`/`ended_at` observations plus separately measured local `duration_ns`. |
| `predict_*` | `TraceMeasurement(kind="predicted")`; never overwrite. |
| overwritten `predict_prepare_ms` / `predict_know_prepare_ms` | Preserve original dictionary; adapter emits the final value as `legacy_projected` because original kind is unknowable, and emits unambiguous `actual_*` separately when present. |
| `actual_compute_ms` | Legacy projection of Proxy-observed Instance round trip to first chunk, not compute. |
| `actual_vllm_internal_ms` | Actual at Proxy boundary with name `proxy_forward_to_first_chunk`; not vLLM-internal. |
| `first_token_ms` | `first_token` only when token parsing proves it; otherwise `gateway_request`/forward first-chunk observation. |
| `decode_start_ms/end_ms` | Legacy-projected decode approximation until vLLM events exist. |
| `text_actual_path`, `kvcache_actual_path` | Explicit stage outcome + error/fallback code; retain strings in legacy dictionary. |
| `error` / `first_token_missing_reason` | Sanitized stable `error_code` and optional safe message; retain original only in existing meta. |
| integer boolean flags | Typed booleans in stage fields. |
| `kv_ack.network_*` | Measurement with declared producer/boundary and kind; otherwise legacy-projected. |
| queue snapshots / Prometheus deltas | Endpoint-level `observed`, or `inferred` only under documented isolated-test assumptions. |

## 12. Rollout and exact file plan

### Phase 1 — dependency-light vertical slice

Add:

* `cacheroute_observability/__init__.py` — public, dependency-light exports.
* `cacheroute_observability/enums.py` — stage, kind, outcome, component vocabularies and
  stable rank table.
* `cacheroute_observability/models.py` — frozen schemas and validators.
* `cacheroute_observability/clock.py` — clock protocol, production clock, test seam.
* `cacheroute_observability/collector.py` — process-local append-only collection.
* `cacheroute_observability/legacy_proxy_trace.py` — pure Legacy projection.
* `test/observability/` — CPU-only contract, collector, isolation, adapter, and demo tests.
* `scripts/demo_observability_v1.py` — deterministic executable demonstration.
* `cacheroute_observability/README.md` — maintained package documentation.

Do not modify production component files. This is the independently reviewable
first PR: contracts, collector, Legacy adapter, deterministic CPU-only tests, and
package documentation. It includes no production instrumentation, propagation,
Gateway I/O, or external tracing backend.

### Phase 2 — production compatibility integration

Modify `proxy/proxy.py` at `build_cacheroute_meta` to optionally append
`request_trace_v1`, and possibly correct `ProxyTask.trace`'s annotation to
`Dict[str, Any]` without changing values. Retain the dictionary and meta shape.

### Phase 3 — component instrumentation/propagation

Add internal-envelope helpers and modify
`scheduler/scheduler.py`, `core/fwd.py`, `proxy/proxy.py`,
`proxy/queue/task.py`, `proxy/queue/manager.py`, `proxy/queue/instance_queues.py`,
`proxy/queue/knowledge.py`, KDN cache-service facade call sites,
`kdn_server/gateway/base.py`, `instance/instance_api.py`,
`instance/control_plane.py`, and `instance/kv_service.py`. Add component and Mock
Gateway timeline tests. Changes remain observational and additive.

### Phase 4 — optional runtime observations

Add optional adapter modules under `instance/observability/` (public event or
labelled-metric adapters only) and validator reporting changes. No core model
imports an LMCache/vLLM client. Keep unlabelled Prometheus delta classification
as endpoint aggregate/isolated inference.

## 13. CPU-only test matrix

| Test | Assertions | External requirements |
|---|---|---|
| Serialization | Exact enum strings, UTC JSON, ns integers, deterministic stage/measurement order, round trip | None |
| Frozen export | Exported context/stage/trace cannot mutate; collector append creates a new snapshot | None |
| Clock | Injected monotonic duration, zero allowed, negative rejected, no epoch-derived duration | None |
| Value kinds | Same semantic metric can coexist as predicted/observed/actual/inferred; no overwrite | None |
| Provenance | Runtime/Profile/endpoint pair and positive generation validation; Legacy generation zero only | None |
| Freshness | valid expiry; stale observation retained with stale outcome; bad ordering rejected | None |
| Outcomes | unsupported/partial/failed/skipped/cancelled/fallback serialization and safe errors | None |
| Shared task | multiple waiters, duplicates, late registration, cancellation, expiry, bounded capacity, stable order | None |
| Legacy projection | Every current trace key maps or remains allow-listed legacy; overwritten predictions marked ambiguous projection | None |
| Free-form compatibility | Current mixed int/float/string/None dictionary is preserved byte-for-value in existing meta | None |
| Disabled/sampled | disabled allocates no stages; unsampled propagates only context; neither changes callback results/order | None |
| Security | reject secrets, auth headers, raw tokens/prompts, Redis keys, file paths, tensors, KV bytes/pointers, extras | None |
| Mock Gateway timeline | request, async operation, observation, shared waiter, Instance load, completion combine deterministically | In-memory Mock Gateway only |
| Import isolation | importing `cacheroute_observability` does not load FastAPI/httpx/redis/vllm/lmcache/torch/CUDA modules | None |
| Environment independence | full suite runs with network disabled and without Redis, LMCache, vLLM, GPU, or tracing backend | None |

Validation for the first PR should run from the repository root with
`python3 -m pytest -q test/observability` and an import-isolation subprocess test.
Failure is any nondeterministic order, mutable exported object, negative duration
acceptance, kind collapse, forbidden physical/secret field acceptance, external
service access, or behavior difference when tracing is disabled.

## 14. Maintainer decisions and unresolved questions

1. Is `cacheroute_observability/` accepted, or should #139/#140 common primitives first
   move inward to avoid `core -> kdn_server.domain/contracts` imports?
2. Is the canonical request ID generated at Client when supplied or always at
   Scheduler? What retry semantics should preserve it?
3. Should `correlation_id` default to `request_id`, or be mandatory and distinct?
4. Are `incompatible` and `idempotency_conflict` first-class stage outcomes, or
   should the trace retain the smaller stage vocabulary plus #140 `outcome_code`?
5. Which measurement names warrant a closed v1 allow-list in the first PR?
6. May safe `source_endpoint` contain normalized route templates such as
   `/v1/chat/completions`, or only logical endpoint IDs? Arbitrary method names
   must not become stage names either way.
7. What are the default sampling rate, terminal operation TTL, maximum tracked
   operations, and maximum waiters per operation?
8. Should an unsampled request export a minimal `RequestTrace`, or only preserve
   context in existing `cacheroute_meta`?
9. Can upstream streaming adapters reliably distinguish first decoded token from
   role/metadata chunks across supported vLLM versions? Until confirmed, keep the
   existing marker legacy-projected.
10. Which `kv_ack` network durations are measured with monotonic clocks at their
    producer, and which are estimates? They must remain Legacy/ambiguous until
    provenance is confirmed.
11. Is preserving raw free-form `error` in legacy meta acceptable during the
    transition, given that v1 exports will sanitize it?

These decisions do not block a contract-only first PR if the initial schema
marks disputed fields optional and the PR contains no production instrumentation.
