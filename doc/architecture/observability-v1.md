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

Phase 4A does not instrument services, propagate trace context across
processes, change requests or responses, export telemetry, perform I/O, or
integrate with OpenTelemetry, Gateway implementations, LMCache, or vLLM.
Later focused work may add propagation and adapters after their wire and
failure semantics are reviewed.
