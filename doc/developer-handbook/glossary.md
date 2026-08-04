# Glossary

[Back to handbook](README.md).

| Term | Meaning |
|---|---|
| RuntimeProfile | Canonical runtime compatibility enum: `v1`, `legacy`, `test/mock`, and startup-only `auto`. |
| Legacy | Explicit compatibility with older CacheRoute/LMCache behavior; not automatically Deprecated. |
| v1 | Current version boundary for canonical KDN contracts (`kdn.v1`) and modern runtime profile; not a version of the entire repository. |
| test/mock | Runtime profile for tests/mocks; forbidden from selecting real Redis key layouts. |
| Scheduler | Central control plane selecting Proxy/KDN resources and building/forwarding work. |
| Proxy | Local execution control plane selecting Instances, queueing, preparing knowledge, and forwarding. |
| Instance | vLLM-facing service and capability/resource boundary. |
| KDN | Knowledge Data Network service managing text, KV artifacts, embeddings, and resource status. |
| knowledge ID / `kid` | Existing knowledge identifier owned by current KB code. No universal format is documented because source does not declare one canonical regex. |
| artifact ID | Deterministic `artifact_` plus 32 lowercase hexadecimal characters from canonical artifact identity. |
| endpoint ID | Deterministic `endpoint_` plus 32 lowercase hexadecimal characters from endpoint name. |
| endpoint generation | Positive incarnation counter; zero means unknown only on Legacy projections/targets where allowed. |
| compatibility profile | Non-empty identifier binding runtime/gateway compatibility; its string format is intentionally opaque. |
| CacheOperationTask | Immutable logical cache-operation lifecycle snapshot; it does not execute backend work. |
| cache operation/task ID | `cacheop_` plus 32 lowercase hexadecimal characters. |
| trace ID | Cross-stage trace identifier. No Current canonical format exists on this baseline. |
| request ID | Contract v1 default is `req_` plus 32 hexadecimal characters; other legacy request paths can have their own IDs. |
| correlation ID | Optional caller-provided relationship identifier; no canonical pattern is imposed. |
| stage ID | Identifier for a trace stage; observability v1 is In review, so no Current canonical format is claimed. |
| injection mode | Request execution choice. Current primitive paths are `text` and `kvcache`; perf `hybrid` expands a ratio into those values. |
| predicted | Model-estimated value before the event. |
| desired | Requested/intended state, not proof it occurred. |
| observed | Reported from a named observation source, with freshness/provenance where modeled. |
| measured | Directly instrumented quantity. |
| actual | Selected/executed result confirmed by the responsible path. |
| inferred | Derived from other evidence rather than directly measured. |
| legacy-projected | Read-only interpretation of Legacy data; low-confidence/uncertain and not authoritative backend state. |
| canonical | Authoritative owner/import for a concept. |
| public | Supported, documented import or interface; explicit `__all__` guides Python surfaces. |
| internal | Implementation detail without compatibility promise. |
| compatibility shim | Temporary forwarding/adapter path preserving an older import or wire behavior. |
| Historical | Earlier repository behavior, not supported current behavior. |
| Current | Present on the checked-in main implementation baseline. |
| Transitional | Present and supported while accepted migration remains incomplete. |
| Target / Accepted | Approved end-state architecture, whether implemented or not. |
| In review | Exists only on an unmerged review branch; not Current. |
| Proposed | Suggested but not accepted/merged. |
| Deprecated | Still supported with an approved removal direction or milestone. |
