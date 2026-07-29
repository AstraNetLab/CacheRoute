# CacheRoute observability v1

`cacheroute_observability` is the dependency-light Phase 1 contract and collection
boundary for Issue #141. It imports only the Python standard library and Pydantic,
so Client, Scheduler, Proxy, KDN, Gateway, and Instance code can adopt it later
without loading the CacheRoute application graph.

## Models and vocabulary

Frozen, extra-forbidding contracts represent trace context, provenance, typed
measurements, ordered stages, request traces, cache-operation traces, and links
between one shared operation and multiple waiting requests. Stable enums never
encode route names, implementation methods, Redis commands, or private LMCache
events. `TraceStageState` describes lifecycle (`pending`, `running`, `completed`);
`TraceStageOutcome` independently describes the terminal result.

## Clocks and collector

UTC wall-clock values support cross-process correlation. Durations come only from
local `monotonic_ns()` readings. `ManualTraceClock` makes both sources deterministic
in CPU-only tests. `TraceCollector` starts stages with both readings, calculates a
local monotonic duration on finish, preserves append sequence (including repeated
stage names), and exports a new immutable snapshot. Disabled and unsampled
collectors allocate no stages. Optional instrumentation can use `safely()` so an
observability failure cannot affect caller behavior.

## Legacy projection and security

`project_legacy_proxy_trace()` is a pure allow-list adapter. It classifies known
Proxy fields, treats ambiguous and overwritten values as `legacy_projected`, uses
truthful Proxy-boundary names, sanitizes known fallback codes, and omits unknown
keys and raw error text. It never embeds the source trace or `kv_ack` mapping.
Contracts reject extras, containers as generic scalar values, secret/physical-KV
field names, raw content, paths, credentials, Redis keys, KV bytes, tensors, and
pointers.

## Phase 1 limitations

This package provides contracts, a process-local collector, Legacy projection,
and a CPU-only demonstration. It does **not** instrument production components,
propagate context, change `cacheroute_meta`, perform Gateway/network I/O, attribute
aggregate metrics to requests, or integrate with LMCache/vLLM. Those remain later
Issue #141 phases after review.

The temporary design record is
[`doc/research/issue-141-unified-observability.md`](../doc/research/issue-141-unified-observability.md)
and will be removed after Issue #141 is completed and stable material is moved to
maintained documentation.
