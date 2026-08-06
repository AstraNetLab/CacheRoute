# Observability v1 foundation

Issue #178 establishes CacheRoute's Phase 4A observability foundation before
any production instrumentation. Stable serializable models live in
`cacheroute.observability.v1`; the unversioned `cacheroute.observability`
package exports only clocks, the process-local collector, and the Legacy Proxy
projection helper. The package reuses `RuntimeProfile`, `OutcomeCode`,
`ContractErrorDetail`, LMCache topology vocabulary, and cache operation
vocabulary from their canonical owners rather than defining lookalikes.

## Schema and lifecycle

`TraceContext` carries an explicit `observability.v1` schema version and a
resolved runtime profile. `TraceStageState` describes collection lifecycle.
Only a completed stage has a canonical `OutcomeCode`; a skipped stage instead
has a bounded safe reason. Explicit, unique sequence numbers define order, so
clock adjustment cannot reorder stages and one stage name may occur repeatedly.

Provenance records where and when a value was captured. Endpoint identity and
generation are paired, generation zero is restricted to Legacy projections,
and canonical Gateway profiles are reused. Measurements have a required value
kind and exactly one typed value. Prediction, observation, measurement, actual,
inference, and Legacy projection therefore remain distinguishable.

All exported snapshots are recursively immutable: collections are tuples and
nested records are frozen validated models. Validated copies rerun invariants.
Prompts, generated text, headers, bodies, secrets, raw errors, physical KV
payloads, tensors, paths, private adapter objects, and physical indexes have no
schema field and are rejected by bounded safe scalar validation.

## Timing and correlation

`SystemTraceClock` uses UTC wall time for external correlation and
`time.perf_counter_ns()` for elapsed duration. The collector never derives a
duration by subtracting wall-clock timestamps. `ManualTraceClock` provides
independent, non-decreasing time domains for deterministic CPU-only tests.

A request snapshot can reference multiple logical cache operation IDs. An
operation snapshot can contain multiple immutable waiter links. These links
record correlation only and do not transition canonical `CacheOperationTask`
state or alter queue policy. Gateway request and asynchronous operation stages
are separate vocabulary, allowing their durations to remain separate.

## Legacy boundary and limitations

`project_legacy_proxy_trace` is a pure allow-list reader for today's Proxy trace
dictionary. Unknown keys, `kv_ack`, raw errors, and the source mapping are not
copied. Ambiguous or overwritten values are labeled `legacy_projected`, never
upgraded to actual observations. The current `cacheroute_meta` has no
`request_id`, and this foundation does not add one.

## Internal propagation

The Scheduler now creates the internal context and overwrites the complete
reserved header set: `scheduler-request-id`, `x-cacheroute-trace-version`,
`x-cacheroute-trace-id`, `x-cacheroute-runtime-profile`,
`x-cacheroute-trace-sampled`, and `x-cacheroute-trace-created-at`. The request
ID allocated by the Scheduler remains authoritative. Client values using these
names are never trusted; Authorization forwarding and the serialized payload
remain unchanged. Propagation now reaches the selected Instance through the same exact reserved header set. Proxy encodes its accepted Scheduler context, or its Proxy-local fallback context, immediately before forwarding to Instance and overwrites every reserved value for that internal call. No arbitrary client trace header becomes authoritative and no JSON/base64 trace payload is added to the request body. Instance validates the complete reserved set, accepts matching fresh context, or creates a request-local fallback context using its resolved startup profile and sample rate. The reserved headers stop at Instance: Instance-to-vLLM forwarding does not include CacheRoute trace headers, W3C Trace Context, or any canonical trace object, and no trace is returned to a client.

Scheduler and Proxy each resolve `CACHEROUTE_RUNTIME_PROFILE` through an explicit lifespan startup helper, with `legacy` as the compatibility default. Because the current services do not have an implemented production v1 data path, `auto` resolves with `v1_available=False` and is stored as `legacy`; explicit `legacy`, `test/mock`, and `v1` remain valid metadata values, but no stored or propagated context can remain `auto`. A missing, malformed, stale, request-ID-mismatched, or profile-mismatched context causes a Proxy-local context to be created and never rejects an otherwise valid request. Profile metadata does not select runtime behavior. The internal propagation freshness rule retains the five-minute maximum age and accepts only a bounded 30-second future clock skew among Scheduler, Proxy, and Instance clocks.

`CACHEROUTE_TRACE_SAMPLE_RATE` defaults to `0.0`. Invalid configuration fails
closed to that value. Rates of zero and one disable or enable collection for
every request; intermediate decisions are deterministically derived from the
canonical trace ID. An accepted context retains the Scheduler decision.

## Proxy-observed stages

The Proxy prepare queue interval starts immediately before `prepare_q.put` and
finishes at dequeue. The ready queue interval starts immediately before the
current ready-queue insertion, after reservation and prediction work, and
finishes after the dispatch-turn wait, immediately before forwarding. Completion
spans downstream handling. For streams, first-token spans forwarding to the first
non-empty chunk and decode spans from that chunk until stream end. Non-streaming
requests explicitly skip first-token and decode; an empty successful stream fails
first-token and completion with the bounded empty-stream error, skips decode, and
exports a failed request trace. These are **Proxy-observed transport boundaries**, not authoritative
vLLM execution, prefill, decode, Gateway, or LMCache timings.

Collection remains process-local and immutable. The Legacy trace mapping and
client metadata are unchanged and are not copied into `RequestTrace`. There is
no client export, external exporter, registry, debug endpoint, or persistence.


## Instance-observed stages

Instance resolves `CACHEROUTE_RUNTIME_PROFILE` and `CACHEROUTE_TRACE_SAMPLE_RATE` once during FastAPI lifespan startup and stores the immutable result in application state. The compatibility default remains `legacy`; `auto` is resolved and never persisted; invalid sample rates fail closed to `0.0` with at most one bounded warning reason. These settings are correlation metadata only and do not select mock versus real vLLM mode, registration, heartbeat, topology discovery, routing, injection, fallback, retries, or timeouts.

For sampled valid Instance requests, collection is request-local. Completion spans only the Instance-observed downstream boundary around the existing mock or real-vLLM helper. Streaming first response spans from downstream invocation to the first non-empty downstream chunk observed by Instance. Streaming decode spans from after that chunk until the downstream stream ends. Non-streaming requests skip first response and decode with `non_streaming_request`. Empty streams, failures, and cancellations finalize without running stages and use bounded static canonical errors. All Instance stages use `TraceComponent.INSTANCE`; this slice does not emit `VLLM_PREFILL`, does not claim vLLM or LMCache provenance, and does not provide authoritative internal vLLM prefill/decode timing, LMCache hit-token data, remote-read data, external export, persistence, registry, aggregation, or client-visible traces. Proxy and Instance may contain repeated stage names in separate process-local traces that share one `TraceContext`.
